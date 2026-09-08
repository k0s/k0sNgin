import hashlib
import html
import mimetypes
import os
import pathlib
import re
import time
from collections import defaultdict
from email.utils import formatdate, parsedate_to_datetime
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from .cache import RenderCache
from .directory import collect_cascading_formatters, serve_directory
from .formatter import apply_formatters
from .links import is_allowed
from .path import TOP_LEVEL_DIR
from .transformer import UNKNOWN_RENDERER, resolve_renderer
from .version import COMMIT

HERE = pathlib.Path(__file__).parent

# Cache policy: media/static files may be cached this long (seconds) by
# browsers and the Cloudflare edge; everything else (HTML, text) must
# revalidate every time (`no-cache`), which the 304 handling below makes
# cheap. Trade-off: an in-place media edit can stay stale up to this long
# unless the edge is purged.
MEDIA_MAX_AGE = int(os.environ.get("K0SNGIN_MEDIA_MAX_AGE", str(24 * 60 * 60)))
MEDIA_CACHE_TYPES = ("image/", "audio/", "video/", "font/",
                     "text/css", "application/javascript", "text/javascript")


def cache_control_for(media_type) -> str:
    """Cache-Control policy for a response content type."""
    if media_type and media_type.startswith(MEDIA_CACHE_TYPES):
        return f"public, max-age={MEDIA_MAX_AGE}"
    return "no-cache"


# Rendering happens in the request path only on a cache miss. In steady state
# the asset pipeline has already rendered everything, so a miss means a gap in
# the pipeline rather than ordinary traffic — hence the warning on every one.
# The size cap keeps a pathologically large "text" file from being read whole
# into memory here; above it, the file is served as itself.
MAX_RENDER_BYTES = int(os.environ.get("K0SNGIN_MAX_RENDER_BYTES", str(2 * 1024 * 1024)))
render_cache = RenderCache()

# Formatters that describe the *page* rather than a directory listing. A
# rendered document takes these from its containing directory, so it carries
# the site's stylesheets, favicon, navigation header and breadcrumbs. `title`
# is deliberately excluded: `/title` names the directory, not the document.
PAGE_FORMATTERS = ("css", "icon", "include", "breadcrumbs")

# Transformer names we've already complained about, so a misconfigured
# directory costs one warning rather than one per request.
unknown_transformers = set()

first_heading = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
markup = re.compile(r"<[^>]+>")


def document_title(fragment: str, fallback: str) -> str:
    """A document's title: its first heading, else `fallback`.

    Taking the title from the content means a Markdown file names its own page
    the same way it names itself when read as source.
    """
    match = first_heading.search(fragment)
    if not match:
        return fallback
    title = html.unescape(markup.sub("", match.group(1))).strip()
    return title or fallback


def renderer_for(requested_path: pathlib.Path):
    """The renderer that should transform this file, or None to serve it as-is.

    Resolves `/transformer` from the containing directory up to the served
    root. Every "no" here — no directive, no matching glob, a Content-Type
    override rather than a renderer, an unknown renderer, an oversized file —
    means the file is served unchanged, which is what it did before this
    feature existed.
    """
    # Shared with the pre-render CLI (see transformer.resolve_renderer), so the
    # two cannot disagree about which files render. A Content-Type target —
    # decoupage's `*.ini=text/plain` form — resolves to no renderer here: it is
    # recognised so it isn't mistaken for a broken renderer name, not acted on.
    renderer, reason = resolve_renderer(requested_path)
    if renderer is None:
        if reason.startswith(UNKNOWN_RENDERER) and reason not in unknown_transformers:
            unknown_transformers.add(reason)
            print(f"Renderer not found: {reason}")  # TODO: log this; a warning
        return None

    if requested_path.stat().st_size > MAX_RENDER_BYTES:
        print(f"Too large to render, serving as-is: {requested_path}")  # TODO: log
        return None

    return renderer


def file_etag(stat_result) -> str:
    """ETag for a file — Starlette's FileResponse formula, reproduced so the
    etags we validate against are the same ones FileResponse has been
    handing out."""
    etag_base = f"{stat_result.st_mtime}-{stat_result.st_size}"
    return f'"{hashlib.md5(etag_base.encode(), usedforsecurity=False).hexdigest()}"'


def etag_matches(request: Request, etag: str) -> bool | None:
    """Whether ``If-None-Match`` accepts `etag`; None if the client sent none."""
    if_none_match = request.headers.get("if-none-match")
    if not if_none_match:
        return None
    tokens = {token.strip().removeprefix("W/")
              for token in if_none_match.split(",")}
    return "*" in tokens or etag in tokens


def client_cache_is_fresh(request: Request, etag: str, mtime: float) -> bool:
    """True if the client's conditional headers show it already has the file.

    ``If-None-Match`` wins over ``If-Modified-Since`` (RFC 9110 §13.1.3).
    """
    matched = etag_matches(request, etag)
    if matched is not None:
        return matched
    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            since = parsedate_to_datetime(if_modified_since)
        except (TypeError, ValueError):
            return False
        return int(mtime) <= since.timestamp()
    return False

print(f"K0sNgin serving files from: {TOP_LEVEL_DIR}")
print(f"K0sNgin commit: {COMMIT}")

# Disable API docs for security
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Rate limiting middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Get client IP (consider X-Forwarded-For from Cloudflare)
        client_ip = request.client.host if request.client else "unknown"
        if "x-forwarded-for" in request.headers:
            # Cloudflare sets this header
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()

        # Clean old entries (older than 1 minute)
        current_time = time.time()
        self.request_counts[client_ip] = [
            timestamp for timestamp in self.request_counts[client_ip]
            if current_time - timestamp < 60
        ]

        # Check rate limit
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": "60"}
            )

        # Record this request
        self.request_counts[client_ip].append(current_time)

        return await call_next(request)

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Identify the build being served (read once at import; see version.py)
        response.headers["X-K0sNgin-Commit"] = COMMIT
        # Content Security Policy - adjust based on your needs
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response

# Always enable rate limiting (60 requests per minute per IP by default;
# K0SNGIN_RATE_LIMIT overrides, e.g. for the test suite)
app.add_middleware(RateLimitMiddleware,
                   requests_per_minute=int(os.environ.get("K0SNGIN_RATE_LIMIT", "60")))
app.add_middleware(SecurityHeadersMiddleware)

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=HERE / "templates")


def serve_document(requested_path: pathlib.Path, request: Request, renderer) -> Response:
    """Serve a file rendered to HTML, wrapped in the containing directory's chrome.

    Only the rendered *fragment* is cached. The page around it is assembled per
    request from the directory's cascading formatters, so restyling the site or
    editing its navigation shows up immediately and invalidates no artifacts.
    """
    source = requested_path.read_bytes()
    relative_source = requested_path.relative_to(TOP_LEVEL_DIR)
    fragment, was_cached = render_cache.get_or_render(source, relative_source, renderer)
    if not was_cached:
        # Loud on purpose: with the asset pipeline pre-rendering, a miss is a
        # gap in the pipeline. This line is the signal that target is slipping.
        print(f"Render cache miss: {relative_source} ({renderer.name})")  # TODO: log

    directory = requested_path.parent
    variables = {"files": {}, "request": request, "document_html": fragment}
    cascading = collect_cascading_formatters(directory)
    page_formatters = {key: value for key, value in cascading.items()
                       if key in PAGE_FORMATTERS}
    apply_formatters(page_formatters, directory, request, variables)

    variables["title"] = document_title(fragment, requested_path.name)
    variables["directory_name"] = requested_path.name
    # The document's parent is the directory holding it, not the directory above.
    path_info = request.scope.get("path", "/")
    variables["parent_url"] = path_info.rsplit("/", 1)[0] + "/"

    body = templates.get_template("document.html").render(**variables)

    # The ETag covers the *response*, not the source file: the same Markdown
    # renders differently after a renderer upgrade or a change to the site's
    # CSS cascade, and a source-derived etag would claim otherwise.
    etag = f'"{hashlib.md5(body.encode("utf-8"), usedforsecurity=False).hexdigest()}"'
    headers = {
        "etag": etag,
        "cache-control": "no-cache",
        "last-modified": formatdate(requested_path.stat().st_mtime, usegmt=True),
    }
    # Deliberately If-None-Match only. `If-Modified-Since` would wrongly report
    # "not modified" when the source is untouched but the rendered page changed.
    if etag_matches(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="text/html; charset=utf-8", headers=headers)


@app.api_route("/{file_path:path}", methods=["GET", "HEAD"])
async def serve_file(file_path: str, request: Request):
    """
    Serve files from the K0SNGIN_TOP_LEVEL directory.

    Security: Only serves files strictly within the top-level directory.
    Directories are rendered using Jinja2 templates with optional index.conf metadata.

    Args:
        file_path: The path to the file relative to K0SNGIN_TOP_LEVEL

    Returns:
        FileResponse: The requested file content, or
        TemplateResponse: Directory index page for directories

    Raises:
        HTTPException: 404 if file not found or outside allowed directory
        HTTPException: 403 if permission denied
    """
    # The requested path, normalized lexically ("." / ".." collapsed) but with
    # symlinks intact — this is the path we serve, so directory features
    # (index.ini cascade, local templates) see the content tree, not a
    # symlink's target.
    requested_path = pathlib.Path(os.path.normpath(TOP_LEVEL_DIR / file_path))

    # Security check, two layers: the request must stay inside the top-level
    # directory lexically...
    try:
        requested_path.relative_to(TOP_LEVEL_DIR)
    except ValueError:
        # Path is outside the allowed directory
        raise HTTPException(status_code=404, detail="File not found")

    # ...and its real path (every symlink followed) must land inside the tree
    # or inside an allowed link target (K0SNGIN_LINKS).
    if not is_allowed(requested_path.resolve()):
        raise HTTPException(status_code=404, detail="File not found")

    # Check if the file exists
    if not requested_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Check if it's a directory - redirect to trailing slash version
    if requested_path.is_dir():
        # If the URL doesn't end with a slash, redirect to the version with a slash
        # But don't redirect if we're already at the root with a slash
        if file_path.strip('/') and not file_path.endswith('/'):
            return RedirectResponse(url=f"/{file_path}/", status_code=301)
        return serve_directory(requested_path, request, templates)

    # Extension-based rendering: `/transformer` may map this file to a renderer
    # (see transformer.py). `?format=raw` bypasses it and serves the source, as
    # it did in decoupage.
    if request.query_params.get("format") != "raw":
        renderer = renderer_for(requested_path)
        if renderer is not None:
            return serve_document(requested_path, request, renderer)

    # Conditional requests: answer 304 when the client's cache is current.
    stat_result = requested_path.stat()
    etag = file_etag(stat_result)
    media_type = mimetypes.guess_type(requested_path.name)[0]
    cache_control = cache_control_for(media_type)
    if client_cache_is_fresh(request, etag, stat_result.st_mtime):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={
            "etag": etag,
            "cache-control": cache_control,
            "last-modified": formatdate(stat_result.st_mtime, usegmt=True),
        })

    # Serve the file with inline disposition
    file_response = FileResponse(
        path=str(requested_path),
        filename=requested_path.name,
        media_type=media_type,
    )

    # Override the Content-Disposition header to display inline
    file_response.headers["Content-Disposition"] = f"inline; filename=\"{requested_path.name}\""
    file_response.headers["Cache-Control"] = cache_control

    return file_response

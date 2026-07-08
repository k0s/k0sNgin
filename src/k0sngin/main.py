import hashlib
import mimetypes
import os
import pathlib
import time
from collections import defaultdict
from email.utils import formatdate, parsedate_to_datetime
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from .directory import serve_directory
from .path import TOP_LEVEL_DIR
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


def file_etag(stat_result) -> str:
    """ETag for a file — Starlette's FileResponse formula, reproduced so the
    etags we validate against are the same ones FileResponse has been
    handing out."""
    etag_base = f"{stat_result.st_mtime}-{stat_result.st_size}"
    return f'"{hashlib.md5(etag_base.encode(), usedforsecurity=False).hexdigest()}"'


def client_cache_is_fresh(request: Request, etag: str, mtime: float) -> bool:
    """True if the client's conditional headers show it already has the file.

    ``If-None-Match`` wins over ``If-Modified-Since`` (RFC 9110 §13.1.3).
    """
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        tokens = {token.strip().removeprefix("W/")
                  for token in if_none_match.split(",")}
        return "*" in tokens or etag in tokens
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
    # Resolve the requested file path
    requested_path = (TOP_LEVEL_DIR / file_path).resolve()

    # Security check: ensure the file is within the top-level directory
    try:
        requested_path.relative_to(TOP_LEVEL_DIR)
    except ValueError:
        # Path is outside the allowed directory
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

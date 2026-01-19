import os
import pathlib
import time
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from pydantic import BaseModel
from .parser import parse_config
from .directory import serve_directory
from .path import TOP_LEVEL_DIR

HERE = pathlib.Path(__file__).parent

print(f"K0sNgin serving files from: {TOP_LEVEL_DIR}")

# Determine if we're in production (disable docs)
PRODUCTION = os.environ.get("K0SNGIN_PRODUCTION", "false").lower() == "true"

app = FastAPI(
    docs_url="/docs" if not PRODUCTION else None,
    redoc_url="/redoc" if not PRODUCTION else None,
    openapi_url="/openapi.json" if not PRODUCTION else None,
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

# Configure rate limiting (default: 60 requests per minute per IP)
rate_limit = int(os.environ.get("K0SNGIN_RATE_LIMIT", "60"))
app.add_middleware(RateLimitMiddleware, requests_per_minute=rate_limit)
app.add_middleware(SecurityHeadersMiddleware)

# Initialize Jinja2 templates
templates = Jinja2Templates(directory=HERE / "templates")


@app.get("/{file_path:path}")
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

    # Serve the file with inline disposition
    file_response = FileResponse(
        path=str(requested_path),
        filename=requested_path.name,
        media_type=None  # Let FastAPI determine the media type
    )

    # Override the Content-Disposition header to display inline
    file_response.headers["Content-Disposition"] = f"inline; filename=\"{requested_path.name}\""

    return file_response

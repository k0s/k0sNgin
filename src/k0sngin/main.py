import os
import pathlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from .parser import parse_config
from .directory import serve_directory
from .path import TOP_LEVEL_DIR

HERE = pathlib.Path(__file__).parent

print(f"K0sNgin serving files from: {TOP_LEVEL_DIR}")

app = FastAPI()

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
            return RedirectResponse(url=f"{file_path}/", status_code=301)
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


class ParseRequest(BaseModel):
    content: str


@app.post("/parse")
async def parse_config_content(request: ParseRequest):
    """
    Parse a custom INI-like configuration format.

    This format supports:
    - Key-value pairs: key = value
    - Line continuation: indented lines continue the previous value
    - Special keys starting with /
    - Empty values
    """
    try:
        parsed = parse_config(request.content)
        return parsed
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")


@app.get("/format-info")
async def get_format_info():
    """
    Get information about the supported format.
    """
    return {
        "format": "Unix conf-file format",
        "features": [
            "Key-value pairs: key = value",
            "Line continuation: indented lines continue the previous value",
            "Special keys starting with /",
            "Empty values supported"
        ],
        "example": {
            "content": "/title = My Title\n    with continuation\nkey = value",
            "parsed": {
                "/title": "My Title with continuation",
                "key": "value"
            }
        }
    }

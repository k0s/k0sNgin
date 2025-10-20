import os
import pathlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Dict
from .parser import parse_config

# Get the top-level directory from environment or use CWD
TOP_LEVEL_DIR = pathlib.Path(os.environ.get("K0SNGIN_TOP_LEVEL", os.getcwd())).resolve()
print(f"K0sNgin serving files from: {TOP_LEVEL_DIR}")

app = FastAPI()

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="src/k0sngin/templates")


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

    # Check if it's a directory - render directory index
    if requested_path.is_dir():
        # Look for index files or generate directory listing
        files = {}
        description = None

        # Check for index.conf file for metadata
        index_conf_path = requested_path / "index.conf"
        if index_conf_path.exists():
            try:
                with open(index_conf_path, 'r') as f:
                    conf_content = f.read()
                parsed_conf = parse_config(conf_content)

                # Extract description if available
                if "/description" in parsed_conf:
                    description = parsed_conf["/description"]

                # Extract file information
                for key, value in parsed_conf.items():
                    if not key.startswith("/") and not key.startswith("_"):
                        files[key] = {
                            "description": value,
                            "name": key
                        }
            except Exception:
                # If parsing fails, fall back to basic directory listing
                pass

        # If no index.conf or parsing failed, do basic directory listing
        if not files:
            try:
                for item in requested_path.iterdir():
                    if item.is_file():
                        files[item.name] = {
                            "description": None,
                            "name": item.name
                        }
            except PermissionError:
                raise HTTPException(status_code=403, detail="Permission denied")

        # Render the directory index template
        return templates.TemplateResponse("index.html", {
            "request": request,
            "directory_name": file_path or "Root",
            "description": description,
            "files": files
        })

    # Serve the file
    return FileResponse(
        path=str(requested_path),
        filename=requested_path.name,
        media_type=None  # Let FastAPI determine the media type
    )


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

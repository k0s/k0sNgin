import os
import pathlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict
from .parser import parse_config

# Get the top-level directory from environment or use CWD
TOP_LEVEL_DIR = pathlib.Path(os.environ.get("K0SNGIN_TOP_LEVEL", os.getcwd())).resolve()
print(f"K0sNgin serving files from: {TOP_LEVEL_DIR}")

app = FastAPI()


@app.get("/{file_path:path}")
async def serve_file(file_path: str):
    """
    Serve files from the K0SNGIN_TOP_LEVEL directory.

    Security: Only serves files strictly within the top-level directory.
    Directories are not supported and will return NotImplemented.

    Args:
        file_path: The path to the file relative to K0SNGIN_TOP_LEVEL

    Returns:
        FileResponse: The requested file content

    Raises:
        HTTPException: 404 if file not found or outside allowed directory
        HTTPException: 501 if requesting a directory
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

    # Check if it's a directory (not supported)
    if requested_path.is_dir():
        raise HTTPException(status_code=501, detail="Directory listing not implemented")

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

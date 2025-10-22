"""
Directory indexer.
"""

import pathlib
from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates

from .formatter import apply_formatters
from .parser import parse_config


class DirectoryIndexer:
    """Directory indexer."""
    # XXX Unused

    def __init__(self, directory: pathlib.Path):
        self.directory = directory

    def index(self) -> dict:
        """Index the directory."""
        return {}


def parse_index_conf(index_conf_path: pathlib.Path) -> dict:
    """Parse the index.ini file."""

    # TODO: Handle cascading index.ini files
    with open(index_conf_path, 'r') as f:
        conf_content = f.read()
    parsed =  parse_config(conf_content)

    # Extract formatters
    formatters = {}
    for item in list(parsed.keys()):
        if item.startswith("/"):
            key = item[1:].strip()
            if not key:
                raise ValueError(f"Empty key: {item}")
            value = parsed.pop(item).strip()
            formatters[key] = value


    # Extract file information
    files = {}
    for key, value in parsed.items():
        if not key.startswith("/") and not key.startswith("_"):
            files[key] = {
                "description": value,
                "name": key
            }
    return {
        "formatters": formatters,
        "files": files
    }


def serve_directory(requested_path: pathlib.Path, request: Request, templates: Jinja2Templates) -> dict:
    """
    Serve a directory.
    Look for index.ini file for metadata and generate directory listing.
    """

    template_variables = None

    # Check for index.ini file for metadata
    index_conf_path = requested_path / "index.ini"
    if index_conf_path.exists():
        try:
            template_variables = parse_index_conf(index_conf_path)
        except Exception:
            # If parsing fails, fall back to basic directory listing
            pass

    # If no index.conf or parsing failed, do basic directory listing
    # TODO: this should be done first and then refined from `index.ini`
    if template_variables is None:
        files = {}
        try:
            for item in requested_path.iterdir():
                if item.is_file():
                    files[item.name] = {
                        "description": None,
                        "name": item.name
                    }
        except PermissionError:
            raise HTTPException(status_code=404, detail="Not found")

        template_variables = {
            "files": files
        }

    # Apply formatters
    formatters = template_variables.pop("formatters", None)
    if formatters is not None:
        template_variables = apply_formatters(formatters, requested_path, request, template_variables)

    # Populate template variables
    # Get the directory path from the request
    path_info = request.scope.get("path", "/")
    # Remove trailing slash for display, then add it back
    if path_info == "/":
        template_variables["directory_name"] = "/"
    else:
        template_variables["directory_name"] = path_info.rstrip("/") + "/"

    template_variables["request"] = request

    # Render the directory index template
    return templates.TemplateResponse("index.html", template_variables)

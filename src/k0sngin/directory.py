"""
Directory indexer.
"""

import pathlib
from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates

from .formatter import apply_formatters
from .parser import parse_config
from .path import TOP_LEVEL_DIR


class DirectoryIndexer:
    """Directory indexer."""
    # XXX Unused

    def __init__(self, directory: pathlib.Path):
        self.directory = directory

    def index(self) -> dict:
        """Index the directory."""
        return {}


def parse_index_conf(index_conf_path: pathlib.Path) -> dict:
    """Parse the index.ini file and return formatters and files separately."""

    with open(index_conf_path, 'r') as f:
        conf_content = f.read()
    parsed = parse_config(conf_content)

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


def collect_cascading_formatters(directory: pathlib.Path) -> dict:
    """
    Collect formatters by walking up the directory tree from the given directory
    to the root, with child directories overriding parent formatters.
    """
    formatters = {}

    # Walk up the directory tree from current to root
    current_dir = directory
    while True:
        # Check if we've reached the top-level directory
        try:
            current_dir.relative_to(TOP_LEVEL_DIR)
        except ValueError:
            # We've gone above the top-level directory, stop here
            break

        # Look for index.ini in current directory
        index_conf_path = current_dir / "index.ini"
        if index_conf_path.exists():
            try:
                conf_data = parse_index_conf(index_conf_path)
                # Child formatters override parent formatters
                formatters.update(conf_data["formatters"])
            except Exception:
                # If parsing fails, continue to parent directory
                pass

        # Move to parent directory
        parent = current_dir.parent
        if parent == current_dir:
            # We've reached the filesystem root
            break
        current_dir = parent

    return formatters


def serve_directory(requested_path: pathlib.Path, request: Request, templates: Jinja2Templates) -> dict:
    """
    Serve a directory.
    Look for index.ini file for metadata and generate directory listing.
    """

    template_variables = {
        "files": {}
    }

    # Get directory listing
    files = {}
    for item in requested_path.iterdir():

        try:
            # Determine file type
            type = None
            if item.is_file():
                type = 'file'
            elif item.is_dir():
                type = 'directory'

            files[item.name] = {
                "name": item.name,
                "type": type
                # TODO: created, last modified, size...
            }
        except PermissionError:
            # Just skip for now
            # We should log this eventually
            continue

    # Check for index.ini file for metadata (only for current directory)
    index_conf_path = requested_path / "index.ini"
    if index_conf_path.exists():
        try:
            conf_data = parse_index_conf(index_conf_path)
            template_variables.update(conf_data)
        except Exception:
            # If parsing fails, fall back to basic directory listing
            pass

    # Augment parsed data with directory listing metadata
    for name, data in files.items():
        if name not in template_variables['files']:
            template_variables['files'][name] = data

    # Collect cascading formatters from parent directories
    cascading_formatters = collect_cascading_formatters(requested_path)

    # Apply formatters (cascading formatters override local ones)
    local_formatters = template_variables.pop("formatters", {})
    all_formatters = {**cascading_formatters, **local_formatters}
    if all_formatters:
        template_variables = apply_formatters(all_formatters, requested_path, request, template_variables)

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

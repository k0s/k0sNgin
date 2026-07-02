"""
Directory indexer.
"""

import fnmatch
import pathlib
from fastapi import Request, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

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


def select_visible_names(disk_entries: dict, declared: dict, local_formatters: dict) -> set:
    """Select which directory entries to list, per the local ``all`` directive.

    - ``all`` absent          -> every entry on disk.
    - ``all`` empty string     -> only files described in this ``index.ini`` that
      exist on disk (dangling descriptions are skipped).
    - ``all`` = comma-separated globs -> entries whose filename matches any glob
      (``fnmatch``); surrounding whitespace is insignificant.

    ``all`` is **local** to the directory — it is never inherited from parents.
    See ``docs/formatters.md``.
    """
    if "all" not in local_formatters:
        return set(disk_entries)
    value = local_formatters["all"].strip()
    if not value:
        return {name for name in declared if name in disk_entries}
    globs = [glob.strip() for glob in value.split(",") if glob.strip()]
    return {
        name for name in disk_entries
        if any(fnmatch.fnmatch(name, glob) for glob in globs)
    }


def serve_directory(requested_path: pathlib.Path, request: Request, templates: Jinja2Templates) -> dict:
    """
    Serve a directory.
    Look for index.ini file for metadata and generate directory listing.
    """

    template_variables = {
        "files": {}
    }

    # Raw directory listing: name -> basic metadata.
    disk_entries = {}
    for item in requested_path.iterdir():
        try:
            item_type = None
            if item.is_file():
                item_type = 'file'
            elif item.is_dir():
                item_type = 'directory'

            disk_entries[item.name] = {
                "name": item.name,
                "type": item_type
                # TODO: created, last modified, size...
            }
        except PermissionError:
            # Just skip for now
            # We should log this eventually
            continue

    # index.ini for THIS directory: described files + local formatters.
    declared = {}
    local_formatters = {}
    index_conf_path = requested_path / "index.ini"
    if index_conf_path.exists():
        try:
            conf_data = parse_index_conf(index_conf_path)
            declared = conf_data["files"]
            local_formatters = conf_data["formatters"]
        except Exception:
            # If parsing fails, fall back to a plain listing.
            declared = {}
            local_formatters = {}

    # Which entries are visible (the `all` directive; local, non-cascading).
    visible = select_visible_names(disk_entries, declared, local_formatters)

    # Build the listing: described entries first (in index.ini order), then any
    # remaining entries (directory order) — restricted to the visible set.
    files = {}
    for name, data in declared.items():
        if name in visible:
            entry = dict(data)
            if name in disk_entries:
                entry.setdefault("type", disk_entries[name]["type"])
            files[name] = entry
    for name, data in disk_entries.items():
        if name in visible and name not in files:
            files[name] = data
    template_variables["files"] = files

    # Collect cascading formatters from parent directories
    cascading_formatters = collect_cascading_formatters(requested_path)

    # Apply formatters (cascading formatters override local ones). `all` is
    # handled above (local listing filter), so strip it out — it is not a
    # template formatter and must not cascade.
    merged_formatters = {**cascading_formatters, **local_formatters}
    merged_formatters.pop("all", None)
    if merged_formatters:
        template_variables = apply_formatters(merged_formatters, requested_path, request, template_variables)

    # Populate template variables
    # Get the directory path from the request
    path_info = request.scope.get("path", "/")
    # Remove trailing slash for display, then add it back
    if path_info == "/":
        template_variables["directory_name"] = "/"
    else:
        template_variables["directory_name"] = path_info.rstrip("/") + "/"

    template_variables["request"] = request

    # Check for local template override
    template_name = "index.html"  # TODO: make this configurable
    local_template_path = requested_path / template_name
    if local_template_path.exists():
        # Try to verify the file is UTF-8 decodable before using as template
        try:
            with open(local_template_path, 'r', encoding='utf-8') as f:
                f.read()
        except UnicodeDecodeError:
            # File is not UTF-8, serve it as-is instead of as a template
            return FileResponse(
                path=str(local_template_path),
                media_type="text/html"
            )

        # File is UTF-8, use it as a template
        env = Environment(loader=FileSystemLoader(str(requested_path)))
        template = env.get_template("index.html")
        html_content = template.render(**template_variables)
        return Response(content=html_content, media_type="text/html")
    else:
        # Use default template
        # TODO: reconcile with the local template path mechanism above
        return templates.TemplateResponse(template_name, template_variables)

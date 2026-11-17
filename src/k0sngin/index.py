"""Per-directory metadata: ``index.json``, and ``index.ini`` before it.

``index.json`` is the successor to ``index.ini``. Where ``index.ini`` packs a
title, a description and links into one string that directives teach the
server to take apart, ``index.json`` names each field::

    {
      "version": 1,
      "title": "Portfolio",
      "entries": [
        {"name": "resume.html", "title": "My Resume",
         "links": {"PDF": "resume.pdf"}}
      ],
      "k0sngin": {"all": false, "css": ["/css/style.css"]}
    }

The top level and ``entries`` are for any reader. Everything about how
k0sNgin presents the directory is under ``"k0sngin"``; other namespaces
belong to other tools and are ignored here, as are fields this version does
not know.

Both formats are read into one internal shape (``formatters`` and ``files``),
so the rest of the server does not care which a directory uses, and a tree can
be converted one directory at a time. Where a directory has both,
``index.json`` wins. See ``docs/index-json.md``.
"""

import json
import logging
import pathlib

from .parser import parse_config

log = logging.getLogger(__name__)

VERSION = 1
INI = "index.ini"
JSON = "index.json"

# Set on entries read from index.json: their title and links are already
# named fields, so the formatters that split descriptions leave them alone.
STRUCTURED = "structured"


class MetadataError(ValueError):
    """An index.json that claims to be directory metadata and is malformed."""


def parse_ini(text: str) -> dict:
    """Split parsed ``index.ini`` content into formatters and files."""
    parsed = parse_config(text)
    formatters = {}
    for item in list(parsed.keys()):
        if item.startswith("/"):
            key = item[1:].strip()
            if not key:
                raise ValueError(f"Empty key: {item}")
            formatters[key] = parsed.pop(item).strip()
    files = {key: {"description": value, "name": key}
             for key, value in parsed.items()
             if not key.startswith("/") and not key.startswith("_")}
    return {"formatters": formatters, "files": files, "source": "ini"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MetadataError(message)


def _strings(value, what: str) -> list:
    _require(isinstance(value, list) and all(isinstance(i, str) for i in value),
             f"{what} must be a list of strings")
    return value


def validate(data: dict) -> dict:
    """Check the fields this version reads; unknown fields pass untouched.

    The same rules as ``schema/index-v1.json``, which the tests hold this to.
    """
    _require(data.get("version") == VERSION, f"version must be {VERSION}")
    for key in ("title", "description", "link"):
        _require(isinstance(data.get(key, ""), str), f"{key} must be a string")
    entries = data.get("entries", [])
    _require(isinstance(entries, list), "entries must be a list")
    for entry in entries:
        _require(isinstance(entry, dict) and isinstance(entry.get("name"), str)
                 and entry["name"], "every entry needs a name")
        name = entry["name"]
        for key in ("title", "description"):
            _require(isinstance(entry.get(key, ""), str), f"{name}: {key} must be a string")
        links = entry.get("links", {})
        _require(isinstance(links, dict)
                 and all(isinstance(v, str) for v in links.values()),
                 f"{name}: links must map text to targets")
        _strings(entry.get("tags", []), f"{name}: tags")
        _require(isinstance(entry.get("hidden", False), bool),
                 f"{name}: hidden must be true or false")
    ours = data.get("k0sngin", {})
    _require(isinstance(ours, dict), "k0sngin must be an object")
    if "all" in ours and not isinstance(ours["all"], bool):
        _strings(ours["all"], "k0sngin.all")
    for key in ("ignore", "css"):
        if key in ours:
            _strings(ours[key], f"k0sngin.{key}")
    for key in ("icon", "include", "layout"):
        _require(isinstance(ours.get(key, ""), str), f"k0sngin.{key} must be a string")
    _require(isinstance(ours.get("breadcrumbs", True), bool),
             "k0sngin.breadcrumbs must be true or false")
    _require(isinstance(ours.get("images", {}), dict), "k0sngin.images must be an object")
    audio = ours.get("audio", {})
    _require(audio is False or isinstance(audio, dict),
             "k0sngin.audio must be an object, or false")
    transformer = ours.get("transformer", {})
    _require(isinstance(transformer, dict)
             and all(isinstance(v, str) for v in transformer.values()),
             "k0sngin.transformer must map globs to targets")
    return data


def _arguments(options: dict) -> str:
    """A formatter argument string (``flag, key=value``) from an object."""
    parts = []
    for key, value in options.items():
        if value is True:
            parts.append(key)
        elif value is not False and value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def _images(options: dict) -> str:
    options = dict(options)
    width, height = options.pop("width", None), options.pop("height", None)
    if width is not None or height is not None:
        options["size"] = f"{'' if width is None else width}x{'' if height is None else height}"
    return _arguments(options)


def from_json(data: dict) -> dict:
    """The internal shape for validated ``index.json`` data.

    Formatter values are rendered back into the argument strings the
    formatters parse, so there is one implementation of each formatter rather
    than one per file format. The title is the exception: it is passed as an
    object, because a string would have to be split on ``:`` again.
    """
    formatters = {}
    if data.get("title"):
        formatters["title"] = {"title": data["title"], "link": data.get("link")}
    ours = data.get("k0sngin", {})
    if "all" in ours and ours["all"] is not True:
        formatters["all"] = "" if ours["all"] is False else ", ".join(ours["all"])
    if "ignore" in ours:
        formatters["ignore"] = ", ".join(ours["ignore"])
    if "css" in ours:
        formatters["css"] = " ".join(ours["css"])
    for key in ("icon", "include"):
        if key in ours:
            formatters[key] = ours[key]
    if "breadcrumbs" in ours:
        formatters["breadcrumbs"] = "" if ours["breadcrumbs"] else "off"
    if "images" in ours:
        formatters["images"] = _images(ours["images"])
    if "audio" in ours:
        formatters["audio"] = "off" if ours["audio"] is False else _arguments(ours["audio"])
    if ours.get("layout"):
        formatters["template"] = f"{ours['layout']}.html"
    if "transformer" in ours:
        formatters["transformer"] = ",".join(
            f"{glob}={target}" for glob, target in ours["transformer"].items())

    files = {}
    for entry in data.get("entries", []):
        record = {"name": entry["name"], "description": entry.get("description") or None,
                  STRUCTURED: True}
        if entry.get("title"):
            record["title"] = entry["title"]
        if entry.get("links"):
            record["links"] = dict(entry["links"])
        if entry.get("tags"):
            record["tags"] = list(entry["tags"])
        if entry.get("hidden"):
            record["hidden"] = True
        files[entry["name"]] = record
    return {"formatters": formatters, "files": files, "source": "json"}


def load_json(path: pathlib.Path) -> dict | None:
    """The directory metadata in an ``index.json``, validated.

    Returns None when the file is some other JSON that happens to have the
    name: anything that is not an object with an integer ``version``. Raises
    ``MetadataError`` when it is meant as metadata and cannot be used.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MetadataError(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        return None
    try:
        return validate(data)
    except MetadataError as exc:
        raise MetadataError(f"{path}: {exc}") from exc


def read_index(directory: pathlib.Path) -> dict | None:
    """A directory's metadata as ``{"formatters", "files", "source"}``, from
    ``index.json`` if it has one and otherwise ``index.ini``; None with neither.

    Raises if the file it settles on cannot be read. Callers treat that as a
    directory with no metadata, so a broken file costs the page its
    descriptions rather than its existence.
    """
    json_path = directory / JSON
    if json_path.is_file():
        data = load_json(json_path)
        if data is not None:
            if (directory / INI).is_file():
                log.warning("%s has both %s and %s; using %s", directory, JSON, INI, JSON)
            return from_json(data)
    ini_path = directory / INI
    if ini_path.is_file():
        with open(ini_path, "r") as f:
            return parse_ini(f.read())
    return None

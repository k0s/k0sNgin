"""Convert ``index.ini`` content to ``index.json`` (version 1).

The conversion is the mapping table in ``docs/index-json.md``. It reuses the
server's own parsers for each directive, so a converted directory renders the
same page; the handful of places where it deliberately does not are listed in
that document, and reported as notes here.
"""

import json
import pathlib
import re

from .formatter import AudioFormatter, ImagesFormatter, LinksFormatter
from .index import VERSION, parse_ini
from .parser import parse_config
from .transformer import parse_transformer_map

OFF_VALUES = {"off", "false", "no"}
NAMESPACE = "k0sngin"
# For directives this server parses and ignores. They are decoupage's, the
# server index.ini was written for; carried so that converting loses nothing.
LEGACY_NAMESPACE = "decoupage"
# index.json is indented by two spaces, for reading and editing by hand.
INDENT = 2


def _number(text: str):
    """An int or float if `text` is one, else the text."""
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            continue
    return text


def convert_title(value: str) -> dict:
    """``/title``: the directory's title, and the URL it links to if the
    value has the ``Title: https://…`` form."""
    value = value.strip()
    if not value:
        return {}
    if ":" in value:
        title, url = [part.strip() for part in value.split(":", 1)]
        if "://" in url:
            return {"title": title, "link": url}
    return {"title": value}


def convert_all(value: str, notes: list):
    """``/all``: false for the empty value (list only described entries),
    else the globs. Lists separated by spaces rather than commas, which the
    server reads as one glob that matches nothing, are split properly."""
    value = value.strip()
    if not value:
        return False
    by_comma = [glob.strip() for glob in value.split(",") if glob.strip()]
    globs = [glob for glob in re.split(r"[,\s]+", value) if glob]
    if globs != by_comma:
        notes.append(f"/all was separated by spaces, which the server reads as one glob; "
                     f"split into {len(globs)}")
    return globs


def convert_images(value: str) -> dict:
    """``/images``: flags become true, ``size=WxH`` becomes width and height."""
    flags, kwargs = ImagesFormatter.parse_args(value)
    options = {flag: True for flag in flags}
    for key, text in kwargs.items():
        if key == "size":
            width, height = ImagesFormatter.parse_size(text)
            if width is not None:
                options["width"] = width
            if height is not None:
                options["height"] = height
        else:
            options[key] = _number(text)
    return options


def convert_audio(value: str):
    """``/audio``: false to turn an inherited player off, else its options."""
    if value.strip().lower() in OFF_VALUES:
        return False
    _flags, kwargs = ImagesFormatter.parse_args(value)
    options = {key: text for key, text in kwargs.items() if key != "gap"}
    if "gap" in kwargs:
        options["gap"] = AudioFormatter.parse_gap(kwargs["gap"])
    return options


def convert_entry(name: str, description: str, split_titles: bool, split_links: bool) -> dict:
    """One ``name = description`` line as an entry with named fields.

    `split_titles` and `split_links` say whether ``/title`` and ``/links``
    are in force for the directory, possibly inherited: they decide whether
    the description is taken apart, exactly as the server decides it.
    """
    entry = {"name": name}
    links = {}
    if split_links and description:
        links = dict(LinksFormatter.link_re.findall(description))
        if links:
            description = LinksFormatter.link_re.sub("", description).strip()
    if split_titles and description and ":" in description:
        title, description = [part.strip() for part in description.split(":", 1)]
        # An empty title shows the name, as the server does. It is written
        # out because, without the old split, nothing else would say so.
        entry["title"] = title or name
    if description:
        entry["description"] = description
    if links:
        entry["links"] = links
    return entry


def convert(text: str, in_force: dict | None = None) -> tuple[dict, list]:
    """``index.ini`` content as ``index.json`` data, plus notes on anything
    that was fixed, carried without being understood, or lost before it got
    here.

    `in_force` is the directory's cascaded formatters (its own included), as
    ``collect_cascading_formatters`` returns them. Without it only the file's
    own ``/title`` and ``/links`` are considered.
    """
    notes = []
    dropped = parse_config(text).get("_orphaned_lines")
    if dropped:
        notes.append(f"index.ini lines the server already drops (no '='): {dropped}")
    ini = parse_ini(text)
    formatters = ini["formatters"]
    in_force = formatters if in_force is None else in_force
    title_in_force = in_force.get("title")
    split_titles = bool(title_in_force.strip() if isinstance(title_in_force, str)
                        else title_in_force)
    split_links = "links" in in_force

    data = {"version": VERSION}
    ours, legacy = {}, {}
    converters = {
        "all": lambda v: convert_all(v, notes),
        "ignore": lambda v: [glob.strip() for glob in v.split(",") if glob.strip()],
        "css": str.split,
        "icon": str.strip,
        "include": str.strip,
        "breadcrumbs": lambda v: v.strip().lower() not in OFF_VALUES,
        "images": convert_images,
        "audio": convert_audio,
        "transformer": parse_transformer_map,
    }
    for key, value in formatters.items():
        if key == "title":
            data.update(convert_title(value))
        elif key == "links":
            pass        # a switch for reading descriptions; nothing to carry
        elif key == "template":
            ours["layout"] = value.strip().removesuffix(".html")
        elif key in converters:
            ours[key] = converters[key](value)
        else:
            legacy[key] = value
    if legacy:
        notes.append("directives the server ignores, carried under "
                     f"\"{LEGACY_NAMESPACE}\": {', '.join('/' + key for key in legacy)}")

    entries = [convert_entry(name, record["description"], split_titles, split_links)
               for name, record in ini["files"].items()]
    if entries:
        data["entries"] = entries
    if ours:
        data[NAMESPACE] = ours
    if legacy:
        data[LEGACY_NAMESPACE] = legacy
    return data, notes


def dumps(data: dict) -> str:
    """``index.json`` text as it should be on disk: JSON indented by two
    spaces, non-ASCII written as itself, ending in a newline. The files are
    meant to be read and edited by hand, and anything that rewrites one
    should write it this way."""
    return json.dumps(data, indent=INDENT, ensure_ascii=False) + "\n"


def missing_entries(data: dict, directory: pathlib.Path) -> list:
    """Names the entries describe that are not in the directory."""
    return [entry["name"] for entry in data.get("entries", [])
            if not (directory / entry["name"]).exists()
            and not (directory / entry["name"]).is_symlink()]

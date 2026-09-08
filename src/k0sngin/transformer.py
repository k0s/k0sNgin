"""The ``/transformer`` directive: which renderer handles which files.

Ported from decoupage, where ``/transformer`` mapped filename globs to named
transformers, with one wrinkle: a value containing ``/`` meant "serve this file
unchanged under that Content-Type" rather than naming a transformer. The live
site still carries that configuration verbatim (``*.txt=text/plain``,
``*.html=Genshi``, ``*.gv.txt=Graphviz``, …), so this parser understands both
forms and reports which is which. Only the named-renderer form is acted on
today; see ``docs/formatters.md`` for what is implemented.

Inheritance differs from ``/ignore`` on purpose. ``/ignore``'s glob list is
replaced wholesale by a descendant, but a transformer map *merges* down the
tree, most specific directory winning per glob. The value is a mapping rather
than a list, and the site's own configuration is written expecting a subtree to
add one extension without restating everything its ancestors declared. A bare
``/transformer =`` stops inheritance entirely, matching how ``/ignore`` clears.
"""

import fnmatch
import pathlib

from .path import TOP_LEVEL_DIR


def parse_transformer_map(value: str) -> dict:
    """Parse ``glob=target`` pairs into an ordered ``{glob: target}`` mapping.

    Declaration order is preserved because it is what disambiguates overlapping
    globs (see `target_for`). Malformed segments are skipped rather than
    raising — a typo in one entry should not take a directory's whole
    configuration with it.
    """
    mapping = {}
    for item in value.split(","):
        glob, separator, target = item.partition("=")
        if not separator:
            continue
        glob, target = glob.strip(), target.strip()
        if glob and target:
            mapping.setdefault(glob, target)
    return mapping


def resolve_transformer_map(directory: pathlib.Path) -> dict:
    """Merge ``/transformer`` from `directory` up to the served root.

    Walking child-to-parent and never overwriting an entry means the most
    specific directory wins per glob, and leaves the resulting mapping ordered
    most-specific-first — which is exactly the order `target_for` wants.
    """
    mapping = {}
    # Imported here rather than at module scope: directory.py imports formatter
    # machinery, and this module is imported from the serving path in main.py.
    from .directory import parse_index_conf

    current = directory
    while True:
        try:
            current.relative_to(TOP_LEVEL_DIR)
        except ValueError:
            # Above the served root; nothing here belongs to the site.
            break

        index_conf = current / "index.ini"
        if index_conf.exists():
            try:
                formatters = parse_index_conf(index_conf)["formatters"]
            except Exception:
                # An unparseable index.ini shouldn't disable transformers for
                # the whole subtree; skip this level as the indexer does.
                formatters = {}
            if "transformer" in formatters:
                value = formatters["transformer"].strip()
                if not value:
                    # An explicit `/transformer =` clears: inherit nothing more.
                    break
                for glob, target in parse_transformer_map(value).items():
                    mapping.setdefault(glob, target)

        parent = current.parent
        if parent == current:
            break
        current = parent

    return mapping


def target_for(filename: str, mapping: dict) -> str | None:
    """The transformer target for `filename`, or None if nothing matches.

    First match wins, as in decoupage. Because `resolve_transformer_map` orders
    the mapping most-specific-directory-first, a subtree's ``*.gv.txt`` is
    consulted before the root's ``*.txt``.
    """
    for glob, target in mapping.items():
        if fnmatch.fnmatch(filename, glob):
            return target
    return None


def is_content_type(target: str) -> bool:
    """True if `target` names a MIME type rather than a renderer.

    decoupage's convention, kept so the site's existing configuration keeps its
    meaning: ``*.ini=text/plain`` overrides a Content-Type, ``*.md=markdown``
    names a renderer.
    """
    return "/" in target

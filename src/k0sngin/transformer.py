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
from .renderers import get_renderer


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


def resolve_transformer_map(directory: pathlib.Path, top_level=None) -> dict:
    """Merge ``/transformer`` from `directory` up to the served root.

    Walking child-to-parent and never overwriting an entry means the most
    specific directory wins per glob, and leaves the resulting mapping ordered
    most-specific-first — which is exactly the order `target_for` wants.

    `top_level` names the root to stop at, defaulting to the served one. It is
    a parameter rather than only a module global because ``TOP_LEVEL_DIR`` is
    computed once at import: a caller that wants a different root — the
    pre-render CLI's ``--top-level`` — cannot get one by setting the
    environment afterwards, and silently walking the wrong tree is a much worse
    failure than an explicit argument is a cost.
    """
    root = TOP_LEVEL_DIR if top_level is None else top_level
    mapping = {}
    # Imported here rather than at module scope: directory.py imports formatter
    # machinery, and this module is imported from the serving path in main.py.
    from .directory import parse_index_conf

    current = directory
    while True:
        try:
            current.relative_to(root)
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


# Why a file is not being rendered. Returned alongside the renderer so callers
# can say *which* "no" they hit: the pre-render CLI reports these per file, and
# a file that should be rendering but isn't is diagnosed by reading this rather
# than by guessing at the cascade.
NO_DIRECTIVE = "no /transformer in the cascade"
NO_MATCH = "no /transformer glob matches"
CONTENT_TYPE = "maps to a Content-Type, not a renderer"
UNKNOWN_RENDERER = "renderer not found"


def resolve_renderer(path: pathlib.Path, top_level=None) -> tuple:
    """The renderer for `path`, as ``(renderer, reason)``.

    Exactly one of the two is meaningful: a renderer with `reason` None, or
    None with a `reason` naming the "no". Callers that only need a yes/no can
    ignore the second element.

    This is the single definition of "would this file be rendered". The server
    and the pre-render CLI both call it, deliberately: if they answered that
    question separately they would eventually disagree, and every disagreement
    is either a permanent cache miss or an artifact nothing ever reads.

    Note that `path` is used as given, symlinks intact. That matches how the
    server addresses a file — `site/stories` is a symlink, and a document
    beneath it belongs to the site tree at `stories/...`, not at the link's
    target — so resolving here would look up the wrong directory's `index.ini`
    and key the wrong cache entry.
    """
    mapping = resolve_transformer_map(path.parent, top_level)
    if not mapping:
        return None, NO_DIRECTIVE

    target = target_for(path.name, mapping)
    if target is None:
        return None, NO_MATCH

    if is_content_type(target):
        return None, CONTENT_TYPE

    renderer = get_renderer(target)
    if renderer is None:
        return None, f"{UNKNOWN_RENDERER}: {target}"

    return renderer, None

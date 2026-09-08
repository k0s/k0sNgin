"""Content renderers: source bytes -> HTML fragment.

A renderer turns a file's bytes into an HTML *fragment* — document body markup
with no ``<html>``/``<head>`` around it. Wrapping is deliberately somebody
else's job (``templates/document.html``), because it makes a cached fragment a
function of the source content and the renderer alone: restyling the site, or
changing its navigation, then invalidates nothing.

Renderers are named, and ``index.ini``'s ``/transformer`` directive maps
filename globs to those names (see ``transformer.py``). Each renderer carries a
``version`` that becomes a path component of its cache entries (see
``cache.py``), so changing how one renderer produces output invalidates exactly
its own artifacts. The version folds in the underlying library's version too —
upgrading cmarkgfm cannot leave stale HTML behind.
"""

import importlib.metadata
import re

import cmarkgfm
from cmarkgfm.cmark import Options

# Version strings become directory names, so keep them to characters that are
# unambiguous in a path.
UNSAFE_IN_PATH = re.compile(r"[^A-Za-z0-9._-]")


def library_version(distribution: str) -> str:
    """Installed version of `distribution`, for folding into a cache key.

    An unknown version deliberately reads as ``unknown`` rather than raising:
    failing to render a page because a version lookup failed would be a much
    worse outcome than a slightly less precise cache key.
    """
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return UNSAFE_IN_PATH.sub("_", version)


class Renderer:
    """Abstract base class for renderers.

    Subclasses set ``name`` (what ``/transformer`` refers to), bump ``schema``
    when their own output changes for identical input, and name the ``library``
    whose version should also invalidate cached output.
    """

    name: str = ""
    schema: str = "1"
    library: str | None = None

    @classmethod
    def version(cls) -> str:
        """Cache-invalidating version: our schema plus the library's version."""
        if not cls.library:
            return cls.schema
        return f"{cls.schema}+{cls.library}-{library_version(cls.library)}"

    def render(self, source: bytes) -> str:
        """Render source bytes to an HTML fragment."""
        raise NotImplementedError


class MarkdownRenderer(Renderer):
    """GitHub Flavored Markdown, via GitHub's own cmark-gfm.

    cmarkgfm binds libcmark-gfm — the C library GitHub renders with, and the
    one PyPI uses for project READMEs — so GFM support here is the real thing
    rather than an approximation: tables, task lists, strikethrough and
    autolinks all come from ``github_flavored_markdown_to_html`` itself.

    Raw HTML is dropped (cmarkgfm's default) instead of passed through. That is
    a deliberate agreement with the site's Content-Security-Policy, which
    forbids inline ``<script>`` and ``<style>``: a renderer that emitted them
    would only produce markup the browser refuses to run. The visible cost is
    that an ``<iframe>`` embedded in a document (bandcamp, soundcloud) is
    stripped rather than rendered.
    """

    name = "markdown"
    schema = "1"
    library = "cmarkgfm"

    options = Options.CMARK_OPT_FOOTNOTES

    def render(self, source: bytes) -> str:
        """Render GFM source to an HTML fragment."""
        # Undecodable bytes become replacement characters rather than an error:
        # a mangled character is a better outcome for a served page than a 500.
        text = source.decode("utf-8", errors="replace")
        return cmarkgfm.github_flavored_markdown_to_html(text, options=self.options)


all_renderers = [
    MarkdownRenderer,
]

renderers = {renderer.name: renderer for renderer in all_renderers}


def get_renderer(name: str) -> Renderer | None:
    """The renderer registered under `name`, or None if there isn't one."""
    renderer = renderers.get(name)
    return renderer() if renderer is not None else None

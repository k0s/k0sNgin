"""Shared pytest fixtures for k0sNgin.

The key constraint these fixtures work around: ``k0sngin.path.TOP_LEVEL_DIR`` is
resolved from ``K0SNGIN_TOP_LEVEL`` **once, at import time** (see ``path.py``).
So the served content root must be created and the env var set *before* the app
is imported. We therefore build a throwaway content tree at module load and set
the env var here, at the top of conftest — which pytest imports before any test
module — then import the app.

The tree deliberately includes a file *outside* the served root
(``secret.txt``) so the path-traversal test can prove a real, existing file
cannot be reached from under the top level.
"""

import os
import pathlib
import tempfile

import pytest

# --- Build the content tree BEFORE importing k0sngin (see module docstring). ---
_TMP_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="k0sngin-test-"))
_SITE = _TMP_ROOT / "site"
_SITE.mkdir()

# A plain file the server should serve.
(_SITE / "hello.txt").write_text("hello world\n")

# A subdirectory with an index.ini supplying a page title and a file
# description (the "name : description" split is applied by the title formatter).
_DOCS = _SITE / "docs"
_DOCS.mkdir()
(_DOCS / "readme.txt").write_text("readme body\n")
(_DOCS / "notes.txt").write_text("notes body\n")
(_DOCS / "report.html").write_text("<p>report</p>\n")
(_DOCS / "report.pdf").write_bytes(b"%PDF-1.4 stub\n")
(_DOCS / "paper.txt").write_text("paper body\n")
(_DOCS / "paper.pdf").write_bytes(b"%PDF-1.4 stub\n")
(_DOCS / "index.ini").write_text(
    "/title = Docs\n"
    "/links =\n"
    "readme.txt = the readme : a description\n"
    "notes.txt = just some notes\n"
    "report.html = The Report; [PDF]=report.pdf\n"
    "paper.txt = A Paper : with details; [PDF]=paper.pdf\n"
)

# A file OUTSIDE the served root: the traversal target that must stay unreachable
# even though it exists on disk.
(_TMP_ROOT / "secret.txt").write_text("TOP SECRET\n")

# --- Symlink-allowlist fixtures (K0SNGIN_LINKS; see src/k0sngin/links.py). ---
# An out-of-tree content directory that IS allowed via links.json…
_EXTERNAL = _TMP_ROOT / "external"
_EXTERNAL.mkdir()
(_EXTERNAL / "poem.txt").write_text("external poem\n")
(_EXTERNAL / "index.ini").write_text("poem.txt = a poem from outside\n")
# …including a nested symlink that tries to escape it (must stay unreachable).
(_EXTERNAL / "escape.txt").symlink_to(_TMP_ROOT / "secret.txt")
# An out-of-tree directory that is NOT in links.json.
_NOT_ALLOWED = _TMP_ROOT / "notallowed"
_NOT_ALLOWED.mkdir()
(_NOT_ALLOWED / "nope.txt").write_text("should never be served\n")

# Symlinks in the served tree pointing at each.
(_SITE / "linked").symlink_to(_EXTERNAL)
(_SITE / "unlisted").symlink_to(_NOT_ALLOWED)

# The links file: same shape as ~/web/ansible/links.json (string pairs; values
# may be absolute — home-relative resolution is unit-tested separately).
_LINKS_FILE = _TMP_ROOT / "links.json"
_LINKS_FILE.write_text('{"site/linked": "%s"}\n' % _EXTERNAL)

# --- Rendered-document fixtures (/transformer; see src/k0sngin/transformer.py).
# `documents/` opts into Markdown rendering and sets page chrome; each
# subdirectory exercises one way the directive can resolve differently from
# its parent.
_DOCUMENTS = _SITE / "documents"
_DOCUMENTS.mkdir()
(_DOCUMENTS / "index.ini").write_text(
    "/transformer = *.md=markdown\n"
    "/css = /documents.css\n"
    "/icon = /documents.ico\n"
)
(_DOCUMENTS / "notes.md").write_text(
    "# Notes on Deployment\n"
    "\n"
    "| key | value |\n"
    "|-----|-------|\n"
    "| a   | 1     |\n"
    "\n"
    "~~struck~~ text and a task list:\n"
    "\n"
    "- [x] done\n"
    "- [ ] pending\n"
    "\n"
    "<script>alert(\"xss\")</script>\n"
)

# Inherits /transformer from documents/ while overriding /css — a descendant's
# value must win over its ancestor's.
_NESTED = _DOCUMENTS / "nested"
_NESTED.mkdir()
(_NESTED / "index.ini").write_text("/css = /nested.css\n")
(_NESTED / "deep.md").write_text("# Deep\n\nnested body\n")

# No index.ini at all: inherits the directive unchanged.
_PLAIN = _DOCUMENTS / "plain"
_PLAIN.mkdir()
(_PLAIN / "inner.md").write_text("# Inner\n\ninner body\n")

# A bare `/transformer =` stops inheritance: these files stay untransformed.
_OPAQUE = _DOCUMENTS / "opaque"
_OPAQUE.mkdir()
(_OPAQUE / "index.ini").write_text("/transformer =\n")
(_OPAQUE / "off.md").write_text("# Off\n\nnot rendered\n")

# decoupage's Content-Type form (a `/` in the value) rather than a renderer.
_TYPED = _DOCUMENTS / "typed"
_TYPED.mkdir()
(_TYPED / "index.ini").write_text("/transformer = *.md=text/plain\n")
(_TYPED / "typed.md").write_text("# Typed\n\nnot rendered\n")

# A renderer that doesn't exist: must degrade to serving the file, not 500.
_UNKNOWN = _DOCUMENTS / "unknown"
_UNKNOWN.mkdir()
(_UNKNOWN / "index.ini").write_text("/transformer = *.md=NoSuchRenderer\n")
(_UNKNOWN / "mystery.md").write_text("# Mystery\n\nnot rendered\n")

# Outside any directory declaring /transformer: served as source, as before.
(_SITE / "untouched.md").write_text("# Untouched\n\nplain source\n")

# --- index.json fixtures (see src/k0sngin/index.py). ---
# The same content as docs/, as index.json: the two must render alike.
_JSONDOCS = _SITE / "jsondocs"
_JSONDOCS.mkdir()
for _name in ("readme.txt", "notes.txt", "report.html", "report.pdf", "paper.txt",
              "paper.pdf", "secret-draft.txt"):
    (_JSONDOCS / _name).write_text("body\n")
(_JSONDOCS / "index.json").write_text("""{
  "version": 1,
  "title": "Docs",
  "link": "https://example.org/docs",
  "entries": [
    {"name": "readme.txt", "title": "the readme", "description": "a description"},
    {"name": "notes.txt", "description": "just some notes"},
    {"name": "report.html", "description": "The Report", "links": {"PDF": "report.pdf"}},
    {"name": "paper.txt", "title": "A Paper", "description": "with details: and a colon",
     "links": {"PDF": "paper.pdf"}, "tags": ["paper"]},
    {"name": "secret-draft.txt", "description": "not listed", "hidden": true}
  ],
  "k0sngin": {"ignore": ["index.ini", "*.pdf"], "css": ["/json.css"]},
  "someone-else": {"anything": [1, 2, 3]}
}
""")
# No metadata of its own, under an index.json directory.
(_JSONDOCS / "bare").mkdir()
(_JSONDOCS / "bare" / "file.txt").write_text("body\n")
# An index.ini directory under an index.json one: it still needs the title
# switch to read its own descriptions.
(_JSONDOCS / "legacy").mkdir()
(_JSONDOCS / "legacy" / "old.txt").write_text("body\n")
(_JSONDOCS / "legacy" / "index.ini").write_text("old.txt = Old Title : old description\n")
# index.json wins where a directory has both.
_BOTH = _SITE / "bothformats"
_BOTH.mkdir()
(_BOTH / "a.txt").write_text("body\n")
(_BOTH / "index.ini").write_text("/title = From INI\na.txt = ini description\n")
(_BOTH / "index.json").write_text(
    '{"version": 1, "title": "From JSON", "entries": [{"name": "a.txt", "description": "json description"}]}\n')
# A file named index.json that is somebody's data, not directory metadata.
_DATA = _SITE / "jsondata"
_DATA.mkdir()
(_DATA / "index.json").write_text('{"nodes": [1, 2, 3]}\n')
(_DATA / "index.ini").write_text("/title = Data\nindex.json = the data : a graph\n")
# Metadata that is broken: the directory falls back to a plain listing.
_BROKEN = _SITE / "jsonbroken"
_BROKEN.mkdir()
(_BROKEN / "a.txt").write_text("body\n")
(_BROKEN / "index.json").write_text('{"version": 1, "entries": "not a list"}\n')
# An index.json directory under an index.ini one that sets a title.
_UNDERINI = _DOCS / "converted"
_UNDERINI.mkdir()
(_UNDERINI / "x.txt").write_text("body\n")
(_UNDERINI / "index.json").write_text(
    '{"version": 1, "entries": [{"name": "x.txt", "description": "keeps: its colon"}]}\n')
# Markdown rendering asked for from index.json.
_JSONMD = _SITE / "jsonmd"
_JSONMD.mkdir()
(_JSONMD / "page.md").write_text("# From JSON\n\nbody\n")
(_JSONMD / "index.json").write_text(
    '{"version": 1, "k0sngin": {"transformer": {"*.md": "markdown"}}}\n')

# The render cache lives outside the served tree — as it must in production,
# so derived artifacts never re-enter the asset pipeline as file events.
_CACHE_ROOT = _TMP_ROOT / "cache"
os.environ["K0SNGIN_CACHE_DIR"] = str(_CACHE_ROOT)

os.environ["K0SNGIN_LINKS"] = str(_LINKS_FILE)
os.environ["K0SNGIN_TOP_LEVEL"] = str(_SITE)
# The whole suite runs against one app instance from one client IP; keep the
# rate limiter (60/min default) from 429-ing the later tests.
os.environ["K0SNGIN_RATE_LIMIT"] = "100000"

# Safe to import the app now that the env is set.
from fastapi.testclient import TestClient  # noqa: E402
from k0sngin.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    """A TestClient bound to the app served from the throwaway content tree."""
    return TestClient(app)


@pytest.fixture(scope="session")
def site_root() -> pathlib.Path:
    """Path to the served top-level directory (``K0SNGIN_TOP_LEVEL``)."""
    return _SITE


@pytest.fixture(scope="session")
def cache_root() -> pathlib.Path:
    """Path to the render cache root (``K0SNGIN_CACHE_DIR``)."""
    return _CACHE_ROOT

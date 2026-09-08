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

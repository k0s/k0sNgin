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

os.environ["K0SNGIN_TOP_LEVEL"] = str(_SITE)

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

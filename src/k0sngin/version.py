"""Identify the build currently being served.

The commit is read **once at import** (not per request, not baked at build
time): because uvicorn ``--reload`` re-imports the module on code changes and a
service restart re-imports too, ``COMMIT`` refreshes exactly when the served
code changes. git is authoritative for the checkout-based deploy; the
``K0SNGIN_COMMIT`` env var is a fallback for environments without ``.git``
(e.g. a Docker image where the hash is injected at build).
"""

import os
import pathlib
import subprocess

_HERE = pathlib.Path(__file__).resolve().parent


def _read_commit() -> str:
    """Short commit hash of the running checkout, with ``-dirty`` if the working
    tree has uncommitted changes (so a dirty deploy can't masquerade as a commit).
    Never derived from request input; fixed argument vectors, no shell, bounded
    by a timeout so a hung git cannot block startup."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_HERE, capture_output=True, text=True, timeout=2, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_HERE, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        return f"{commit}{'-dirty' if dirty else ''}"
    except Exception:
        return os.environ.get("K0SNGIN_COMMIT", "unknown")


COMMIT = _read_commit()

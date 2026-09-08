"""On-disk cache of rendered HTML fragments.

Two properties make this cache a *contract* rather than a private
implementation detail, and both drive its layout:

1. **It lives outside the served tree**, and outside every directory the asset
   pipeline watches or unison syncs. Derived artifacts written into a watched,
   synced directory re-enter as change events on every peer; keeping renders
   under ``~/.cache`` makes that class of feedback loop structurally
   impossible rather than merely guarded against.

2. **Its paths mirror the source tree**, so source and artifact map to each
   other in both directions without reading either one::

       ~/.cache/k0sngin/render/<renderer>/<version>/<path/below/site/root>.html

   The asset pipeline's rule model requires that invertibility: it is what
   lets a reconciler tell warm from cold with a stat, which in turn is what
   makes "no cache misses" a measurable target instead of an aspiration.

Bumping a renderer's version orphans one whole directory — that is both the
invalidation mechanism and a safe thing to delete. The cache is pure derived
data throughout: removing any part of it costs a re-render and nothing else.

Serving never fails because of this cache. An unwritable cache directory
degrades to rendering on every request (warned once, not once per request);
an unreadable or corrupt entry is simply re-rendered.
"""

import hashlib
import os
import pathlib
import tempfile

# Every artifact starts with its source's digest, so a hit can be verified
# against the current file rather than inferred from timestamps. Hashing costs
# one read of a small text file, and buys correctness under exactly the cases
# mtime comparison gets wrong: unison and rsync -t preserve mtimes, and a
# restore from restic can move a file's content backwards in time.
HEADER_PREFIX = "<!-- k0sngin-render source-sha256="
HEADER_SUFFIX = " -->"


def default_cache_root() -> pathlib.Path:
    """Where rendered artifacts live, honouring K0SNGIN_CACHE_DIR then XDG."""
    configured = os.environ.get("K0SNGIN_CACHE_DIR")
    if configured:
        return pathlib.Path(configured).expanduser()
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = pathlib.Path(xdg_cache).expanduser() if xdg_cache else pathlib.Path.home() / ".cache"
    return base / "k0sngin" / "render"


class RenderCache:
    """Content-verified, path-addressed cache of rendered fragments."""

    def __init__(self, root: pathlib.Path | None = None):
        self.root = pathlib.Path(root) if root is not None else default_cache_root()
        # Whether we've already complained about being unable to write. A
        # broken cache is worth one warning, not one per request.
        self.warned = False

    def artifact_path(self, relative_source: pathlib.PurePath, renderer) -> pathlib.Path:
        """Cache path for `relative_source` (a path below the served root)."""
        return self.root / renderer.name / renderer.version() / f"{relative_source}.html"

    def get_or_render(self,
                      source: bytes,
                      relative_source: pathlib.PurePath,
                      renderer) -> tuple[str, bool]:
        """Return ``(fragment, was_hit)``, rendering and storing on a miss.

        A miss is reported rather than swallowed so callers can log it: with
        the asset pipeline pre-rendering, a miss means a gap in the pipeline,
        not ordinary traffic.
        """
        digest = hashlib.sha256(source).hexdigest()
        path = self.artifact_path(relative_source, renderer)

        cached = self.read(path, digest)
        if cached is not None:
            return cached, True

        fragment = renderer.render(source)
        self.write(path, digest, fragment)
        return fragment, False

    def read(self, path: pathlib.Path, digest: str) -> str | None:
        """The stored fragment if it was rendered from exactly this content."""
        try:
            stored = path.read_text(encoding="utf-8")
        except OSError:
            return None
        header, newline, fragment = stored.partition("\n")
        if not newline:
            return None
        if not (header.startswith(HEADER_PREFIX) and header.endswith(HEADER_SUFFIX)):
            return None
        stored_digest = header[len(HEADER_PREFIX):-len(HEADER_SUFFIX)]
        if stored_digest != digest:
            # The source changed underneath a stable path — a stale artifact,
            # about to be replaced.
            return None
        return fragment

    def write(self, path: pathlib.Path, digest: str, fragment: str) -> bool:
        """Store `fragment` atomically. False if the cache isn't writable."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.warn(f"cannot create cache directory {path.parent}: {error}")
            return False

        payload = f"{HEADER_PREFIX}{digest}{HEADER_SUFFIX}\n{fragment}"
        # Write-then-rename: a reader either sees the previous artifact or the
        # new one, never a half-written file. Matters because the pre-render
        # CLI and the server can be writing the same entry at once.
        handle = None
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(dir=path.parent,
                                                     prefix=".k0sngin-render-",
                                                     suffix=".html")
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
            handle.write(payload)
            handle.close()
            handle = None
            os.replace(temporary, path)
            return True
        except OSError as error:
            self.warn(f"cannot write cache entry {path}: {error}")
            if handle is not None:
                handle.close()
            if temporary is not None:
                pathlib.Path(temporary).unlink(missing_ok=True)
            return False

    def warn(self, message: str) -> None:
        """Complain about a broken cache once per process."""
        if self.warned:
            return
        self.warned = True
        # TODO: logging, once k0sNgin has any (see directory.py, formatter.py)
        print(f"Render cache unavailable, rendering every request: {message}")

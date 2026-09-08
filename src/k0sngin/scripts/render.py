"""Render documents into the cache ahead of time, so serving never has to.

The server renders on a cache miss, in the request path. That is a correctness
net rather than the intended steady state: dropping a file into the tree should
always work, but a visitor should not be the one who pays to render it. This
script is the other half of that bargain — point it at the content tree after
publishing and the miss never happens.

    k0sngin-render ~/web/site                  # the whole tree
    k0sngin-render ~/web/site/portfolio        # one subtree
    k0sngin-render ~/web/site/notes.md         # one file
    k0sngin-render --dry-run ~/web/site        # what is cold, changing nothing

Which files get rendered is decided by ``/transformer`` in the tree's
``index.ini`` files, not by this script — it asks the same question the server
asks, through the same function (``transformer.resolve_renderer``). Anything
else would let the two disagree, and a disagreement is either a permanent cache
miss or an artifact nothing ever reads. In practice that means Markdown today,
and whatever the configuration says tomorrow, with no change here.

Nothing it writes is precious: the cache is derived data, and ``--force``
re-renders, so the worst outcome of a bad run is wasted CPU.
"""

import argparse
import hashlib
import os
import pathlib
import sys

from ..cache import RenderCache
from ..path import TOP_LEVEL_DIR
from ..transformer import resolve_renderer

# What a file's outcome was, in the order a summary should read them.
RENDERED = "rendered"
WARM = "already cached"
SKIPPED = "skipped"
FAILED = "failed"


def parse_args(args):
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog="k0sngin-render",
        description="Render documents into the cache before anyone requests them.",
        epilog="Which files render is decided by /transformer in index.ini, "
               "the same way the server decides it.",
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", type=pathlib.Path,
                        help="files to render, or directories to crawl for them")
    parser.add_argument("--cache-dir", type=pathlib.Path, default=None,
                        help="where to write artifacts "
                             "(default: $K0SNGIN_CACHE_DIR, else ~/.cache/k0sngin/render)")
    parser.add_argument("--top-level", type=pathlib.Path, default=None,
                        help="the served root, which cache paths are relative to "
                             "(default: $K0SNGIN_TOP_LEVEL)")
    parser.add_argument("--force", action="store_true",
                        help="re-render even files already cached")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be rendered, writing nothing")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="also report files that were skipped, and why")
    return parser.parse_args(args)


def documents(root: pathlib.Path):
    """Every file under `root`, following symlinked directories.

    Following links is required rather than incidental. `site/stories` is a
    symlink into another tree, and the server addresses documents beneath it as
    `stories/...` — so a crawl that skipped links would leave exactly those
    files permanently cold, which is the failure this script exists to prevent.

    Directories already visited are tracked by their real path, so a symlink
    loop terminates instead of walking forever.
    """
    seen = set()
    for directory, subdirectories, filenames in os.walk(root, followlinks=True):
        real = pathlib.Path(directory).resolve()
        if real in seen:
            # A link pointing back at somewhere we have been. Don't descend.
            subdirectories[:] = []
            continue
        seen.add(real)
        for filename in sorted(filenames):
            yield pathlib.Path(directory) / filename


def render_one(path: pathlib.Path, cache, top_level: pathlib.Path,
               force: bool, dry_run: bool) -> tuple:
    """Render `path` if it should be. Returns ``(outcome, detail)``."""
    # Containment is checked before the transformer cascade, not after. A file
    # outside the served root has no cascade to find, so asking first would
    # report it as "no /transformer glob matches" — true, useless, and hiding
    # the actual problem, which is usually a mistyped path or the wrong
    # --top-level.
    try:
        relative_source = path.relative_to(top_level)
    except ValueError:
        return FAILED, f"outside the served root ({top_level})"

    renderer, reason = resolve_renderer(path, top_level)
    if renderer is None:
        return SKIPPED, reason

    try:
        source = path.read_bytes()
    except OSError as error:
        return FAILED, str(error)

    artifact = cache.artifact_path(relative_source, renderer)
    digest = hashlib.sha256(source).hexdigest()
    if not force:
        # Ask the cache itself whether the entry matches this exact content,
        # rather than testing for the file's existence: an artifact left over
        # from an earlier version of the source is not a hit.
        if cache.read(artifact, digest) is not None:
            return WARM, str(artifact)

    if dry_run:
        return RENDERED, f"would render -> {artifact}"

    try:
        fragment = renderer.render(source)
    except Exception as error:  # a renderer is third-party code; keep going
        return FAILED, f"{type(error).__name__}: {error}"

    if not cache.write(artifact, digest, fragment):
        return FAILED, f"could not write {artifact}"
    return RENDERED, str(artifact)


def main(args=sys.argv[1:]):
    """CLI entry point."""
    options = parse_args(args)

    # The served root is passed down explicitly rather than set in the
    # environment: `TOP_LEVEL_DIR` is computed once at import, so an env var
    # set here would be ignored by an already-imported k0sngin and `--top-level`
    # would quietly do nothing.
    top_level = (options.top_level.expanduser().resolve()
                 if options.top_level is not None else TOP_LEVEL_DIR)
    cache = RenderCache(options.cache_dir.expanduser() if options.cache_dir else None)

    counts = {RENDERED: 0, WARM: 0, SKIPPED: 0, FAILED: 0}
    failures = []

    for given in options.paths:
        path = given.expanduser()
        if not path.exists():
            print(f"{FAILED}: {path}: no such file or directory", file=sys.stderr)
            counts[FAILED] += 1
            failures.append(path)
            continue

        candidates = documents(path) if path.is_dir() else [path]
        for candidate in candidates:
            outcome, detail = render_one(candidate, cache, top_level,
                                         options.force, options.dry_run)
            counts[outcome] += 1
            if outcome == FAILED:
                failures.append(candidate)
                print(f"{FAILED}: {candidate}: {detail}", file=sys.stderr)
            elif outcome == SKIPPED:
                if options.verbose:
                    print(f"{SKIPPED}: {candidate}: {detail}")
            elif outcome == RENDERED or options.verbose:
                print(f"{outcome}: {candidate}")

    summary = ", ".join(f"{counts[outcome]} {outcome}"
                        for outcome in (RENDERED, WARM, SKIPPED, FAILED))
    print(f"{'(dry run) ' if options.dry_run else ''}{summary}")

    # A failure is worth a non-zero exit — this runs unattended after a
    # publish, where nobody is reading the output unless something broke.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main() or 0)

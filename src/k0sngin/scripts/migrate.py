"""Write index.json beside index.ini.

    k0sngin-migrate ~/web/site                # say what would be written
    k0sngin-migrate --write ~/web/site        # write it
    k0sngin-migrate -v ~/web/site/portfolio   # also print the JSON

Nothing is written without ``--write``, and ``index.ini`` is never changed or
removed. A directory that already has an ``index.json`` is skipped unless
``--force`` is given, and an ``index.json`` that is not directory metadata is
never replaced. Symlinked directories are followed, because the server serves
through them.

The server reads ``index.json`` in preference to ``index.ini``, so writing
one changes what a directory serves immediately; the notes say where the two
will differ.
"""

import argparse
import os
import pathlib
import sys
import tempfile

from k0sngin.directory import collect_cascading_formatters
from k0sngin.index import INI, JSON, MetadataError, load_json, validate
from k0sngin.migrate import convert, dumps, missing_entries


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog="k0sngin-migrate",
        description="Convert index.ini files to index.json, beside them.")
    parser.add_argument("paths", nargs="+", metavar="PATH", type=pathlib.Path,
                        help="directories to crawl for index.ini files")
    parser.add_argument("--top-level", type=pathlib.Path, default=None,
                        help="the served root, where inheritance stops "
                             "(default: $K0SNGIN_TOP_LEVEL)")
    parser.add_argument("--write", action="store_true",
                        help="write the files (default: only report)")
    parser.add_argument("--force", action="store_true",
                        help="rewrite directories that already have an index.json")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print the JSON for each directory")
    return parser.parse_args(args)


def directories(root: pathlib.Path):
    """Every directory under `root` with an index.ini, following symlinked
    directories and visiting each real directory once."""
    seen = set()
    for directory, subdirectories, filenames in os.walk(root, followlinks=True):
        real = pathlib.Path(directory).resolve()
        if real in seen:
            subdirectories[:] = []
            continue
        seen.add(real)
        subdirectories.sort()
        if INI in filenames:
            yield pathlib.Path(directory)


def write_atomically(path: pathlib.Path, text: str) -> None:
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".index-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(temp, 0o666 & ~_umask())
        os.replace(temp, path)
    except BaseException:
        pathlib.Path(temp).unlink(missing_ok=True)
        raise


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def migrate(directory: pathlib.Path, top_level: pathlib.Path, *, write: bool,
            force: bool, verbose: bool) -> str:
    """Convert one directory. Returns "written", "would write", "skipped" or
    "failed", having reported why."""
    target = directory / JSON
    if target.exists():
        try:
            existing = load_json(target)
        except MetadataError:
            existing = {}   # meant as metadata, but broken: replaceable with --force
        if existing is None:
            print(f"skipped {target}: exists and is not directory metadata; "
                  f"this directory keeps its {INI}")
            return "skipped"
        if not force:
            print(f"skipped {target}: already there (--force rewrites it)")
            return "skipped"
    try:
        text = (directory / INI).read_text(encoding="utf-8")
        data, notes = convert(text, collect_cascading_formatters(directory, top_level))
        validate(data)
    except (OSError, ValueError) as exc:
        print(f"failed {directory / INI}: {exc}")
        return "failed"
    missing = missing_entries(data, directory)
    if missing:
        notes.append(f"{len(missing)} entries describe names not in the directory "
                     f"(kept): {', '.join(missing[:5])}{', …' if len(missing) > 5 else ''}")
    outcome = "written" if write else "would write"
    if write:
        write_atomically(target, dumps(data))
    print(f"{'wrote' if write else 'would write'} {target} "
          f"({len(data.get('entries', []))} entries)")
    for note in notes:
        print(f"    {note}")
    if verbose:
        print(dumps(data))
    return outcome


def main(args=None) -> int:
    options = parse_args(sys.argv[1:] if args is None else args)
    top_level = options.top_level or os.environ.get("K0SNGIN_TOP_LEVEL")
    if not top_level:
        print("k0sngin-migrate: give --top-level, or set K0SNGIN_TOP_LEVEL", file=sys.stderr)
        return 2
    top_level = pathlib.Path(top_level).expanduser().absolute()
    counts = {}
    for path in options.paths:
        path = path.expanduser().absolute()
        if not path.is_dir():
            print(f"k0sngin-migrate: {path} is not a directory", file=sys.stderr)
            return 2
        for directory in directories(path):
            outcome = migrate(directory, top_level, write=options.write,
                              force=options.force, verbose=options.verbose)
            counts[outcome] = counts.get(outcome, 0) + 1
    summary = ", ".join(f"{n} {outcome}" for outcome, n in sorted(counts.items())) or "nothing found"
    print(summary + ("" if options.write else ". Nothing was written; --write does it."))
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())

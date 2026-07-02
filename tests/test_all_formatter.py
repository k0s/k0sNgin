"""Tests for the `/all` index.ini directive (directory listing filter).

Spec (docs/formatters.md): `/all` controls which entries a directory lists —
absent = everything; empty = only files described in index.ini (that exist);
a comma-separated glob list = exactly the entries whose filename matches a glob.
`/all` is local to the directory (never inherited).

Each test builds a fresh directory under the served root at runtime (k0sNgin
reads the filesystem and index.ini per request) and checks which filenames the
rendered index links to.
"""

import pathlib


def _make_dir(site_root: pathlib.Path, name: str, files, ini=None) -> None:
    """Create <site_root>/<name>/ with the given files and optional index.ini."""
    d = site_root / name
    d.mkdir()
    for fname in files:
        (d / fname).write_text(f"{fname} body\n")
    if ini is not None:
        (d / "index.ini").write_text(ini)


def _linked(html: str, name: str) -> bool:
    """True if the rendered index links to `name` (default template uses href)."""
    return f'href="{name}"' in html


def test_all_absent_lists_everything(client, site_root):
    """With no /all line, every entry in the directory is listed."""
    _make_dir(site_root, "all_absent",
              ["a.txt", "b.png", "c.md"],
              ini="/title = Absent\na.txt = alpha\n")  # describes a.txt, no /all
    html = client.get("/all_absent/").text
    assert _linked(html, "a.txt")
    assert _linked(html, "b.png")
    assert _linked(html, "c.md")


def test_all_empty_lists_only_described(client, site_root):
    """`/all =` (empty) lists only the files described in index.ini."""
    _make_dir(site_root, "all_empty",
              ["a.txt", "b.png", "c.md"],
              ini="/all =\na.txt = alpha\nc.md = gamma\n")
    html = client.get("/all_empty/").text
    assert _linked(html, "a.txt")
    assert _linked(html, "c.md")
    assert not _linked(html, "b.png")   # not described -> hidden


def test_all_empty_skips_dangling_description(client, site_root):
    """`/all =` skips a described file that does not exist on disk (no dead link)."""
    _make_dir(site_root, "all_dangling",
              ["a.txt"],
              ini="/all =\na.txt = alpha\nghost.md = nope\n")
    html = client.get("/all_dangling/").text
    assert _linked(html, "a.txt")
    assert not _linked(html, "ghost.md")


def test_all_globs_list_matching_only(client, site_root):
    """A glob list renders exactly the entries matching any glob; whitespace is
    insignificant and a described non-match is still hidden."""
    _make_dir(site_root, "all_globs",
              ["a.txt", "d.txt", "b.png", "c.md"],
              ini="/all = *.txt, *.png\na.txt = alpha\nc.md = described-but-no-match\n")
    html = client.get("/all_globs/").text
    assert _linked(html, "a.txt")
    assert _linked(html, "d.txt")   # matches *.txt though undescribed
    assert _linked(html, "b.png")
    assert not _linked(html, "c.md")  # described, but matches no glob -> hidden


def test_all_glob_exact_filename(client, site_root):
    """A bare filename works as a glob (matches just that file)."""
    _make_dir(site_root, "all_exact",
              ["hello.md", "a.txt", "b.png"],
              ini="/all = hello.md\n")
    html = client.get("/all_exact/").text
    assert _linked(html, "hello.md")
    assert not _linked(html, "a.txt")
    assert not _linked(html, "b.png")

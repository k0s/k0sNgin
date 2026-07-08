"""Tests for the `/ignore` index.ini directive (listing subtraction filter).

Spec (docs/formatters.md): `/ignore` is a comma-separated glob list — the same
syntax and parsing as `/all` — naming entries to hide from the directory
listing. It is processed **after** `/all` (`/all` selects the displayed set,
`/ignore` subtracts from it) and **cascades**: a parent's globs apply to
descendants, a descendant's own `/ignore` overrides wholesale, and a bare
`/ignore =` clears inherited globs. Ignored files are only hidden from the
listing — they remain directly fetchable by URL.
"""

import pathlib


def _make_dir(site_root: pathlib.Path, name: str, files, ini=None, child_ini=None) -> pathlib.Path:
    """Create <site_root>/<name>/ (and child/ mirroring `files`) with inis."""
    d = site_root / name
    d.mkdir()
    child = d / "child"
    child.mkdir()
    for fname in files:
        (d / fname).write_text(f"{fname} body\n")
        (child / fname).write_text(f"{fname} body\n")
    if ini is not None:
        (d / "index.ini").write_text(ini)
    if child_ini is not None:
        (child / "index.ini").write_text(child_ini)
    return d


def _linked(html: str, name: str) -> bool:
    return f'href="{name}"' in html


def test_ignore_hides_matching_entries(client, site_root):
    """Globs hide matching names; everything else still lists."""
    _make_dir(site_root, "ign_basic",
              ["a.txt", "b.png", ".hidden", "keep.md"],
              ini="/ignore = *.txt, .*, index.ini\n")
    html = client.get("/ign_basic/").text
    assert not _linked(html, "a.txt")
    assert not _linked(html, ".hidden")
    assert not _linked(html, "index.ini")
    assert _linked(html, "b.png")
    assert _linked(html, "keep.md")


def test_ignore_cascades(client, site_root):
    """A parent's /ignore applies to descendant listings."""
    _make_dir(site_root, "ign_cascade",
              ["a.txt", "b.png"],
              ini="/ignore = *.txt\n")
    html = client.get("/ign_cascade/child/").text
    assert not _linked(html, "a.txt")
    assert _linked(html, "b.png")


def test_ignore_child_clears_with_empty_value(client, site_root):
    """A bare `/ignore =` in a child clears the inherited globs."""
    _make_dir(site_root, "ign_clear",
              ["a.txt", "b.png"],
              ini="/ignore = *.txt\n",
              child_ini="/ignore =\n")
    html = client.get("/ign_clear/child/").text
    assert _linked(html, "a.txt")
    assert _linked(html, "b.png")


def test_ignore_processed_after_all(client, site_root):
    """/all selects the displayed set; /ignore subtracts from it."""
    _make_dir(site_root, "ign_after_all",
              ["a.txt", "b.md", "c.png"],
              ini="/all = *.txt, *.md\n/ignore = *.md\n")
    html = client.get("/ign_after_all/").text
    assert _linked(html, "a.txt")
    assert not _linked(html, "b.md")    # selected by /all, removed by /ignore
    assert not _linked(html, "c.png")   # never selected by /all


def test_ignored_files_remain_fetchable(client, site_root):
    """/ignore hides from the listing only; the file still serves."""
    _make_dir(site_root, "ign_fetch",
              ["a.txt"],
              ini="/ignore = *.txt\n")
    assert not _linked(client.get("/ign_fetch/").text, "a.txt")
    response = client.get("/ign_fetch/a.txt")
    assert response.status_code == 200
    assert "a.txt body" in response.text

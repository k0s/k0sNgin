"""Tests for the `/include` formatter (raw HTML fragment at the top of the body).

Spec (docs/formatters.md): `/include = <file>` inserts the named file's
contents verbatim above the page navigation and listing. It cascades; the
file is resolved by walking up from the rendered directory to the served
root (first hit wins, so a subtree can override with its own copy). Only
relative paths inside the served tree resolve; missing or out-of-tree
fragments are skipped, never an error.
"""

import pathlib

HEADER = '<div id="sitenav"><a href="/">home</a></div>'
OVERRIDE = '<div id="sitenav-override">local nav</div>'


def _make_tree(site_root: pathlib.Path, name: str, ini) -> pathlib.Path:
    """Create <site_root>/<name>/{hello.txt,index.ini} and an empty child/."""
    d = site_root / name
    d.mkdir()
    (d / "hello.txt").write_text("hello\n")
    (d / "index.ini").write_text(ini)
    child = d / "child"
    child.mkdir()
    (child / "nested.txt").write_text("nested\n")
    return d


def test_include_renders_raw_html(client, site_root):
    """The fragment is inserted verbatim (not escaped), before the listing."""
    d = _make_tree(site_root, "inc_basic", ini="/include = header.html\n")
    (d / "header.html").write_text(HEADER)
    html = client.get("/inc_basic/").text
    assert HEADER in html
    assert html.index(HEADER) < html.index("file-list")


def test_include_cascades_with_walk_up_resolution(client, site_root):
    """A child inherits the directive and finds the ancestor's fragment."""
    d = _make_tree(site_root, "inc_cascade", ini="/include = header.html\n")
    (d / "header.html").write_text(HEADER)
    html = client.get("/inc_cascade/child/").text
    assert HEADER in html


def test_include_subtree_override(client, site_root):
    """A subtree's own copy of the fragment wins over an ancestor's."""
    d = _make_tree(site_root, "inc_override", ini="/include = header.html\n")
    (d / "header.html").write_text(HEADER)
    (d / "child" / "header.html").write_text(OVERRIDE)
    html = client.get("/inc_override/child/").text
    assert OVERRIDE in html
    assert HEADER not in html


def test_include_missing_file_is_skipped(client, site_root):
    """A fragment that doesn't exist anywhere is skipped, not an error."""
    _make_tree(site_root, "inc_missing", ini="/include = nope.html\n")
    response = client.get("/inc_missing/")
    assert response.status_code == 200
    assert "file-list" in response.text


def test_include_traversal_rejected(client, site_root):
    """Absolute paths and .. never resolve (secret.txt sits above the root)."""
    for i, value in enumerate(["../secret.txt", "/etc/hostname"]):
        _make_tree(site_root, f"inc_traversal_{i}", ini=f"/include = {value}\n")
        response = client.get(f"/inc_traversal_{i}/")
        assert response.status_code == 200
        assert "TOP SECRET" not in response.text


def test_include_appears_on_gallery_pages(client, site_root):
    """base.html hosts the fragment, so gallery templates show it too."""
    d = _make_tree(site_root, "inc_gallery",
                   ini="/include = header.html\n/images =\n/template = strip.html\n")
    (d / "header.html").write_text(HEADER)
    (d / "a.jpg").write_bytes(b"stub")
    html = client.get("/inc_gallery/").text
    assert HEADER in html
    assert "gallery-strip" in html

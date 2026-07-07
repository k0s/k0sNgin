"""Tests for parent-index navigation and the `/breadcrumbs` formatter.

Spec (docs/formatters.md): every directory index except the root links to the
index above it (a `.parent-nav` line rendered by base.html, so all built-in
templates get it). The cascading `/breadcrumbs` directive upgrades that line
to a full linked trail (`/ » pictures » gallery`, current directory unlinked);
a descendant opts out with `/breadcrumbs = off`. The root never shows either.
"""

import pathlib


def _make_tree(site_root: pathlib.Path, name: str, ini=None, child_ini=None) -> pathlib.Path:
    """Create <site_root>/<name>/child/ with optional index.ini at each level."""
    d = site_root / name
    d.mkdir()
    (d / "hello.txt").write_text("hello\n")
    if ini is not None:
        (d / "index.ini").write_text(ini)
    child = d / "child"
    child.mkdir()
    (child / "nested.txt").write_text("nested\n")
    if child_ini is not None:
        (child / "index.ini").write_text(child_ini)
    return d


def test_root_has_no_parent_nav(client):
    """The root index has nothing above it."""
    html = client.get("/").text
    assert "parent-nav" not in html
    assert "breadcrumbs" not in html


def test_subdirectory_links_to_parent(client, site_root):
    """A directory index links to the index above it."""
    _make_tree(site_root, "nav_parent")
    html = client.get("/nav_parent/").text
    assert '<nav class="parent-nav"><a href="/">../</a></nav>' in html
    nested = client.get("/nav_parent/child/").text
    assert '<nav class="parent-nav"><a href="/nav_parent/">../</a></nav>' in nested


def test_gallery_templates_get_parent_nav(client, site_root):
    """The parent link comes from base.html, so gallery templates have it too."""
    d = site_root / "nav_gallery"
    d.mkdir()
    (d / "a.jpg").write_bytes(b"stub")
    (d / "index.ini").write_text("/images =\n/template = strip.html\n")
    html = client.get("/nav_gallery/").text
    assert 'class="parent-nav"' in html
    assert "gallery-strip" in html


def test_breadcrumbs_replace_parent_nav(client, site_root):
    """/breadcrumbs renders a linked trail; the plain parent link goes away."""
    _make_tree(site_root, "nav_crumbs", ini="/breadcrumbs =\n")
    html = client.get("/nav_crumbs/").text
    assert 'class="breadcrumbs"' in html
    assert 'class="parent-nav"' not in html
    assert '<a href="/">/</a>' in html
    assert "nav_crumbs" in html                       # current dir, shown...
    assert '<a href="/nav_crumbs/">' not in html      # ...but not linked


def test_breadcrumbs_cascade_and_link_ancestors(client, site_root):
    """/breadcrumbs is inherited by descendants, which link every ancestor."""
    _make_tree(site_root, "nav_cascade", ini="/breadcrumbs =\n")
    html = client.get("/nav_cascade/child/").text
    assert 'class="breadcrumbs"' in html
    assert '<a href="/">/</a>' in html
    assert '<a href="/nav_cascade/">nav_cascade</a>' in html
    assert '<a href="/nav_cascade/child/">' not in html   # current dir unlinked


def test_breadcrumbs_off_in_child(client, site_root):
    """A descendant opts out with `/breadcrumbs = off` (parent link returns)."""
    _make_tree(site_root, "nav_off",
               ini="/breadcrumbs =\n",
               child_ini="/breadcrumbs = off\n")
    html = client.get("/nav_off/child/").text
    assert 'class="breadcrumbs"' not in html
    assert '<nav class="parent-nav"><a href="/nav_off/">../</a></nav>' in html

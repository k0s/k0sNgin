"""Tests for the `/template` index.ini directive (page template selection).

Spec (docs/formatters.md): `/template` selects one of k0sNgin's built-in page
templates by bare filename (strip.html, grid.html, sequence.html,
background.html, index.html). It is local to its directory, takes precedence
over a local index.html file, and never loads templates from the content tree
— names with path separators or unknown names fall back to the default.
"""

import pathlib
import re


def _make_gallery(site_root: pathlib.Path, name: str, ini, descriptions=None) -> pathlib.Path:
    """Create <site_root>/<name>/ with three stub images and an index.ini."""
    d = site_root / name
    d.mkdir()
    for fname in ["a.jpg", "b.jpg", "c.jpg"]:
        (d / fname).write_bytes(b"not really an image")
    (d / "index.ini").write_text(ini)
    return d


def test_each_gallery_template_renders(client, site_root):
    """All four gallery templates are selectable and distinguishable."""
    for template in ["strip", "grid", "sequence", "background"]:
        _make_gallery(site_root, f"tpl_{template}",
                      ini=f"/images = size=100x\n/template = {template}.html\n")
        html = client.get(f"/tpl_{template}/").text
        assert f"gallery-{template}" in html


def test_unknown_template_falls_back(client, site_root):
    """An unknown template name falls back to the default listing."""
    _make_gallery(site_root, "tpl_unknown",
                  ini="/template = nonexistent.html\n")
    response = client.get("/tpl_unknown/")
    assert response.status_code == 200
    assert "file-list" in response.text


def test_template_traversal_rejected(client, site_root):
    """Names with path separators never escape the built-in templates dir."""
    for i, name in enumerate(["../templates/strip.html",
                              "subdir/evil.html",
                              "/etc/passwd"]):
        _make_gallery(site_root, f"tpl_traversal_{i}",
                      ini=f"/template = {name}\n")
        response = client.get(f"/tpl_traversal_{i}/")
        assert response.status_code == 200
        assert "file-list" in response.text  # default template used


def test_explicit_template_beats_local_index_html(client, site_root):
    """An explicit /template wins over a local index.html file."""
    d = _make_gallery(site_root, "tpl_beats_local",
                      ini="/images =\n/template = strip.html\n")
    (d / "index.html").write_text("LOCAL OVERRIDE")
    html = client.get("/tpl_beats_local/").text
    assert "gallery-strip" in html
    assert "LOCAL OVERRIDE" not in html


def test_local_index_html_still_wins_without_template(client, site_root):
    """Without /template, the existing local index.html override still applies."""
    d = _make_gallery(site_root, "tpl_local_default",
                      ini="/images =\n")
    (d / "index.html").write_text("LOCAL OVERRIDE")
    html = client.get("/tpl_local_default/").text
    assert "LOCAL OVERRIDE" in html


def test_sequence_navigation(client, site_root):
    """sequence.html shows one image per page with prev/next links."""
    _make_gallery(site_root, "tpl_seq_nav",
                  ini="/images =\n/template = sequence.html\n"
                      "a.jpg = alpha\nb.jpg = beta\nc.jpg = gamma\n")

    first = client.get("/tpl_seq_nav/").text
    assert 'src="a.jpg"' in first
    assert 'src="b.jpg"' not in first
    assert '"?index=1"' in first and "beta" in first   # next
    assert '"?index=-1"' not in first                   # no prev at start

    middle = client.get("/tpl_seq_nav/?index=1").text
    assert 'src="b.jpg"' in middle
    assert '"?index=0"' in middle and "alpha" in middle
    assert '"?index=2"' in middle and "gamma" in middle

    last = client.get("/tpl_seq_nav/?index=2").text
    assert 'src="c.jpg"' in last
    assert '"?index=3"' not in last                     # no next at end

    out_of_range = client.get("/tpl_seq_nav/?index=99").text
    assert "<img" not in out_of_range


def test_background_image_selection(client, site_root):
    """background.html uses the first image, or a valid ?image= selection."""
    _make_gallery(site_root, "tpl_bg",
                  ini="/images =\n/template = background.html\n"
                      "a.jpg = alpha\nb.jpg = beta\nc.jpg = gamma\n")

    default = client.get("/tpl_bg/").text
    assert "url('a.jpg')" in default

    selected = client.get("/tpl_bg/?image=b.jpg").text
    assert "url('b.jpg')" in selected

    bogus = client.get("/tpl_bg/?image=nope.jpg").text
    assert "url('a.jpg')" in bogus


def test_sequence_index_by_filename(client, site_root):
    """sequence.html accepts ?index=<filename> as an alias for its position."""
    _make_gallery(site_root, "tpl_seq_name",
                  ini="/images =\n/template = sequence.html\n")
    seen = set()
    for position in range(3):
        by_position = client.get(f"/tpl_seq_name/?index={position}").text
        name = re.search(r'<div class="image" id="([^"]+)">', by_position).group(1)
        seen.add(name)
        assert client.get(f"/tpl_seq_name/?index={name}").text == by_position
    assert seen == {"a.jpg", "b.jpg", "c.jpg"}

    missing = client.get("/tpl_seq_name/?index=nope.jpg").text
    assert 'class="gallery gallery-sequence"' not in missing


def test_sequence_numeric_index_beats_filename(client, site_root):
    """A numeric ?index= is a position even when a file has that name."""
    d = site_root / "tpl_seq_numeric"
    d.mkdir()
    for fname in ["5", "a", "b"]:
        (d / fname).write_bytes(b"stub")
    (d / "index.ini").write_text("/template = sequence.html\n")
    # position 5 is out of range, so nothing renders -- not the file named "5"
    html = client.get("/tpl_seq_numeric/?index=5").text
    assert 'class="gallery gallery-sequence"' not in html
    assert 'href="5"' not in html

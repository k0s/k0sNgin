"""Tests for the `/images` gallery formatter (ported from montage).

Spec (docs/formatters.md): `/images` restricts a directory listing to image
files and prepares them for gallery display — `size=WxH` maps to the rendered
``<img>`` width/height (either side optional), `columns` feeds the grid
template, and the `thumbnails` flag points ``<img>`` at an existing
``thumbs/thumb_<name>`` file. Thumbnails are *used* when present on disk but
never generated. `/images` is local to its directory (never inherited).

Image files here are name-only stubs: the formatter guesses mimetypes from
the file name and never opens the pixels.
"""

import pathlib


def _make_gallery(site_root: pathlib.Path, name: str, files, ini) -> pathlib.Path:
    """Create <site_root>/<name>/ with the given files and index.ini."""
    d = site_root / name
    d.mkdir()
    for fname in files:
        (d / fname).write_bytes(b"not really an image")
    (d / "index.ini").write_text(ini)
    return d


def test_images_filters_non_images(client, site_root):
    """Only image-mimetype entries survive; text files and subdirs are dropped."""
    d = _make_gallery(site_root, "img_filter",
                      ["a.jpg", "b.png", "notes.txt"],
                      ini="/images =\n/template = strip.html\n")
    (d / "subdir").mkdir()
    html = client.get("/img_filter/").text
    assert 'src="a.jpg"' in html
    assert 'src="b.png"' in html
    assert "notes.txt" not in html
    assert "subdir" not in html
    assert "index.ini" not in html


def test_size_width_only(client, site_root):
    """`size=400x` sets width and leaves height off."""
    _make_gallery(site_root, "img_width",
                  ["a.jpg"],
                  ini="/images = size=400x\n/template = strip.html\n")
    html = client.get("/img_width/").text
    assert 'src="a.jpg" width="400" alt=' in html


def test_size_height_only(client, site_root):
    """`size=x550` sets height and leaves width off."""
    _make_gallery(site_root, "img_height",
                  ["a.jpg"],
                  ini="/images = size=x550\n/template = strip.html\n")
    html = client.get("/img_height/").text
    assert 'src="a.jpg" height="550" alt=' in html


def test_size_both(client, site_root):
    """`size=160x160` sets both dimensions."""
    _make_gallery(site_root, "img_both",
                  ["a.jpg"],
                  ini="/images = size=160x160\n/template = strip.html\n")
    html = client.get("/img_both/").text
    assert 'src="a.jpg" width="160" height="160" alt=' in html


def test_size_absent(client, site_root):
    """Empty `/images` renders images at natural size."""
    _make_gallery(site_root, "img_nosize",
                  ["a.jpg"],
                  ini="/images =\n/template = strip.html\n")
    html = client.get("/img_nosize/").text
    assert 'src="a.jpg" alt=' in html   # no width/height attrs before alt
    assert 'width="' not in html
    assert 'height="' not in html


def test_columns_explicit(client, site_root):
    """`columns=4` reaches the grid template."""
    _make_gallery(site_root, "img_columns",
                  ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"],
                  ini="/images = thumbnails,size=150x,columns=4\n/template = grid.html\n")
    html = client.get("/img_columns/").text
    assert "repeat(4, auto)" in html


def test_columns_default_is_image_count(client, site_root):
    """Without `columns`, the grid defaults to one row (columns = image count)."""
    _make_gallery(site_root, "img_columns_default",
                  ["a.jpg", "b.jpg", "c.jpg"],
                  ini="/images =\n/template = grid.html\n")
    html = client.get("/img_columns_default/").text
    assert "repeat(3, auto)" in html


def test_thumbnails_use_existing(client, site_root):
    """With the `thumbnails` flag, an existing thumbs/thumb_<name> becomes the
    <img> src while the link still targets the full image; a missing thumbnail
    falls back to the full image (never generated)."""
    d = _make_gallery(site_root, "img_thumbs",
                      ["a.jpg", "b.jpg"],
                      ini="/images = thumbnails, size=150x\n/template = strip.html\n")
    thumbs = d / "thumbs"
    thumbs.mkdir()
    (thumbs / "thumb_a.jpg").write_bytes(b"thumb stub")
    html = client.get("/img_thumbs/").text
    assert 'href="a.jpg"' in html
    assert 'src="thumbs/thumb_a.jpg"' in html
    assert 'src="b.jpg"' in html          # no thumb on disk -> full image
    assert "thumb_b.jpg" not in html      # ...and nothing was generated
    assert not (thumbs / "thumb_b.jpg").exists()


def test_empty_thumbnail_counts_as_missing(client, site_root):
    """A zero-byte thumbnail (montage's old failed-write leftovers) is
    skipped in favor of the full image — it would serve 200 but render as a
    broken tile."""
    d = _make_gallery(site_root, "img_empty_thumb",
                      ["a.jpg"],
                      ini="/images = thumbnails, size=150x\n/template = strip.html\n")
    thumbs = d / "thumbs"
    thumbs.mkdir()
    (thumbs / "thumb_a.jpg").write_bytes(b"")
    html = client.get("/img_empty_thumb/").text
    assert 'src="a.jpg"' in html
    assert 'src="thumbs/thumb_a.jpg"' not in html


def test_images_is_local_only(client, site_root):
    """A parent's /images (and /template) do not cascade into children."""
    d = _make_gallery(site_root, "img_local",
                      ["a.jpg"],
                      ini="/images = size=400x\n/template = strip.html\n")
    child = d / "child"
    child.mkdir()
    (child / "notes.txt").write_text("notes body\n")
    html = client.get("/img_local/child/").text
    assert 'href="notes.txt"' in html      # not filtered out by /images
    assert "gallery-strip" not in html     # not rendered by parent's /template

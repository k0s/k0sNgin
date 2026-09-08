"""Extension-based rendering: the ``/transformer`` directive.

Covers which files get transformed (directive resolution and inheritance) and
what a transformed file is served as. The cache behind it is exercised
separately in ``test_render_cache.py``.

The guiding property throughout: every way of *not* transforming a file — no
directive, no matching glob, inheritance cleared, a Content-Type target, an
unknown renderer — serves the file exactly as k0sNgin did before this feature
existed. Rendering is opt-in and never fails a request.
"""


def test_markdown_renders_to_html(client):
    """A .md file under a /transformer directive is served as HTML."""
    r = client.get("/documents/notes.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<h1>Notes on Deployment</h1>" in r.text


def test_github_flavored_extensions_render(client):
    """Tables, strikethrough and task lists — the GFM part of GFM."""
    html = client.get("/documents/notes.md").text
    assert "<table>" in html
    assert "<del>struck</del>" in html
    assert '<input type="checkbox"' in html


def test_raw_html_is_stripped(client):
    """Embedded raw HTML is dropped, not passed through.

    The site's CSP forbids inline scripts, so a renderer that emitted them
    would only produce markup the browser refuses to run.
    """
    html = client.get("/documents/notes.md").text
    assert "<script>" not in html
    assert "raw HTML omitted" in html


def test_title_comes_from_the_first_heading(client):
    """A document names its own page."""
    assert "<title>Notes on Deployment</title>" in client.get("/documents/notes.md").text


def test_document_wears_the_directory_chrome(client):
    """A rendered document inherits its directory's stylesheets and favicon."""
    html = client.get("/documents/notes.md").text
    assert "/documents.css" in html
    assert "/documents.ico" in html


def test_parent_link_points_at_the_containing_directory(client):
    """The `../` link goes to the directory holding the file, not above it."""
    assert 'href="/documents/"' in client.get("/documents/notes.md").text


def test_transformer_cascades_to_subdirectories(client):
    """A directory with no index.ini inherits the directive from above."""
    r = client.get("/documents/plain/inner.md")
    assert r.status_code == 200
    assert "<h1>Inner</h1>" in r.text


def test_descendant_css_overrides_ancestor(client):
    """A descendant's cascading formatter beats its ancestor's.

    Regression test: the cascade walk previously let the *root* overwrite what
    a nested directory declared, which is backwards from the documented
    semantics and would have made subtree overrides of /transformer useless.
    """
    html = client.get("/documents/nested/deep.md").text
    assert "<h1>Deep</h1>" in html
    assert "/nested.css" in html
    assert "/documents.css" not in html


def test_bare_transformer_stops_inheritance(client):
    """`/transformer =` opts a subtree back out of rendering."""
    r = client.get("/documents/opaque/off.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text == "# Off\n\nnot rendered\n"


def test_content_type_target_is_not_rendered(client):
    """decoupage's `glob=type/subtype` form names a MIME type, not a renderer."""
    r = client.get("/documents/typed/typed.md")
    assert r.status_code == 200
    assert "<h1>" not in r.text


def test_unknown_renderer_serves_the_source(client):
    """A renderer that doesn't exist degrades to serving the file."""
    r = client.get("/documents/unknown/mystery.md")
    assert r.status_code == 200
    assert r.text == "# Mystery\n\nnot rendered\n"


def test_markdown_without_a_directive_is_untouched(client):
    """Rendering is opt-in: no directive, no transformation."""
    r = client.get("/untouched.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text == "# Untouched\n\nplain source\n"


def test_format_raw_bypasses_rendering(client):
    """`?format=raw` serves the source, as it did in decoupage."""
    r = client.get("/documents/notes.md?format=raw")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# Notes on Deployment")


def test_oversized_files_are_served_as_source(client, site_root, monkeypatch):
    """A file too large to render is served rather than read into memory."""
    from k0sngin import main
    monkeypatch.setattr(main, "MAX_RENDER_BYTES", 4)
    r = client.get("/documents/notes.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")


def test_head_request_returns_html_headers_without_a_body(client):
    """HEAD on a rendered document answers like the GET, minus the body."""
    r = client.head("/documents/notes.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.text == ""


def test_etag_round_trip_yields_304(client):
    """A client holding the current render is told it is current."""
    first = client.get("/documents/notes.md")
    etag = first.headers["etag"]
    second = client.get("/documents/notes.md", headers={"if-none-match": etag})
    assert second.status_code == 304


def test_if_modified_since_does_not_short_circuit(client):
    """Documents honour If-None-Match only.

    The rendered page can change while the source file's mtime does not — a
    renderer upgrade, a CSS cascade edit — so a timestamp is not evidence the
    client's copy is current.
    """
    import email.utils
    import time

    future = email.utils.formatdate(time.time() + 3600, usegmt=True)
    r = client.get("/documents/notes.md", headers={"if-modified-since": future})
    assert r.status_code == 200


def test_etag_changes_when_the_source_changes(client, site_root):
    """Editing a document invalidates the client's copy of it."""
    document = site_root / "documents" / "mutable.md"
    document.write_text("# One\n")
    first = client.get("/documents/mutable.md")
    assert "<h1>One</h1>" in first.text

    document.write_text("# Two\n")
    second = client.get("/documents/mutable.md")
    assert "<h1>Two</h1>" in second.text
    assert second.headers["etag"] != first.headers["etag"]

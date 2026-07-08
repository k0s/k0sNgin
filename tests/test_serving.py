"""End-to-end tests for k0sNgin's HTTP serving behavior.

Covers the two highest-risk paths for a public fileserver — the path-traversal
guard and directory-index rendering — plus the file-serving contract and the
security/rate-limit middleware. Each test states the behavior it pins.

Rate-limit isolation: conftest raises the shared app's limit (via
``K0SNGIN_RATE_LIMIT``) so the growing suite never trips it; the 429 behavior
is pinned against a dedicated app instance with a tiny limit instead.
"""


def test_serves_file_inline(client):
    """A file under the top level is returned verbatim, inline, with its type."""
    r = client.get("/hello.txt")
    assert r.status_code == 200
    assert r.text == "hello world\n"
    assert r.headers["content-type"].startswith("text/plain")
    # Content-Disposition is inline (viewed in-browser), not an attachment.
    assert r.headers["content-disposition"] == 'inline; filename="hello.txt"'


def test_security_headers_and_commit_present(client):
    """Every response carries the security headers and the served-build header."""
    r = client.get("/hello.txt")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers
    # X-K0sNgin-Commit identifies the running build; must be present and non-empty.
    assert r.headers.get("x-k0sngin-commit")


def test_missing_file_returns_404(client):
    """A nonexistent path returns 404 (not 403), avoiding info disclosure."""
    assert client.get("/does-not-exist.txt").status_code == 404


def test_path_traversal_is_blocked(client):
    """An encoded ``../`` escape to a real file outside the root returns 404.

    ``secret.txt`` exists on disk one level above the served root; the guard must
    refuse it. The URL is percent-encoded so the HTTP client can't normalize the
    dot-segments away before they reach the app.
    """
    r = client.get("/%2e%2e%2fsecret.txt")
    assert r.status_code == 404
    assert "TOP SECRET" not in r.text


def test_directory_index_renders_metadata(client):
    """A directory renders an index listing its files, using index.ini metadata.

    The link text is the per-file title (from the ``name = title : description``
    split), the link target is the filename, and the description renders
    separately.
    """
    r = client.get("/docs/")
    assert r.status_code == 200
    assert 'href="readme.txt"' in r.text   # link target is the filename
    assert ">the readme</a>" in r.text     # link text is the per-file title
    assert "Docs" in r.text                # /title from index.ini
    assert "a description" in r.text       # split-off description still shown


def test_colonless_description_is_link_text(client):
    """A description without a ``:`` becomes the link text and is not repeated.

    The title formatter must only split descriptions that contain the
    separator; a plain ``name = description`` line displays the same with
    and without /title, and the description is not duplicated in a
    separate description element.
    """
    r = client.get("/docs/")
    assert r.status_code == 200
    assert 'href="notes.txt"' in r.text
    assert ">just some notes</a>" in r.text
    assert r.text.count("just some notes") == 1


def test_alternate_form_links(client):
    """``; [text]=target`` renders extra links to alternate forms of a resource.

    ``report.html = The Report; [PDF]=report.pdf`` shows one entry titled
    "The Report" linking to report.html, followed by a [PDF] link to
    report.pdf; the link segment does not leak into the displayed text.
    """
    r = client.get("/docs/")
    assert r.status_code == 200
    assert ">The Report</a>" in r.text
    assert '[<a href="report.pdf" class="file-alt-link">PDF</a>]' in r.text
    assert "[PDF]=report.pdf" not in r.text


def test_links_extracted_before_title_split(client):
    """Link segments are stripped before the title formatter splits on ':'.

    ``paper.txt = A Paper : with details; [PDF]=paper.pdf`` yields title
    "A Paper", description "with details", and a [PDF] alternate link.
    """
    r = client.get("/docs/")
    assert ">A Paper</a>" in r.text
    assert "with details" in r.text
    assert '[<a href="paper.pdf" class="file-alt-link">PDF</a>]' in r.text
    assert "[PDF]=paper.pdf" not in r.text


def test_undescribed_file_falls_back_to_filename(client):
    """A file with no index.ini description uses its filename as link text."""
    r = client.get("/")
    assert r.status_code == 200
    assert ">hello.txt</a>" in r.text


def test_directory_without_trailing_slash_redirects(client):
    """A directory URL without a trailing slash 301-redirects to the slash form."""
    r = client.get("/docs", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].endswith("/docs/")


def test_root_directory_is_served(client):
    """The root path lists the top-level directory without redirecting."""
    r = client.get("/")
    assert r.status_code == 200
    assert "hello.txt" in r.text


def test_rate_limit_returns_429_when_exceeded():
    """Exceeding the per-IP limit within a minute yields 429 with Retry-After."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from k0sngin.main import RateLimitMiddleware

    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, requests_per_minute=3)
    limited = TestClient(app)
    for _ in range(3):
        assert limited.get("/ping").status_code == 200
    blocked = limited.get("/ping")
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")

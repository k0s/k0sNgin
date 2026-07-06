"""End-to-end tests for k0sNgin's HTTP serving behavior.

Covers the two highest-risk paths for a public fileserver — the path-traversal
guard and directory-index rendering — plus the file-serving contract and the
security/rate-limit middleware. Each test states the behavior it pins.

Rate-limit isolation: the limiter keys on the first ``X-Forwarded-For`` value
(``main.py``), so tests that could exhaust a bucket send a unique ``X-Forwarded-For``
to get their own counter and avoid interfering with each other.
"""

# Keep in sync with the value passed to RateLimitMiddleware in k0sngin/main.py.
RATE_LIMIT_PER_MINUTE = 60


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


def test_rate_limit_returns_429_when_exceeded(client):
    """Exceeding the per-IP limit within a minute yields 429 with Retry-After."""
    headers = {"x-forwarded-for": "203.0.113.7"}  # dedicated bucket for this test
    for _ in range(RATE_LIMIT_PER_MINUTE):
        assert client.get("/hello.txt", headers=headers).status_code == 200
    blocked = client.get("/hello.txt", headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")

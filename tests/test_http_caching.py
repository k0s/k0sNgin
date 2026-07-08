"""Tests for HTTP caching: conditional requests, Cache-Control, and HEAD.

Spec: file responses carry an ETag (Starlette's mtime-size formula) and
Last-Modified, and the server honors ``If-None-Match``/``If-Modified-Since``
with a bodyless 304. Cache-Control policy: media/static content types get
``public, max-age=<K0SNGIN_MEDIA_MAX_AGE>`` (default 1 day); everything else —
including the dynamic directory indexes — gets ``no-cache`` (store but always
revalidate). HEAD is supported and returns headers only.
"""


def test_file_response_carries_validators(client):
    """File GETs include ETag and Last-Modified."""
    r = client.get("/hello.txt")
    assert r.status_code == 200
    assert r.headers.get("etag")
    assert r.headers.get("last-modified")


def test_if_none_match_returns_304(client):
    """A matching If-None-Match yields a bodyless 304 with the validators."""
    etag = client.get("/hello.txt").headers["etag"]
    r = client.get("/hello.txt", headers={"if-none-match": etag})
    assert r.status_code == 304
    assert r.content == b""
    assert r.headers["etag"] == etag
    assert "cache-control" in r.headers


def test_stale_etag_returns_full_response(client):
    """A non-matching If-None-Match yields the full 200."""
    r = client.get("/hello.txt", headers={"if-none-match": '"deadbeef"'})
    assert r.status_code == 200
    assert r.text == "hello world\n"


def test_if_modified_since_returns_304(client):
    """If-Modified-Since with the served Last-Modified yields 304."""
    last_modified = client.get("/hello.txt").headers["last-modified"]
    r = client.get("/hello.txt", headers={"if-modified-since": last_modified})
    assert r.status_code == 304


def test_if_modified_since_old_date_returns_200(client):
    """A stale If-Modified-Since yields the full response."""
    r = client.get("/hello.txt",
                   headers={"if-modified-since": "Mon, 01 Jan 1990 00:00:00 GMT"})
    assert r.status_code == 200


def test_media_gets_long_lived_cache_control(client, site_root):
    """Image responses are cacheable without revalidation (max-age)."""
    (site_root / "cache_probe.png").write_bytes(b"png stub")
    r = client.get("/cache_probe.png")
    assert r.headers["cache-control"].startswith("public, max-age=")


def test_text_gets_no_cache(client):
    """Non-media files must revalidate every time."""
    r = client.get("/hello.txt")
    assert r.headers["cache-control"] == "no-cache"


def test_directory_index_gets_no_cache(client):
    """Dynamic directory indexes must revalidate (index.ini edits show up)."""
    r = client.get("/docs/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_head_file(client):
    """HEAD on a file returns the GET headers and no body."""
    r = client.head("/hello.txt")
    assert r.status_code == 200
    assert r.headers.get("etag")
    assert r.content == b""


def test_head_directory(client):
    """HEAD on a directory index succeeds (no 405)."""
    r = client.head("/docs/")
    assert r.status_code == 200

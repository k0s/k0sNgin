"""The /_k0sngin/ route: files shipped inside the package, nothing else."""


def test_serves_player_script(client):
    response = client.get("/_k0sngin/playlist.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "playlist" in response.text


def test_serves_player_styles(client):
    response = client.get("/_k0sngin/playlist.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_unknown_name_is_404(client):
    assert client.get("/_k0sngin/nope.js").status_code == 404


def test_no_listing(client):
    assert client.get("/_k0sngin/").status_code == 404


def test_no_escape_from_static_dir(client):
    for path in ("/_k0sngin/..%2Fmain.py", "/_k0sngin/../main.py",
                 "/_k0sngin/%2e%2e/main.py"):
        response = client.get(path)
        assert "FastAPI" not in response.text, path

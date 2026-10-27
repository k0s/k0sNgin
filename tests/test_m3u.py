"""?format=m3u on an audio directory: a generated playlist (docs/playlist-design.md)."""

import pathlib

from k0sngin.playlist import build_m3u


def test_build_m3u():
    tracks = [{"name": "a b.mp3", "label": "First"},
              {"name": "c.mp3", "label": "Two\nlines"}]
    text = build_m3u("An Album", tracks, "https://k0s.org/sound/x/")
    assert text == (
        "#EXTM3U\n"
        "#PLAYLIST:An Album\n"
        "#EXTINF:-1,First\n"
        "https://k0s.org/sound/x/a%20b.mp3\n"
        "#EXTINF:-1,Two lines\n"
        "https://k0s.org/sound/x/c.mp3\n"
    )


def test_build_m3u_without_title():
    text = build_m3u("", [{"name": "a.mp3", "label": "a.mp3"}], "http://h/d/")
    assert "#PLAYLIST" not in text


def _album(root: pathlib.Path, name: str, files, ini: str) -> None:
    d = root / name
    d.mkdir()
    for f in files:
        (d / f).write_bytes(b"stub")
    (d / "index.ini").write_text(ini)


def test_m3u_response(client, site_root):
    _album(site_root, "m3u_album", ["one.mp3", "two.mp3", "art.jpg"],
           "/title = An Album\n/all =\none.mp3 = First\ntwo.mp3 = Second\n/audio =\n")
    response = client.get("/m3u_album/?format=m3u")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpegurl")
    assert response.headers["content-disposition"] == 'inline; filename="m3u_album.m3u"'
    assert response.headers["cache-control"] == "no-cache"
    assert response.text.splitlines() == [
        "#EXTM3U",
        "#PLAYLIST:An Album",
        "#EXTINF:-1,First",
        "http://testserver/m3u_album/one.mp3",
        "#EXTINF:-1,Second",
        "http://testserver/m3u_album/two.mp3",
    ]


def test_m3u_ignored_without_audio(client, site_root):
    _album(site_root, "m3u_plain", ["one.mp3"], "/title = Plain\n")
    response = client.get("/m3u_plain/?format=m3u")
    assert response.headers["content-type"].startswith("text/html")


def test_m3u_ignored_when_off(client, site_root):
    _album(site_root, "m3u_off", ["one.mp3"], "/audio = off\n")
    response = client.get("/m3u_off/?format=m3u")
    assert response.headers["content-type"].startswith("text/html")

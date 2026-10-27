"""Audio directories render as player pages; /audio cascades (docs/playlist-design.md)."""

import pathlib


def _album(root: pathlib.Path, rel: str, files=(), ini=None) -> pathlib.Path:
    d = root / rel
    d.mkdir(parents=True)
    for name in files:
        (d / name).write_bytes(b"stub")
    if ini is not None:
        (d / "index.ini").write_text(ini)
    return d


def test_player_markup(client, site_root):
    _album(site_root, "aud_page", ["one.mp3", "two.mp3", "cover.jpg"],
           "/title = An Album\n/all =\n"
           "one.mp3 = First : with a note\ntwo.mp3 = Second\n"
           "/audio = gap=1.5\n")
    html = client.get("/aud_page/").text
    assert 'class="player" data-gap="1.5"' in html
    assert '<img class="player-cover" src="cover.jpg"' in html
    assert '<li data-src="one.mp3">' in html
    assert '>First</a>' in html
    assert '<span class="track-description">with a note</span>' in html
    assert '>Second</a>' in html
    assert html.index("one.mp3") < html.index("two.mp3")
    assert '<script src="/_k0sngin/playlist.js" defer></script>' in html
    assert 'href="/_k0sngin/playlist.css"' in html
    assert '<link rel="alternate" type="audio/mpegurl" href="?format=m3u"' in html
    assert 'href="?format=m3u">Open in a media player' in html
    # nothing else to list, so no empty file list
    assert 'class="file-list"' not in html


def test_other_files_listed_below(client, site_root):
    _album(site_root, "aud_others", ["one.mp3", "notes.txt"], "/audio =\n")
    html = client.get("/aud_others/").text
    assert html.index('class="playlist"') < html.index('class="file-list"')
    assert 'href="notes.txt"' in html


def test_names_are_url_encoded(client, site_root):
    _album(site_root, "aud_names", ["my song.mp3"], "/audio =\n")
    html = client.get("/aud_names/").text
    assert 'data-src="my%20song.mp3"' in html


def test_without_audio_directive_unchanged(client, site_root):
    _album(site_root, "aud_none", ["one.mp3"])
    html = client.get("/aud_none/").text
    assert 'class="player"' not in html
    assert "playlist.js" not in html
    assert 'class="file-list"' in html


def test_cascade(client, site_root):
    _album(site_root, "aud_tree", ini="/audio = gap=2\n")
    _album(site_root, "aud_tree/album", ["a.mp3"])
    _album(site_root, "aud_tree/quiet", ["b.mp3"], "/audio = off\n")
    _album(site_root, "aud_tree/quiet/loud", ["c.mp3"], "/audio =\n")
    # the parent holds only directories: no player
    assert 'class="player"' not in client.get("/aud_tree/").text
    # inherited, with the parent's arguments
    assert 'data-gap="2.0"' in client.get("/aud_tree/album/").text
    # opted out
    assert 'class="player"' not in client.get("/aud_tree/quiet/").text
    # back on below the opt-out; a child's value replaces the parent's wholesale
    assert 'data-gap="0.0"' in client.get("/aud_tree/quiet/loud/").text

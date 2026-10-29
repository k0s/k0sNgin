"""Tests for the `/audio` formatter (docs/playlist-design.md).

The formatter only reads names from the listing and the directory on disk;
audio and image files here are name-only stubs.
"""

import pathlib

from k0sngin.formatter import AudioFormatter, formatters


def _dir(tmp_path: pathlib.Path, names) -> pathlib.Path:
    for name in names:
        (tmp_path / name).write_bytes(b"stub")
    return tmp_path


def _listing(*names) -> dict:
    """A listing as serve_directory builds it: name -> entry, in order."""
    return {name: {"name": name, "type": "file"} for name in names}


def _format(value, directory, files):
    return AudioFormatter().format(value, directory, None, {"files": files})


def test_registered():
    assert formatters["audio"] is AudioFormatter


def test_tracks_in_listing_order(tmp_path):
    d = _dir(tmp_path, ["b.mp3", "a.wav", "notes.txt"])
    result = _format("", d, _listing("b.mp3", "notes.txt", "a.wav"))
    assert [t["name"] for t in result["tracks"]] == ["b.mp3", "a.wav"]
    assert result["audio"] is True


def test_non_tracks_stay_in_files(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "notes.txt"])
    (d / "sub").mkdir()
    files = _listing("a.mp3", "notes.txt")
    files["sub"] = {"name": "sub", "type": "directory"}
    result = _format("", d, files)
    assert list(result["other_files"]) == ["notes.txt", "sub"]
    assert "files" not in result  # the full listing is left in place


def test_playlists_are_not_tracks(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "list.m3u", "list.pls"])
    result = _format("", d, _listing("a.mp3", "list.m3u", "list.pls"))
    assert [t["name"] for t in result["tracks"]] == ["a.mp3"]
    assert "list.m3u" in result["other_files"]


def test_label_prefers_title_then_description_then_name(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "b.mp3", "c.mp3"])
    files = _listing("a.mp3", "b.mp3", "c.mp3")
    files["a.mp3"].update(title="Quote", description="Speaker")
    files["b.mp3"]["description"] = "Just a description"
    result = _format("", d, files)
    labels = [t["label"] for t in result["tracks"]]
    assert labels == ["Quote", "Just a description", "c.mp3"]


def test_no_tracks_leaves_listing_alone(tmp_path):
    d = _dir(tmp_path, ["notes.txt", "cover.jpg"])
    assert _format("", d, _listing("notes.txt", "cover.jpg")) is None


def test_off_values(tmp_path):
    d = _dir(tmp_path, ["a.mp3"])
    for value in ("off", "false", "no", " OFF "):
        assert _format(value, d, _listing("a.mp3")) is None


def test_gap(tmp_path):
    d = _dir(tmp_path, ["a.mp3"])
    assert _format("", d, _listing("a.mp3"))["gap"] == 0.0
    assert _format("gap=1.5", d, _listing("a.mp3"))["gap"] == 1.5
    for bad in ("gap=soon", "gap=-2", "gap=nan", "gap=inf"):
        assert _format(bad, d, _listing("a.mp3"))["gap"] == 0.0


def test_cover_explicit(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "front.jpg", "back.jpg"])
    result = _format("cover=front.jpg", d, _listing("a.mp3", "front.jpg", "back.jpg"))
    assert result["cover"] == "front.jpg"
    assert list(result["other_files"]) == ["back.jpg"]


def test_cover_explicit_must_be_a_local_image(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "notes.txt"])
    for value in ("cover=missing.jpg", "cover=notes.txt", "cover=../x.jpg",
                  "cover=/etc/x.jpg"):
        assert _format(value, d, _listing("a.mp3"))["cover"] is None


def test_cover_fallback_finds_unlisted_single_image(tmp_path):
    """`/all =` hides undescribed files, so the fallback looks at the disk."""
    d = _dir(tmp_path, ["a.mp3", "album.jpg"])
    assert _format("", d, _listing("a.mp3"))["cover"] == "album.jpg"


def test_cover_fallback_needs_exactly_one_image(tmp_path):
    d = _dir(tmp_path, ["a.mp3", "one.jpg", "two.png"])
    assert _format("", d, _listing("a.mp3"))["cover"] is None

"""The on-disk render cache.

Two things are load-bearing beyond "it avoids work", and both are tested here:
the artifact path is an invertible function of the source path (the asset
pipeline needs that to tell warm from cold without rendering), and no cache
failure is ever allowed to fail a request.
"""

import pathlib

import pytest

from k0sngin.cache import RenderCache
from k0sngin.renderers import get_renderer


@pytest.fixture
def renderer():
    return get_renderer("markdown")


@pytest.fixture
def cache(tmp_path):
    return RenderCache(tmp_path / "render")


def test_artifact_path_mirrors_the_source_tree(cache, renderer):
    """Source path in, artifact path out — computable without reading either."""
    path = cache.artifact_path(pathlib.PurePath("a/b/notes.md"), renderer)
    assert path == (cache.root / "markdown" / renderer.version()
                    / "a" / "b" / "notes.md.html")


def test_version_is_part_of_the_path(cache, renderer):
    """A renderer's version scopes its artifacts, so a bump orphans a directory."""
    path = cache.artifact_path(pathlib.PurePath("notes.md"), renderer)
    assert renderer.version() in path.parts


def test_first_render_misses_then_hits(cache, renderer):
    """The second request for unchanged content is a hit."""
    relative = pathlib.PurePath("notes.md")
    fragment, was_cached = cache.get_or_render(b"# One\n", relative, renderer)
    assert "<h1>One</h1>" in fragment
    assert was_cached is False

    fragment, was_cached = cache.get_or_render(b"# One\n", relative, renderer)
    assert "<h1>One</h1>" in fragment
    assert was_cached is True


def test_changed_content_is_a_miss(cache, renderer):
    """Staleness is decided by content, not by timestamps."""
    relative = pathlib.PurePath("notes.md")
    cache.get_or_render(b"# One\n", relative, renderer)
    fragment, was_cached = cache.get_or_render(b"# Two\n", relative, renderer)
    assert "<h1>Two</h1>" in fragment
    assert was_cached is False


def test_write_leaves_no_temporary_files(cache, renderer):
    """Entries appear atomically; no half-written files are left behind."""
    relative = pathlib.PurePath("notes.md")
    cache.get_or_render(b"# One\n", relative, renderer)
    artifact = cache.artifact_path(relative, renderer)
    siblings = list(artifact.parent.iterdir())
    assert siblings == [artifact]


def test_corrupt_entry_is_re_rendered(cache, renderer):
    """An artifact without a usable header is ignored rather than served."""
    relative = pathlib.PurePath("notes.md")
    cache.get_or_render(b"# One\n", relative, renderer)
    artifact = cache.artifact_path(relative, renderer)
    artifact.write_text("garbage with no header\n")

    fragment, was_cached = cache.get_or_render(b"# One\n", relative, renderer)
    assert was_cached is False
    assert "<h1>One</h1>" in fragment


def test_entry_for_different_content_is_ignored(cache, renderer):
    """A stale artifact under a stable path is never served."""
    relative = pathlib.PurePath("notes.md")
    cache.get_or_render(b"# One\n", relative, renderer)
    artifact = cache.artifact_path(relative, renderer)
    stale = artifact.read_text().replace("<h1>One</h1>", "<h1>Stale</h1>")
    artifact.write_text(stale)

    fragment, _ = cache.get_or_render(b"# One\n", relative, renderer)
    assert "<h1>Stale</h1>" in fragment  # digest still matches: a legitimate hit

    fragment, was_cached = cache.get_or_render(b"# Different\n", relative, renderer)
    assert was_cached is False
    assert "<h1>Different</h1>" in fragment


def test_unwritable_cache_still_renders(tmp_path, renderer, capsys):
    """A broken cache degrades to rendering every time, and says so once."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory\n")
    cache = RenderCache(blocked)

    relative = pathlib.PurePath("notes.md")
    for _ in range(2):
        fragment, was_cached = cache.get_or_render(b"# One\n", relative, renderer)
        assert "<h1>One</h1>" in fragment
        assert was_cached is False

    assert capsys.readouterr().out.count("Render cache unavailable") == 1


def test_serving_writes_the_expected_artifact(client, cache_root):
    """The server and the pre-render CLI must agree on where an artifact lives."""
    renderer = get_renderer("markdown")
    client.get("/documents/notes.md")
    artifact = (cache_root / "markdown" / renderer.version()
                / "documents" / "notes.md.html")
    assert artifact.is_file()
    assert "<h1>Notes on Deployment</h1>" in artifact.read_text()


def test_serving_renders_once_across_requests(client, monkeypatch):
    """A warm cache means no rendering in the request path at all."""
    from k0sngin.renderers import MarkdownRenderer

    client.get("/documents/plain/inner.md")  # warm it

    calls = []
    original = MarkdownRenderer.render

    def counted(self, source):
        calls.append(source)
        return original(self, source)

    monkeypatch.setattr(MarkdownRenderer, "render", counted)
    assert client.get("/documents/plain/inner.md").status_code == 200
    assert calls == []

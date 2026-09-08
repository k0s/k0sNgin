"""The pre-render CLI (``k0sngin-render``).

The CLI exists to drive cache misses to zero, so the property worth testing is
not "it renders files" but **"it renders exactly what the server would ask
for, at the path the server would look for it"**. A test that only checked
that some HTML appeared somewhere would pass while the tool silently wrote
artifacts nothing ever reads.

These build their own tree and point `K0SNGIN_TOP_LEVEL` at it, so they are
independent of the session-wide fixture in conftest.
"""

import pathlib

import pytest

from k0sngin.scripts import render


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A served root with documents in and out of transformer scope."""
    site = tmp_path / "site"
    (site / "notes").mkdir(parents=True)
    (site / "opaque").mkdir()

    (site / "index.ini").write_text("/transformer = *.md=markdown\n")
    (site / "top.md").write_text("# Top\n\nbody\n")
    (site / "notes" / "deep.md").write_text("# Deep\n\nbody\n")
    (site / "notes" / "picture.png").write_bytes(b"\x89PNG not really")
    # A subtree that clears inheritance: its .md must NOT be rendered.
    (site / "opaque" / "index.ini").write_text("/transformer =\n")
    (site / "opaque" / "off.md").write_text("# Off\n\nbody\n")

    monkeypatch.setenv("K0SNGIN_TOP_LEVEL", str(site))
    # transformer/path bind TOP_LEVEL_DIR at import, so patch where it is used.
    from k0sngin import transformer
    monkeypatch.setattr(transformer, "TOP_LEVEL_DIR", site)
    return site


@pytest.fixture
def cache_dir(tmp_path):
    """A cache root of this test's own."""
    return tmp_path / "cache"


def run(*args):
    """Invoke the CLI, returning its exit status."""
    return render.main([str(argument) for argument in args])


def artifacts(cache_dir):
    """Every artifact under `cache_dir`, as paths relative to it."""
    if not cache_dir.exists():
        return set()
    return {path.relative_to(cache_dir).as_posix()
            for path in cache_dir.rglob("*") if path.is_file()}


def test_renders_a_directory_recursively(tree, cache_dir):
    """A directory argument reaches documents at any depth."""
    assert run("--cache-dir", cache_dir, "--top-level", tree, tree) == 0
    written = artifacts(cache_dir)
    assert any(name.endswith("/top.md.html") for name in written)
    assert any(name.endswith("/notes/deep.md.html") for name in written)


def test_artifact_path_mirrors_the_source_tree(tree, cache_dir):
    """The artifact lands where the server will look for it.

    This is the whole contract: same renderer name, same version, same path
    below the served root. Computed here from the cache's own API so the test
    fails if either side of that agreement moves.
    """
    from k0sngin.cache import RenderCache
    from k0sngin.transformer import resolve_renderer

    run("--cache-dir", cache_dir, "--top-level", tree, tree)

    renderer, _ = resolve_renderer(tree / "notes" / "deep.md")
    expected = RenderCache(cache_dir).artifact_path(
        pathlib.PurePath("notes/deep.md"), renderer)
    assert expected.is_file()


def test_respects_a_subtree_that_opts_out(tree, cache_dir):
    """`/transformer =` clears inheritance, and the crawler honours it."""
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    assert not any("off.md" in name for name in artifacts(cache_dir))


def test_ignores_files_no_glob_matches(tree, cache_dir):
    """A file the configuration says nothing about is left alone."""
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    assert not any("picture.png" in name for name in artifacts(cache_dir))


def test_single_file_argument(tree, cache_dir):
    """A file argument renders just that file."""
    assert run("--cache-dir", cache_dir, "--top-level", tree,
               tree / "top.md") == 0
    assert len(artifacts(cache_dir)) == 1


def test_second_run_is_a_no_op(tree, cache_dir, capsys):
    """Re-running finds everything warm rather than rendering again."""
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    capsys.readouterr()
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    assert "0 rendered, 2 already cached" in capsys.readouterr().out


def test_force_re_renders(tree, cache_dir, capsys):
    """`--force` ignores a warm entry."""
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    capsys.readouterr()
    run("--force", "--cache-dir", cache_dir, "--top-level", tree, tree)
    assert "2 rendered" in capsys.readouterr().out


def test_editing_the_source_invalidates(tree, cache_dir, capsys):
    """A changed file is re-rendered without needing --force.

    The entry is keyed by path but *verified* by content digest, which is what
    makes this work where an mtime comparison would not.
    """
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    (tree / "top.md").write_text("# Top\n\nrewritten\n")
    capsys.readouterr()
    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    assert "1 rendered, 1 already cached" in capsys.readouterr().out


def test_dry_run_writes_nothing(tree, cache_dir, capsys):
    """`--dry-run` reports what is cold and leaves the cache alone."""
    assert run("--dry-run", "--cache-dir", cache_dir, "--top-level", tree, tree) == 0
    assert "(dry run)" in capsys.readouterr().out
    assert artifacts(cache_dir) == set()


def test_follows_symlinked_directories(tree, cache_dir, tmp_path):
    """Documents behind a symlinked directory are rendered, keyed by site path.

    `site/stories` is a symlink on the real site, and the server addresses what
    is under it as `stories/...`. A crawl that skipped links — or that keyed by
    the link's target — would leave exactly those files permanently cold.
    """
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "linked.md").write_text("# Linked\n\nbody\n")
    (tree / "linked").symlink_to(outside)

    run("--cache-dir", cache_dir, "--top-level", tree, tree)
    assert any(name.endswith("/linked/linked.md.html") for name in artifacts(cache_dir))


def test_symlink_loop_terminates(tree, cache_dir):
    """A directory symlink pointing at an ancestor does not walk forever."""
    (tree / "notes" / "loop").symlink_to(tree)
    assert run("--cache-dir", cache_dir, "--top-level", tree, tree) == 0


def test_missing_path_fails(tree, cache_dir, capsys):
    """A path that does not exist is an error, not a silent no-op."""
    assert run("--cache-dir", cache_dir, "--top-level", tree,
               tree / "nope.md") == 1
    assert "no such file" in capsys.readouterr().err


def test_file_outside_the_root_fails_clearly(tree, cache_dir, tmp_path, capsys):
    """A file outside the served root names that as the problem.

    Containment is checked before the transformer cascade precisely so this
    reports the real cause; asked the other way round it would say "no
    /transformer glob matches", which is true and useless.
    """
    stray = tmp_path / "stray.md"
    stray.write_text("# Stray\n")
    assert run("--cache-dir", cache_dir, "--top-level", tree, stray) == 1
    assert "outside the served root" in capsys.readouterr().err


def test_unwritable_cache_reports_failure(tree, cache_dir, capsys):
    """An unwritable cache is a failure, not a silent success."""
    cache_dir.mkdir()
    cache_dir.chmod(0o500)
    try:
        status = run("--cache-dir", cache_dir, "--top-level", tree, tree)
    finally:
        cache_dir.chmod(0o700)
    assert status == 1
    assert "failed" in capsys.readouterr().err

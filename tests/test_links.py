"""Tests for the symlink allowlist (``K0SNGIN_LINKS``; src/k0sngin/links.py).

The served tree (see conftest) contains ``linked -> <tmp>/external`` (whose
target is in links.json) and ``unlisted -> <tmp>/notallowed`` (whose target is
not). ``external/`` itself contains ``escape.txt -> <tmp>/secret.txt``, a
nested symlink leading outside every allowed root.
"""

import json

from k0sngin.links import load_link_targets


# --- serving through the allowlist -----------------------------------------

def test_allowed_symlink_directory_serves(client):
    """A directory symlink whose target is in links.json serves its index."""
    r = client.get("/linked/")
    assert r.status_code == 200
    assert 'href="poem.txt"' in r.text
    assert "a poem from outside" in r.text  # its own index.ini is honored


def test_allowed_symlink_directory_redirects_to_slash(client):
    """The no-trailing-slash form 301s, same as a real directory."""
    r = client.get("/linked", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"].endswith("/linked/")


def test_file_inside_allowed_symlink_serves(client):
    """A file reached through an allowed symlink is served."""
    r = client.get("/linked/poem.txt")
    assert r.status_code == 200
    assert r.text == "external poem\n"


def test_nested_symlink_escaping_allowed_target_refused(client):
    """A symlink inside an allowed target that leads outside every allowed
    root is refused: resolve() follows the whole chain."""
    r = client.get("/linked/escape.txt")
    assert r.status_code == 404
    assert "TOP SECRET" not in r.text


def test_unlisted_symlink_refused(client):
    """A symlink whose target is not in links.json stays a 404."""
    assert client.get("/unlisted/").status_code == 404
    assert client.get("/unlisted/nope.txt").status_code == 404


# --- load_link_targets ------------------------------------------------------

def test_load_link_targets_unset_disables():
    """No K0SNGIN_LINKS value -> empty allowlist."""
    assert load_link_targets(None) == []
    assert load_link_targets("") == []


def test_load_link_targets_missing_file_disables(tmp_path):
    assert load_link_targets(tmp_path / "absent.json") == []


def test_load_link_targets_invalid_json_disables(tmp_path):
    links = tmp_path / "links.json"
    links.write_text("not json {")
    assert load_link_targets(links) == []


def test_load_link_targets_non_string_values_disable(tmp_path):
    """Strings only: any non-string value invalidates the whole file."""
    links = tmp_path / "links.json"
    links.write_text(json.dumps({"web/site/a": "docs/a", "web/site/b": 2}))
    assert load_link_targets(links) == []
    links.write_text(json.dumps(["docs/a"]))  # not an object at all
    assert load_link_targets(links) == []


def test_load_link_targets_resolves_values(tmp_path, monkeypatch):
    """Relative values resolve against $HOME; absolute values stand alone."""
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: tmp_path))
    links = tmp_path / "links.json"
    links.write_text(json.dumps({
        "web/site/rel": "docs/rel",
        "web/site/abs": str(tmp_path / "elsewhere"),
    }))
    assert load_link_targets(links) == [
        (tmp_path / "docs/rel").resolve(),
        (tmp_path / "elsewhere").resolve(),
    ]

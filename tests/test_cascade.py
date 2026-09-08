"""Direction of the cascading-formatter walk.

`collect_cascading_formatters` walks a directory's ancestors, and the
documented rule is that the *most specific* directory wins. Getting this
backwards is invisible for a directory's own index (which re-merges its local
formatters afterwards) but wrong for every directory below one that overrides
something — which is why it went unnoticed and why it is tested directly here.
"""

import pathlib

import pytest

from k0sngin import directory


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A site root that sets /css, and a subtree that overrides it."""
    site = tmp_path / "site"
    (site / "portfolio" / "sub").mkdir(parents=True)
    (site / "index.ini").write_text("/css = /root.css\n/icon = /root.ico\n")
    (site / "portfolio" / "index.ini").write_text("/css = /portfolio.css\n")
    monkeypatch.setattr(directory, "TOP_LEVEL_DIR", site)
    return site


def test_descendant_overrides_ancestor(tree):
    """A directory's own value beats the one it inherits."""
    formatters = directory.collect_cascading_formatters(tree / "portfolio")
    assert formatters["css"] == "/portfolio.css"


def test_override_reaches_further_descendants(tree):
    """The override applies below the directory that declared it."""
    formatters = directory.collect_cascading_formatters(tree / "portfolio" / "sub")
    assert formatters["css"] == "/portfolio.css"


def test_uncontested_ancestor_values_still_inherit(tree):
    """Overriding one directive doesn't drop the others."""
    formatters = directory.collect_cascading_formatters(tree / "portfolio" / "sub")
    assert formatters["icon"] == "/root.ico"


def test_walk_stops_at_the_served_root(tmp_path, monkeypatch):
    """Configuration above the served root is not part of the site."""
    site = tmp_path / "site"
    site.mkdir()
    (tmp_path / "index.ini").write_text("/css = /outside.css\n")
    monkeypatch.setattr(directory, "TOP_LEVEL_DIR", site)
    assert directory.collect_cascading_formatters(site) == {}

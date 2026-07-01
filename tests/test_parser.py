"""Unit tests for the conf-file parser (``k0sngin.parser``).

The parser backs directory metadata (index.ini), so its handling of key/value
pairs, line continuation, and orphaned lines is worth pinning directly.
"""

from k0sngin.parser import parse_config


def test_basic_key_value_pairs():
    """Plain ``key = value`` lines parse into a dict."""
    parsed = parse_config("/title = My Title\nkey = value\n")
    assert parsed["/title"] == "My Title"
    assert parsed["key"] == "value"


def test_empty_value():
    """A key with no value parses to an empty string, not a missing key."""
    parsed = parse_config("empty =\n")
    assert parsed["empty"] == ""


def test_line_continuation():
    """Indented lines following a key extend its value, space-joined."""
    parsed = parse_config("/title = My Title\n    with continuation\n    and more\n")
    assert parsed["/title"] == "My Title with continuation and more"


def test_orphaned_continuation_is_reported():
    """An indented line with no preceding key is recorded in _orphaned_lines."""
    parsed = parse_config("    orphaned first\nkey = value\n")
    assert parsed["key"] == "value"
    assert "orphaned first" in parsed["_orphaned_lines"]


def test_blank_lines_are_ignored():
    """Blank lines don't create entries or break surrounding pairs."""
    parsed = parse_config("a = 1\n\n\nb = 2\n")
    assert parsed == {"a": "1", "b": "2"}

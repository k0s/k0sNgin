"""
Parser for a custom INI-like format without sections.

This format supports:
- Key-value pairs: key = value
- Line continuation: indented lines continue the previous value
- Special keys starting with /
- Empty values
"""

from typing import Dict, List, Optional, Tuple
import re


class ConfigParser:
    """Parser for custom INI-like format without sections."""

    def __init__(self):
        self.data: Dict[str, str] = {}

    def parse(self, content: str) -> Dict[str, str]:
        """
        Parse the configuration content.

        Args:
            content: The configuration content as a string

        Returns:
            Dictionary of key-value pairs
        """
        self.data = {}
        lines = content.splitlines()
        current_key = None
        current_value_parts = []
        orphaned_lines = []

        for line_num, line in enumerate(lines, 1):
            line = line.rstrip()  # Remove trailing whitespace

            # Skip empty lines
            if not line:
                continue

            # Check if this is a continuation line (starts with whitespace)
            if line.startswith((' ', '\t')):
                if current_key is not None:
                    # This is a continuation of the previous value
                    current_value_parts.append(line.strip())
                else:
                    # This is an orphaned continuation line
                    orphaned_lines.append(f"Line {line_num}: {line}")
                continue

            # Save the previous key-value pair if we have one
            if current_key is not None:
                self.data[current_key] = ' '.join(current_value_parts)
                current_key = None
                current_value_parts = []

            # Parse new key-value pair
            key, value = self._parse_line(line)
            if key is not None:
                current_key = key
                current_value_parts = [value] if value else []
            else:
                # Invalid line that's not a continuation - treat as orphaned
                orphaned_lines.append(f"Line {line_num}: {line}")

        # Don't forget the last key-value pair
        if current_key is not None:
            self.data[current_key] = ' '.join(current_value_parts)

        # Handle orphaned continuation lines
        if orphaned_lines:
            # For now, we'll include them as a special key
            # In a production system, you might want to raise an exception
            self.data['_orphaned_lines'] = '; '.join(orphaned_lines)

        return self.data

    def _parse_line(self, line: str) -> Tuple[Optional[str], str]:
        """
        Parse a single line into key and value.

        Args:
            line: The line to parse

        Returns:
            Tuple of (key, value) or (None, '') if line is invalid
        """
        # Look for the first '=' that's not part of the key
        equal_pos = line.find('=')
        if equal_pos == -1:
            return None, ''

        key = line[:equal_pos].strip()
        value = line[equal_pos + 1:].strip()

        if not key:
            return None, ''

        return key, value

    def get(self, key: str, default: str = '') -> str:
        """Get a value by key."""
        return self.data.get(key, default)

    def get_all(self) -> Dict[str, str]:
        """Get all key-value pairs."""
        return self.data.copy()

    def has_key(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self.data


def parse_config(content: str) -> Dict[str, str]:
    """
    Convenience function to parse configuration content.

    Args:
        content: The configuration content as a string

    Returns:
        Dictionary of key-value pairs
    """
    parser = ConfigParser()
    return parser.parse(content)


def parse_config_file(filepath: str) -> Dict[str, str]:
    """
    Parse a configuration file.

    Args:
        filepath: Path to the configuration file

    Returns:
        Dictionary of key-value pairs
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    return parse_config(content)

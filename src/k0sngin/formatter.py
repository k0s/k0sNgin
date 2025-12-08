"""
Formatters for the directory index.
"""

# TODO: cascading formatters. They will need to know about their parent.

from abc import ABC, abstractmethod
import pathlib

from fastapi import Request


class Formatter(ABC):
    """ABC: Formatter for the directory index."""

    @classmethod
    @abstractmethod
    def key(cls) -> str:
        """Key for the formatter."""

    @abstractmethod
    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> str:
        """Format the directory index."""


class CSSFormatter(Formatter):
    """Space-separated list of CSS paths to include in the directory index."""

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "css"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> str:
        """Format the directory index."""
        value = value.strip()
        if not value:
            return None
        return {"css": value.split()}


class IconFormatter(Formatter):
    """URL for favicon for the directory index."""

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "icon"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> str:
        """Format the directory index."""
        return {"icon": value.strip()}


class TitleFormatter(Formatter):
    """Title for the directory index.
    Splits a description into a title and a description via a separator in
    the description.  The template will now have an additional variable,
    'title', per file
    Arguments:
    * separator: what separator to use (':' by default)
    """

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "title"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> dict:
        """Format the directory index."""
        value = value.strip()
        if not value:
            return None

        # Default separator
        separator = ':'

        # Set webpage title
        result = {}

        if ':' in value:
            _title, url = [i.strip() for i in value.split(':', 1)]
            if '://' in url:
                # Title with URL link
                result['title'] = _title
                result['link'] = url
            else:
                # No URL, use full value as title
                result['title'] = value
        else:
            # No colon, use value as title
            result['title'] = value

        # Process files: split descriptions with separator
        files = variables.get('files', {})
        for file_name, file_data in files.items():
            description = file_data.get('description')
            if description and separator in description:
                # Split description into title and description
                file_title, file_description = description.split(separator, 1)
                file_title = file_title.strip()
                file_description = file_description.strip()
                if not file_title:
                    file_title = file_data.get('name', file_name)
                file_data['title'] = file_title
                file_data['description'] = file_description
            else:
                # No separator: use description as title, clear description
                file_data['title'] = description
                file_data['description'] = None

        return result

all_formatters = [
    CSSFormatter,
    TitleFormatter,
    IconFormatter,
]

formatters = {formatter.key(): formatter for formatter in all_formatters}

def apply_formatters(_formatters: dict,
                     directory: pathlib.Path,
                     request: Request,
                     variables: dict):
    """Apply formatters to the directory index template variables."""
    for key, value in _formatters.items():
        formatter = formatters.get(key)
        if formatter is None:
            message = f"Formatter not found: {key}"
            print(message)  # TODO: log this; this is a warning
            continue
        formatter = formatter()
        _variables = formatter.format(value, directory, request, variables)
        if _variables:
            variables.update(_variables)
    return variables

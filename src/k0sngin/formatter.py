"""
Formatters for the directory index.
"""

# TODO: cascading formatters. They will need to know about their parent.

from abc import ABC, abstractmethod
import pathlib
import re

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


class LinksFormatter(Formatter):
    """Alternate-form links for files in the directory index.

    Description segments of the form ``; [text]=target`` become per-file
    links and are removed from the description::

        resume.html = My Resume; [PDF]=resume.pdf

    yields ``file_data['links'] == {"PDF": "resume.pdf"}`` with description
    ``My Resume`` — one conceptual resource, rendered with links to each form.
    """

    link_re = re.compile(r';\s*\[([^\]]+)\]\s*=\s*(\S+)')

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "links"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> None:
        """Format the directory index."""
        files = variables.get('files', {})
        for file_data in files.values():
            description = file_data.get('description')
            if not description:
                continue
            links = dict(self.link_re.findall(description))
            if not links:
                continue
            file_data['links'] = links
            description = self.link_re.sub('', description).strip()
            file_data['description'] = description or None
        return None


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
            # No separator: leave the description as-is, so a file renders
            # identically with and without /title.

        return result

# Canonical application order: `links` must extract alternate-form link
# segments before `title` splits descriptions on ':'.
all_formatters = [
    CSSFormatter,
    LinksFormatter,
    TitleFormatter,
    IconFormatter,
]

formatters = {formatter.key(): formatter for formatter in all_formatters}

def apply_formatters(_formatters: dict,
                     directory: pathlib.Path,
                     request: Request,
                     variables: dict):
    """Apply formatters to the directory index template variables.

    Formatters run in the canonical ``all_formatters`` order, not the order
    they appear in ``index.ini``.
    """
    for key in _formatters:
        if key not in formatters:
            message = f"Formatter not found: {key}"
            print(message)  # TODO: log this; this is a warning
    for key, formatter in formatters.items():
        if key not in _formatters:
            continue
        _variables = formatter().format(_formatters[key], directory, request, variables)
        if _variables:
            variables.update(_variables)
    return variables

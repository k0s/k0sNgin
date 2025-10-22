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


class DescriptionFormatter(Formatter):
    """Description for the directory index."""

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "description"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> str:
        return {
            "description": value.strip()
        }


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

all_formatters = [
    CSSFormatter,
    DescriptionFormatter,
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

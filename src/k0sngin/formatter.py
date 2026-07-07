"""
Formatters for the directory index.
"""

# TODO: cascading formatters. They will need to know about their parent.

from abc import ABC, abstractmethod
import mimetypes
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


class BreadcrumbsFormatter(Formatter):
    """Full breadcrumb trail for the directory index.

    ``/breadcrumbs`` (empty value) renders a linked trail of ancestor
    directories above the page instead of the default parent-only link::

        / » pictures » gallery

    Cascades: enabling it on a directory enables it for all descendants;
    a descendant may opt back out with ``/breadcrumbs = off``. The root
    itself shows no trail (nothing above it).
    """

    off_values = {"off", "false", "no"}

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "breadcrumbs"

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> dict:
        """Format the directory index."""
        if value.strip().lower() in self.off_values:
            return None
        path = request.scope.get("path", "/")
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return None  # the root has nothing above it
        crumbs = [{"name": "/", "url": "/"}]
        url = ""
        for segment in segments:
            url += f"/{segment}"
            crumbs.append({"name": segment, "url": url + "/"})
        return {"breadcrumbs": crumbs}


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


class ImagesFormatter(Formatter):
    """Image gallery: restrict the listing to images and size them for display.

    Ported from montage (the decoupage photogallery extension). The value is a
    comma-separated argument string of bare flags and key=value pairs::

        /images = thumbnails, size=150x, columns=4

    - ``size=WxH``: display size for ``<img>``; either dimension may be empty
      (``400x``, ``x550``).
    - ``columns``: grid columns (defaults to the number of images).
    - ``thumbnails`` (flag): point ``src`` at ``<thumb_dir>/<thumb_prefix><name>``
      when that file already exists. Thumbnails are never generated in the
      request path — see docs/formatters.md.
    - ``thumb_dir`` (default ``thumbs``), ``thumb_prefix`` (default ``thumb_``).

    Non-image entries (by ``mimetypes.guess_type`` on the name — this includes
    subdirectories) are dropped from the listing. Each surviving entry gets
    ``link`` (the full image) and ``src`` (what ``<img>`` should load).
    """

    defaults = {"thumb_dir": "thumbs", "thumb_prefix": "thumb_"}

    @classmethod
    def key(cls) -> str:
        """Key for the formatter."""
        return "images"

    @staticmethod
    def parse_args(value: str) -> tuple[list, dict]:
        """Parse a montage-style argument string into (flags, kwargs)."""
        flags = []
        kwargs = {}
        for token in value.split(','):
            token = token.strip()
            if not token:
                continue
            if '=' in token:
                key, _, val = token.partition('=')
                kwargs[key.strip()] = val.strip()
            else:
                flags.append(token)
        return flags, kwargs

    @staticmethod
    def parse_size(size: str) -> tuple:
        """Parse ``WxH`` (either side optional) into (width, height)."""
        if not size or 'x' not in size:
            return None, None
        try:
            width, height = [int(i) if i.strip() else None
                             for i in size.split('x', 1)]
        except ValueError:
            return None, None
        return width, height

    def format(self, value: str, directory: pathlib.Path, request: Request, variables: dict) -> dict:
        """Format the directory index."""
        flags, kwargs = self.parse_args(value)
        width, height = self.parse_size(kwargs.get('size', ''))
        thumb_dir = kwargs.get('thumb_dir') or self.defaults['thumb_dir']
        thumb_prefix = kwargs.get('thumb_prefix') or self.defaults['thumb_prefix']
        # thumbnails must live under the served directory
        use_thumbnails = ('thumbnails' in flags
                          and not pathlib.PurePosixPath(thumb_dir).is_absolute()
                          and '..' not in pathlib.PurePosixPath(thumb_dir).parts)

        images = {}
        for name, data in variables.get('files', {}).items():
            mimetype = mimetypes.guess_type(name)[0]
            if not (mimetype and mimetype.startswith('image/')):
                continue
            data['link'] = name
            data['src'] = name
            if use_thumbnails:
                thumbnail = f"{thumb_prefix}{name}"
                if (directory / thumb_dir / thumbnail).is_file():
                    data['src'] = f"{thumb_dir}/{thumbnail}"
            images[name] = data

        try:
            columns = int(kwargs['columns'])
        except (KeyError, ValueError):
            columns = len(images)

        return {
            "files": images,
            "width": width,
            "height": height,
            "columns": max(columns, 1),
            "images": True,
        }


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
# segments before `title` splits descriptions on ':'; `images` filters the
# listing after titles/descriptions are settled.
all_formatters = [
    CSSFormatter,
    LinksFormatter,
    TitleFormatter,
    ImagesFormatter,
    IconFormatter,
    BreadcrumbsFormatter,
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

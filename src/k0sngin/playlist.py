"""M3U playlists generated from an audio directory (``?format=m3u``).

The directory's listing is the source: the same tracks, order and titles as
its player page (see AudioFormatter), so there is no .m3u file to keep in
sync. Durations are -1 (unknown); reading them would mean opening every file
in the request path.
"""

import pathlib
from urllib.parse import quote, urljoin

from fastapi import Request
from starlette.responses import Response


def one_line(text: str) -> str:
    """Collapse whitespace, so a title can't break the line-based format."""
    return " ".join(text.split())


def build_m3u(title: str, tracks: list, directory_url: str) -> str:
    """Extended M3U text for `tracks`, with absolute URLs under `directory_url`.

    Absolute, so a downloaded playlist still plays.
    """
    lines = ["#EXTM3U"]
    if title:
        lines.append(f"#PLAYLIST:{one_line(title)}")
    for track in tracks:
        lines.append(f"#EXTINF:-1,{one_line(track['label'])}")
        lines.append(urljoin(directory_url, quote(track["name"])))
    return "\n".join(lines) + "\n"


def m3u_response(variables: dict, request: Request) -> Response:
    """The playlist for a directory whose variables AudioFormatter has set."""
    directory_url = str(request.url.replace(query=""))
    body = build_m3u(variables.get("title") or "", variables["tracks"], directory_url)
    # A header value must be plain ASCII; the name is only a download hint.
    name = pathlib.PurePosixPath(request.url.path).name
    filename = name.encode("ascii", "ignore").decode().replace('"', "") or "playlist"
    return Response(content=body, media_type="audio/mpegurl; charset=utf-8", headers={
        "Content-Disposition": f'inline; filename="{filename}.m3u"',
        # Generated from index.ini, which can change at any time.
        "Cache-Control": "no-cache",
    })

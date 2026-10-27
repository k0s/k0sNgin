# Design: audio directories as browser players, with M3U as an output

Status: revised 2026-10-27, not yet implemented. Supersedes the 2026-10-15
design, which rendered hand-written `.m3u` files as players (see *History*).

## Goal

A directory of audio, such as an album at `/sound/synth/pure_Nothing/`, should
work in two places:

- In a **browser**, the directory page plays the tracks in order.
- In a **media player** (VLC, mpv), `?format=m3u` on the same URL is a playlist
  of the same tracks.

The directory is the source. Track order and titles already live in its
`index.ini`, as they do for galleries; nothing else has to be kept in sync.

## Example

`/sound/synth/pure_Nothing/index.ini` today:

```
/all =
/title = pure Nothing
planetary_symphonette.mp3 = planetary symphonette
Abyss.mp3 = Abyss
...
```

Turning on the player (here, or once in a parent, see *Opt-in*):

```
/audio = cover=pure_Nothing.jpg
```

- `/sound/synth/pure_Nothing/` shows the cover, the title, and the ten tracks
  in `index.ini` order, with Play all, previous, next and stop. Each row plays
  on click; the current row is highlighted.
- `/sound/synth/pure_Nothing/?format=m3u` returns:

  ```
  #EXTM3U
  #PLAYLIST:pure Nothing
  #EXTINF:-1,planetary symphonette
  https://k0s.org/sound/synth/pure_Nothing/planetary_symphonette.mp3
  #EXTINF:-1,Abyss
  https://k0s.org/sound/synth/pure_Nothing/Abyss.mp3
  ...
  ```

## Behavior

- **Opt-in** through an `/audio` directive in `index.ini`, a sibling of
  `/images`. Without it, directories list as they do today.
- **Which files are tracks:** entries whose guessed mimetype is `audio/*`, in
  listing order (listed in `index.ini` first, then the rest if `/all` is set).
  Titles come from the descriptions, after `/title` has split them.
- **Other entries:** the cover image is shown at the top. Any other files and
  subdirectories stay in an ordinary list below the player, so nothing that is
  reachable today disappears.
- **Arguments**, in the `/images` style (comma-separated flags and
  `key=value`):
  - `cover=<file>`: image shown above the tracks. If it's omitted and the
    directory has exactly one image, that image is used. Otherwise there's no
    cover.
  - `gap=<seconds>`: pause between tracks. Default `0` (albums play through);
    the Shining sample lineup used 1.5.
- **Without JavaScript**, the page is the track list as links: still usable.
- **The page links to `?format=m3u`** as "open in a media player", and declares
  it in the head as
  `<link rel="alternate" type="audio/mpegurl" href="?format=m3u">`.
- **Styling** comes from the cascading `/css`, as for every directory page.

## `?format=m3u`

- Only on directories where `/audio` applies. Elsewhere, the parameter is
  ignored as unknown query parameters are today.
- `Content-Type: audio/mpegurl; charset=utf-8` and
  `Content-Disposition: inline; filename="<directory>.m3u"`, so a browser
  that downloads it names it sensibly.
- `#EXTINF` duration is `-1` (unknown). Reading durations would need an audio
  tag library and file reads in the request path, so it's not worth it here.
- **Entry URLs are absolute**, built from the request's base URL, so a
  downloaded playlist still works. Behind Cloudflare, the scheme must come out
  as `https`. Verify proxy-header handling (`--proxy-headers` /
  `forwarded_allow_ips`) before relying on it.
- Generated per request from the same listing the page uses. The output is
  small and needs no cache.

## Components

### `AudioFormatter` (`formatter.py`)

Key `audio`. Runs after `title` in the canonical order, as `images` does.
It partitions `variables["files"]` into `tracks` (ordered), `cover` and
`others`, sets `audio: True` and `gap`, and leaves `files` as `others` so the
ordinary list template still works.

### Template (`templates/_player.html`)

`index.html` includes the player partial when `audio` is set: cover, an
`<ol class="playlist">` of `<li data-src="…"><a href="…">title</a></li>`,
the m3u link, and `<script src="/_k0sngin/playlist.js" defer>`.

### M3U response (`main.py` / `directory.py`)

When `format=m3u` and the directory's formatters include `audio`, build the
same variables and return the M3U text instead of the HTML page.

### Built-in static files (`main.py`, `src/k0sngin/static/`)

Unchanged from the 2026-10-15 design. Static files shipped in the package are
served under the reserved prefix `/_k0sngin/`, registered before the catch-all.
The route serves only files that exist in `src/k0sngin/static/`: no traversal,
no listing, 404 otherwise. It's needed because the CSP is
`script-src 'self'`. `/_k0sngin/` becomes a reserved path, documented as such.

### `playlist.js` (`src/k0sngin/static/playlist.js`)

Progressive enhancement of `ol.playlist`. It adds the controls and one
`<audio>` element, advances on `ended` after the gap (read from a `data-gap`
attribute), and highlights the current row. No dependencies and no inline
handlers. It is generalized from the hand-built player at
`/sound/samples/shining/`.

## Opt-in: local or cascading

`images` is local-only (it only affects the directory that declares it).
Open question: should `/audio` cascade, so one line in
`/sound/synth/index.ini` turns on the player for every album beneath it?

- **Cascading:** one edit covers about twenty album directories. It only
  takes effect where a directory has audio files, so `sound/synth/` itself is
  unaffected. A per-album `cover=` still goes in each album's own `index.ini`,
  unless the one-image fallback covers it.
- **Local:** consistent with `/images`, and each album opts in explicitly, at
  the cost of an edit per album.

## Limits

- Media on other origins won't play under the CSP's `default-src 'self'`.
  Tracks are local files, so this doesn't arise here.
- One title per track. Credits and per-track notes are future work.
- Playlists that span directories aren't covered. See *Future work*.

## Testing

pytest, alongside the existing suite:

- Formatter: tracks filtered by mimetype and ordered as listed; titles from
  descriptions; `/all` appends unlisted tracks; `cover=` and the one-image
  fallback; `gap` parsing; non-audio entries kept in `others`.
- Page: the playlist markup, the m3u link and `<link rel="alternate">`; a
  directory without `/audio` is unchanged.
- M3U: header, `#PLAYLIST`, `#EXTINF` titles, absolute URLs (https behind a
  proxy), escaping of names with spaces and non-ASCII characters, content type
  and disposition; `?format=m3u` without `/audio` is ignored.
- Static route: serves `playlist.js` with a JavaScript content type; refuses
  anything outside the package's static directory, including traversal.

## Docs

`docs/formatters.md`: an `audio` section next to `images`, covering
arguments, `?format=m3u`, the reserved `/_k0sngin/` prefix, and the
cross-origin limit.

## Future work

- Render standalone `.m3u` files as players (the 2026-10-15 design), for
  playlists that span directories.
- Durations in `#EXTINF` and on the page, if precomputed outside the request
  path.
- Per-track credits or notes.

## History

- 2026-10-15: first design. A `playlist` renderer turned `.m3u` files into
  player pages, chosen by `Accept` header, with `Vary: Accept`. It was dropped
  as the primary path because album directories already keep their track list
  in `index.ini`, so an `.m3u` would duplicate it. Making the directory the
  source also removes the need for content negotiation: `?format=m3u` is an
  explicit request.
- 2026-10-17: the direction changed to the directory as source, with M3U as
  an output.
- 2026-10-27: this document rewritten for that direction.

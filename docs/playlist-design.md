# Design: M3U playlists as browser players

Status: approved 2026-10-15, not yet implemented.

## Goal

An `.m3u` playlist on the site should work in two places from one URL:

- In a **browser**, it opens as a page that plays the entries in order.
- In a **media player** (VLC, mpv) or `curl`, it is the M3U file, unchanged.

One file, kept in sync by whatever tool writes it, serves both audiences. A
playlist may list files from more than one directory, which a directory index
cannot express.

## Behavior

- Opt-in per subtree, like Markdown: `/transformer = *.m3u=playlist` in an
  `index.ini`. Without it, `.m3u` files are served as they are today.
- When the playlist renderer applies, a request whose `Accept` header includes
  `text/html` gets the player page. Any other request gets the M3U source.
  `?format=raw` always gets the source, as it does for every renderer.
- The page shows a heading (the `#PLAYLIST:` title if present, else the
  filename) and one row per entry: the `#EXTINF` title if the entry has one,
  else the entry's filename. With JavaScript it also has Play all, previous,
  next and stop controls, a 1.5 s pause between entries, the current entry
  highlighted, and click-to-play on any row. It links to `?format=raw` as
  "open in a media player".
- Without JavaScript, the page is a list of links to the entries: still usable.
- Styling comes from the containing directory's cascading `/css`, exactly as
  for rendered Markdown, via `templates/document.html`. No playlist-specific
  theming directive.

## Components

### `PlaylistRenderer` (`renderers.py`)

A `Renderer` named `playlist` that turns M3U bytes into an HTML fragment:

- `<h1>` with the playlist title, so `document_title()` picks it up.
- `<ol class="playlist">` of `<li data-src="…"><a href="…">title</a></li>`.
- A link to `?format=raw` and `<script src="/_k0sngin/playlist.js" defer>`.

Parsing rules:

- `#EXTM3U` is optional. `#PLAYLIST:<title>` sets the heading.
- `#EXTINF:<seconds>,<title>` applies to the next entry line. Other `#` lines
  and blank lines are ignored.
- An entry is any other non-blank line. It is playable only if it is a
  relative path or an `http`/`https` URL; anything else (`javascript:`,
  `file:`, …) is listed as plain text without a link.
- Undecodable bytes become replacement characters, as with Markdown. All text
  is HTML-escaped; URLs are attribute-escaped.
- An empty playlist renders a short "no entries" message.

The fragment is cached by the existing render cache, under a `schema`
version, like Markdown. The renderer has no third-party library.

### HTML-only renderers (`main.py`)

A renderer may declare `html_only = True`. For such a renderer the server only
renders when the client's `Accept` includes `text/html`; otherwise it falls
through to serving the file unchanged. Markdown keeps today's behavior
(renders for every client).

Every response for a file an `html_only` renderer applies to (rendered or
raw) carries `Vary: Accept` and `Cache-Control: no-cache`. Without this, the
default one-day caching for `audio/*` types (M3U is served as `audio/mpegurl`) could
let a shared cache hand a browser the raw file or a player the page.

### Built-in static files (`main.py`, `src/k0sngin/static/`)

A route for files shipped inside the package, under the reserved prefix
`/_k0sngin/`, registered before the catch-all. It serves only files that exist
in `src/k0sngin/static/` (no paths outside it, no directory listing; 404
otherwise). Needed because the CSP is `script-src 'self'`: the script must be
a same-origin file, and the content tree is not the place for server code.

`/_k0sngin/` becomes a reserved path: a content directory with that name
would be shadowed. Documented as such.

### `playlist.js` (`src/k0sngin/static/playlist.js`)

Progressive enhancement of `ol.playlist`: adds the controls and one `<audio>`
element, plays rows in order on `ended` with the pause between them, and
highlights the current row. No dependencies, no inline handlers.

## Limits

- The CSP's `default-src 'self'` means media on other origins will not play.
  Such entries are still listed and linked. Documented, not worked around.
- One title per entry. Richer metadata is future work (below).

## Testing

pytest, alongside the existing suite:

- Parsing: with and without `#EXTM3U`; `#PLAYLIST`; `#EXTINF` titles and
  missing titles; comments and blank lines; relative and absolute entries;
  unsafe schemes listed but not linked; escaping of titles and URLs; empty
  playlist.
- Negotiation: `Accept: text/html` gets HTML; `*/*` and no `Accept` get the
  raw M3U; `?format=raw` gets raw; both carry `Vary: Accept` and
  `Cache-Control: no-cache`. Markdown is unaffected.
- Static route: serves `playlist.js` with a JavaScript content type; refuses
  anything not in the package's static directory, including traversal.

## Docs

`docs/formatters.md`: the `playlist` renderer under `/transformer`, the
`Accept` behavior, the reserved `/_k0sngin/` prefix, and the cross-origin
limit.

## Future work

- Richer per-entry metadata (e.g. a subtitle or credit line per entry), via
  extra comment lines in the M3U that players ignore.
- A directory-as-playlist directive (`/audio`), a sibling of `/images`, taking
  order and captions from `index.ini`.

# Directory index formatters

Formatters are `index.ini` **directives** — keys beginning with `/` (e.g.
`/title`, `/all`) — that control how k0sNgin renders a directory index. They sit
alongside the plain `name = description` lines, which describe individual files.

Implemented: [`css`](#css), [`links`](#links), [`title`](#title), [`icon`](#icon),
[`all`](#all), [`ignore`](#ignore), [`images`](#images), [`template`](#template),
[`breadcrumbs`](#breadcrumbs), [`include`](#include).
Not yet implemented (parsed but ignored, logged as `Formatter not found: <key>`):
`transformer`, `sort`, `formatters`.

Formatters run in a canonical order (`css`, `links`, `title`, `images`, `icon`,
`breadcrumbs`, `include`), not the order they appear in `index.ini` — so `links`
strips its link segments before `title` splits descriptions on `:`, and `images`
filters the listing after titles/descriptions are settled.

Unless noted, `css`/`title`/`icon`/`breadcrumbs`/`include`/`ignore` **cascade**: a
directory inherits them from its parents, and a child directory's value overrides
the parent's.
`all`/`images`/`template` are **local-only**: they apply only to the directory
whose `index.ini` declares them and are never inherited by subdirectories.

## `css`

Space-separated list of stylesheet paths to include in the page `<head>`.

```
/css = /css/professional.css /portfolio/style.css
```

## `links`

Alternate-form links: description segments of the form `; [text]=target` become
extra links rendered after the entry's main link, for other forms of the same
conceptual resource.

```
/links =
resume.html = My Resume; [PDF]=resume.pdf
```

renders as **My Resume** (linking to `resume.html`) followed by
**[PDF]** (linking to `resume.pdf`). The segments are stripped from the
displayed description. Internally each file gets a `links` dict of
`{text: target}`, e.g. `{"PDF": "resume.pdf"}`.

## `title`

Page title, and per-file title/description splitting.

```
/title = Portfolio
```

Sets the page `<title>`/`<h1>`. If a file's description contains a `:` separator,
it is split into a per-file title and description
(`name = My Title : the description`). A description **without** a `:` is left
untouched — it renders identically with or without `/title`.

## `icon`

Favicon URL for the page.

```
/icon = /pictures/gallery/avatar.gif
```

## `all`

Controls **which files are listed** in the directory index. Unlike the cascading
formatters above, `/all` is **local to the directory** — it is not inherited by
subdirectories. **Whitespace is not significant.**

Three modes:

| `/all` value | Result |
|--------------|--------|
| **absent** (no `/all` line) | Render **every** entry in the directory. |
| **empty** (`/all =`) | Render **only** the files explicitly listed in this `index.ini` (the `name = …` lines) that exist on disk. |
| **glob list** (`/all = *.txt, *.png, hello.md`) | Render **exactly** the directory entries whose name matches at least one glob. |

Semantics of the glob-list mode (chosen 2026-07-02):

- The globs **define the whole displayed set.** The `name = description` lines only
  supply descriptions/order for the files that match; **a described file that
  matches no glob is not shown.**
- Globs match the **filename only** (not the path), using `fnmatch` (`*`, `?`,
  `[seq]`).
- Commas separate globs; surrounding whitespace is stripped
  (`*.txt, *.png` ≡ `*.txt,*.png`).

Examples (given a directory whose `index.ini` describes `resume.html` and
`2002-MSThesisHammel.pdf`, and which also contains `resume.pdf`, `notes.txt`):

```
# absent  -> resume.html, 2002-MSThesisHammel.pdf, resume.pdf, notes.txt (all)
/all =            # -> resume.html, 2002-MSThesisHammel.pdf (only the described)
/all = *.pdf      # -> 2002-MSThesisHammel.pdf, resume.pdf (only pdfs)
/all = *.pdf, *.txt   # -> 2002-MSThesisHammel.pdf, resume.pdf, notes.txt
```

## `ignore`

Hide entries from the directory listing. The value is a comma-separated glob
list — the **same syntax and parsing as `/all`** (shared code) — naming entries
to hide:

```
/ignore = index.ini, .*, index.html
```

- Processed **after** `/all`: `/all` selects the displayed set, `/ignore`
  subtracts from it.
- **Cascades** (unlike `/all`): a parent's globs apply to all descendants; a
  descendant's own `/ignore` overrides wholesale, and a bare `/ignore =`
  clears the inherited globs.
- Listing-only: ignored files are hidden from the index but remain directly
  fetchable by URL (as in decoupage).
- Note: decoupage's `/ignore` was space-separated; k0sNgin's is
  comma-separated for consistency with `/all` (site content updated
  2026-07-08).

## `images`

Image gallery (ported from [montage](https://k0s.org/hg/montage), the decoupage
photogallery extension). Restricts the listing to image files (by mimetype
guessed from the name — subdirectories and non-images are dropped) and prepares
them for the gallery templates. Local-only. Usually paired with
[`template`](#template).

```
/images = thumbnails, size=150x, columns=4
/template = grid.html
```

The value is a comma-separated argument string of bare flags and `key=value`
pairs:

| argument | meaning |
|----------|---------|
| `size=WxH` | Display size for `<img>` (`width`/`height` attributes). Either side may be empty: `400x`, `x550`, `160x160`. |
| `columns=N` | Grid columns for `grid.html`. Default: the number of images (one row). |
| `thumbnails` (flag) | Point `<img>` at `<thumb_dir>/<thumb_prefix><name>` **when that file already exists on disk**; the image's link still targets the full file. Missing thumbnails fall back to the full image. |
| `thumb_dir=…` | Thumbnail subdirectory (default `thumbs`). Must stay under the directory (no absolute paths, no `..`). |
| `thumb_prefix=…` | Thumbnail filename prefix (default `thumb_`). |

**Thumbnails are never generated in the request path** — k0sNgin only *uses*
thumbnails that already exist (e.g. those pre-generated by montage/decoupage).
Generation is a planned offline script (montage regenerated stale/oversized
thumbnails per request; that behavior is deliberately dropped to keep serving
CPU-free).

Each surviving file entry gets `link` (the full image) and `src` (the thumbnail
if used, else the full image); the page gets `width`, `height`, `columns`, and
`images = true` template variables.

## `template`

Selects the page template by bare filename from k0sNgin's built-in templates.
Local-only.

```
/template = strip.html
```

Built-in gallery templates (all expect `/images` in the same `index.ini`):

| template | presentation |
|----------|--------------|
| `strip.html` | Images in a vertical filmstrip, captions beneath, `<hr>` between. |
| `grid.html` | CSS grid, `columns` wide (montage used a table). |
| `sequence.html` | One image per page, web-comic style; `?index=N` plus prev/next links. |
| `background.html` | Images strip over a full-page background image; `?image=<name>` selects the background (first image by default). |

Precedence: a valid `/template` > a local `index.html` file in the directory >
the default `index.html` template. Only bare filenames that exist in the
built-in templates directory are accepted — values containing path separators
or `..` are rejected (logged, fall back to default); `/template` never loads
templates from the content tree.

## `breadcrumbs`

Full breadcrumb trail. Every directory index except the root already shows a
**parent link** (`../`, a `.parent-nav` line above the page — built-in template
behavior, not a formatter); `/breadcrumbs` upgrades it to a linked trail of all
ancestors, with the current directory shown unlinked:

```
/breadcrumbs =
```

renders (at `/pictures/gallery/`):

```
/ » pictures » gallery
```

Cascades: enabling it on a directory enables it for all descendants. A
descendant opts back out with `/breadcrumbs = off` (also `false`/`no`), which
restores the plain parent link. The root shows neither (nothing above it).
Style hooks: `nav.breadcrumbs` and `nav.parent-nav`.

## `include`

Insert an HTML fragment verbatim at the top of the page body (above the
parent-nav/breadcrumbs line and the listing) — the classic use is a site-wide
navigation header:

```
/include = site-nav.html
```

Cascades, so setting it at the site root applies it to every directory index.
The fragment is resolved by **walking up from the rendered directory to the
served root** — first hit wins, so a subtree can override an ancestor's
fragment by shipping its own copy of the file. Only relative paths inside the
served tree are allowed (no absolute paths, no `..`; fragments live in the
content tree and are therefore also fetchable as normal files). A fragment
that can't be found or read is skipped and logged, never an error.

The contents are inserted **raw** (no escaping, not rendered as a template),
into the `include_html` template variable consumed by `base.html`.

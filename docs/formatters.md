# Directory index formatters

Formatters are `index.ini` **directives** — keys beginning with `/` (e.g.
`/title`, `/all`) — that control how k0sNgin renders a directory index. They sit
alongside the plain `name = description` lines, which describe individual files.

Implemented: [`css`](#css), [`links`](#links), [`title`](#title), [`icon`](#icon),
[`all`](#all).
Not yet implemented (parsed but ignored, logged as `Formatter not found: <key>`):
`ignore`, `include`, `transformer`.

Formatters run in a canonical order (`css`, `links`, `title`, `icon`), not the
order they appear in `index.ini` — so `links` strips its link segments before
`title` splits descriptions on `:`.

Unless noted, `css`/`title`/`icon` **cascade**: a directory inherits them from its
parents, and a child directory's value overrides the parent's.

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

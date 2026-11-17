# `index.json`

Per-directory metadata, the successor to `index.ini`. An `index.ini` packs a
title, a description and links into one string and uses directives to tell the
server how to take it apart. An `index.json` names each field:

```json
{
  "version": 1,
  "title": "Portfolio",
  "entries": [
    {"name": "resume.html", "title": "My Resume", "links": {"PDF": "resume.pdf"}},
    {"name": "vision.html", "description": "Vision"},
    {"name": "drafts", "hidden": true}
  ],
  "k0sngin": {"all": false, "css": ["/css/style.css"]}
}
```

Both formats work, indefinitely, and a tree can mix them. Where a directory has
both files, `index.json` wins and the server logs a warning. The schema is
[`src/k0sngin/schema/index-v1.json`](../src/k0sngin/schema/index-v1.json).

## The file

**For any reader:**

| field | |
|---|---|
| `version` | `1`. Required: it is what marks the file as directory metadata. A file named `index.json` without an integer `version` is somebody's data, and is served and listed like any file. |
| `title` | The directory's title. |
| `link` | A URL the title links to. |
| `description` | One line about the directory. |
| `entries` | The described entries, **in display order**. |

Each entry has a `name` (a file or subdirectory here) and optionally `title`,
`description`, `links` (link text → target, for other forms of the same thing),
`tags`, and `hidden` (described, but left out of listings; still served).

**For k0sNgin**, under `"k0sngin"`. Each key is a [formatter](formatters.md) with
its arguments as values instead of a string:

| key | value | `index.ini` |
|---|---|---|
| `all` | omitted or `true`: list everything. `false`: list only `entries`. A list: exactly the names matching these globs | `/all` |
| `ignore` | list of globs; `[]` clears what was inherited | `/ignore` |
| `css` | list of stylesheet paths | `/css` |
| `icon` | favicon URL | `/icon` |
| `include` | HTML fragment filename | `/include` |
| `breadcrumbs` | `true` or `false` | `/breadcrumbs` |
| `layout` | a built-in template by stem: `grid`, `strip`, `sequence`, `background` | `/template` |
| `images` | `{"thumbnails": true, "width": 150, "height": 200, "columns": 4, "thumb_dir": "thumbs", "thumb_prefix": "thumb_"}`, all optional | `/images` |
| `audio` | `{"cover": "front.jpg", "gap": 1.5}`, or `false` to turn an inherited player off | `/audio` |
| `transformer` | `{"*.md": "markdown"}`; key order is match order; `{}` clears | `/transformer` |

Other top-level objects are other tools' namespaces. The server ignores them,
and any field it does not know. Anything that rewrites the file must keep them.

A broken `index.json` (bad JSON, or a field of the wrong type) costs the
directory its metadata, not its page: it falls back to a plain listing, and the
reason is logged.

## Inheritance

The `k0sngin` keys inherit exactly as their directives do: `all`, `images` and
`layout` apply to their own directory only; the rest pass down, nearest wins;
`transformer` merges per glob. It does not matter which format a parent uses.

**`title` is the exception.** In `index.ini`, `/title` is inherited: a directory
without one shows its parent's. An `index.json` title names its own directory
only, so:

- a directory with an `index.json` and no `title` shows its path, whatever its
  parents say;
- a directory with no metadata under an `index.json` parent shows its path;
- a directory with an `index.ini` still inherits a title from any parent, because
  its descriptions rely on `/title` being in force to be split.

A tree of `index.ini` files behaves exactly as before.

`index.json` is listed like any other file unless the directory hides
`index.ini` (`ignore`), in which case the metadata file is hidden with it.

## Converting: `k0sngin-migrate`

```
k0sngin-migrate ~/web/site                 # report what would be written
k0sngin-migrate -v ~/web/site/portfolio    # and print the JSON
k0sngin-migrate --write ~/web/site         # write index.json beside each index.ini
k0sngin-migrate --write --force DIR        # rewrite ones already converted
```

The served root is `--top-level`, else `K0SNGIN_TOP_LEVEL`; it is where
inheritance stops. Nothing is written without `--write`. `index.ini` is never
changed or removed. An existing `index.json` is skipped without `--force`, and
one that is not directory metadata is never replaced. Symlinked directories are
followed, as the server serves through them.

Because `index.json` wins, **writing one changes what the directory serves at
once.** The conversion is built so the page comes out the same:

| `index.ini` | `index.json` |
|---|---|
| `/title = Text` | `"title": "Text"` |
| `/title = Text: https://…` | `"title": "Text", "link": "https://…"` |
| `name = text` | `{"name": "name", "description": "text"}` |
| `name = Title : text`, with `/title` in force | `{"name", "title": "Title", "description": "text"}`, split at the first `:` |
| `name = : text`, with `/title` in force | `{"name", "title": "name", "description": "text"}` |
| `; [text]=target`, with `/links` in force | `"links": {"text": "target"}` |
| `/title`, `/links` as switches | nothing: the fields are named |
| each other implemented directive | its `k0sngin` key, above |
| directives the server ignores (`/up`, `/sort`, …) | verbatim under `"decoupage"` |

`/title` and `/links` count as in force when inherited, so the conversion reads
the parents first.

It differs from `index.ini` in three ways, each reported as it happens:

1. **Titles stop inheriting** (above). A directory that showed its parent's title
   shows its own path once it, or the parent, is converted.
2. **A space-separated `/all`** (`/all = *.jpg *.png`) is one glob to the server,
   matching nothing. It is converted to the list that was meant, which makes
   those entries appear.
3. **Lines the server already drops** for having no `=` are reported, not
   recovered.

Entries that describe names not in the directory are kept and reported.

# k0sNgin

A FastAPI application with a conf-file format parser.
k0sNgin is meant to be a replacement for http://k0s.org ,
in particular the [decoupage](https://pypi.org/project/decoupage/) dynamic fileserver.

The general idea: files will be served with transformations applied.
Directory indices can be displayed in a variety of formats.


## Configuration File Format

- **Conf Format Parser**: Parses Unix-style conf files with line continuation
- **Line Continuation**: Supports indented lines that continue previous values
- **Special Keys**: Handles keys starting with `/`

## Running the Application

To run the FastAPI application with uvicorn:

```bash
uvicorn k0sngin.main:app --reload
```

This will start the development server with auto-reload enabled. The application will be available at `http://localhost:8000`.

## Configuration

The application uses the `K0SNGIN_TOP_LEVEL` environment variable to determine which directory to serve files from:

- If `K0SNGIN_TOP_LEVEL` is set, files are served from that directory
- If not set, files are served from the current working directory
- The directory is printed on startup for verification

`K0SNGIN_LINKS` (optional) names a JSON file of string key-value pairs
describing intended symlinks — keys are where links live, values are their
target directories (home-relative unless absolute), e.g.
`{"web/site/stories": "docs/stories"}`. A request may resolve outside
`K0SNGIN_TOP_LEVEL` only if its real path lands under one of these targets;
nested symlinks that lead elsewhere are still refused (the whole chain is
resolved before checking). Anything other than a JSON object of strings
disables the allowlist with a warning. Unset means no symlinks out of the
tree are followed.

**Security Features (Always Enabled):**
- Path traversal protection (prevents access to files outside `K0SNGIN_TOP_LEVEL`)
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, etc.)
- Rate limiting (60 requests per minute per IP)
- API documentation endpoints disabled (`/docs`, `/redoc`, `/openapi.json`)

## Formatters

k0sNgin comes with formatters for the directory indices.


* `css`: a space-separated list of CSS paths to include
* `links`: alternate-form links — `name = My Resume; [PDF]=resume.pdf` renders
  extra links after the entry for other forms of the same resource
* `title`: title the page and allow addition title/description separation for file
* `icon`: provide URL for favicon for pages
* `all`: control **which files are listed** — absent renders everything, `/all =`
  (empty) renders only the files described in `index.ini`, and `/all = <globs>`
  (comma-separated, whitespace-insignificant, e.g. `*.txt, *.png`) renders exactly
  the entries whose filename matches a glob. Local to the directory (not cascading).

See [`docs/formatters.md`](docs/formatters.md) for the full specification.

Not yet implemented (parsed but ignored, logged as `Formatter not found: <key>`):

```
Formatter not found: ignore
Formatter not found: include
Formatter not found: transformer
```

Formatters run in a canonical order (`css`, `links`, `title`, `icon`),
regardless of their order in `index.ini`.


Run `k0s-formatters` for information on the formatters

> TODO: these should be pluggable, a la decoupage

## Usage

### Configuration Format

The parser supports the Unix conf-file format with these features:

- **Key-value pairs**: `key = value`
- **Line continuation**: Indented lines continue the previous value
- **Special keys**: Keys starting with `/` (like `/title`, `/all`)
- **Empty values**: `key = ` (empty value)
- **Orphaned lines**: Indented lines without a preceding key are reported

_Examples:_

**Basic key-value pairs:**
```ini
/title = My Title
key = value
empty =
```

**Line continuation:**
```ini
/title = My Title
    with continuation
    and more continuation
key = value
```

**Orphaned lines (reported in `_orphaned_lines`):**
```ini
    orphaned line first
key = value
    orphaned after key
```

**Complex example:**
```ini
/title = figments
absolute-power.txt = absolute power
abyss.txt = the Abyss
acting.txt = acting
```

The parser distinguishes between:
- **Valid continuations**: Indented lines that immediately follow a key-value pair
- **Orphaned lines**: Indented lines that have no preceding key or come after we've moved to a new key

**Orphaned lines are reported in a special `_orphaned_lines` key:**
```json
{
  "key": "value",
  "_orphaned_lines": "Line 1:     orphaned line first; Line 3:     orphaned after key"
}
```

### File Serving

The application can serve files from a configured directory:

- **Security**: Only files strictly within `K0SNGIN_TOP_LEVEL` are accessible
- **Directory traversal protection**: Requests for files outside the allowed directory return 404
- **Directory listing**: Not implemented (returns 501)
- **Media types**: Automatically detected by FastAPI based on file extension

**Security Features:**
- Path resolution prevents directory traversal attacks
- All requested paths are validated against the top-level directory
- Non-existent files return 404 (not 403) to avoid information disclosure


## Directory Indices

Example format:

```
{
    "description": "this is such and such a directory"
    "files": {
        "foo.txt": {
            "name": "foo",
            "description": "a text about foo",
            "datestamp": ...
        }
    }
}
```

## Docker

To build with docker:

```
docker build -t k0sngin .
```

To run and serve the `example/` directory

```
docker run -p 8000:8000 -e K0SNGIN_TOP_LEVEL='/app/example' k0sngin
```

To debug the container after building:

```
docker run k0sngin sh
```

## Site Scanning / Verification

To verify your deployment and ensure only intended files are accessible, you have several options:

### Option 1: Python Scanner (Recommended)

```bash
# Install requests if needed
pip install requests

# Scan your site
python scripts/scan_site.py http://cephalopod.ink

# With rate limit testing
python scripts/scan_site.py http://cephalopod.ink --test-rate-limit
```

### Option 2: Shell Script (Simple)

```bash
# Uses wget and curl (if available)
./scan_site.sh http://cephalopod.ink
```

### Option 3: Manual wget

```bash
# Simple recursive download
wget --recursive --no-parent --no-host-directories http://cephalopod.ink

# Then inspect the downloaded files
```

The scanners check:
- ✅ API docs are disabled (`/docs`, `/redoc`, `/openapi.json`)
- 📋 Lists all accessible files and endpoints
- 🚦 Tests rate limiting behavior

# k0sNgin

A FastAPI application with a conf-file format parser.

## Features

- **Conf Format Parser**: Parses Unix-style conf files with line continuation
- **Line Continuation**: Supports indented lines that continue previous values
- **Special Keys**: Handles keys starting with `/`
- **REST API**: FastAPI endpoints for parsing configuration content

## Running the Application

To run the FastAPI application with uvicorn:

```bash
uvicorn src.k0sngin.main:app --reload
```

This will start the development server with auto-reload enabled. The application will be available at `http://localhost:8000`.

### API Documentation

Once the server is running, you can access:
- Interactive API docs (Swagger UI): `http://localhost:8000/docs`
- Alternative API docs (ReDoc): `http://localhost:8000/redoc`

### API Endpoints

- `GET /{file_path}` - Serve files from the configured directory (main endpoint)
- `POST /parse` - Parse conf-file format content
- `GET /format-info` - Get information about the supported format

### Configuration

The application uses the `K0SNGIN_TOP_LEVEL` environment variable to determine which directory to serve files from:

- If `K0SNGIN_TOP_LEVEL` is set, files are served from that directory
- If not set, files are served from the current working directory
- The directory is printed on startup for verification

### Example Usage

```bash
# Set the directory to serve files from
export K0SNGIN_TOP_LEVEL=/path/to/your/files

# Start the server
uvicorn k0sngin.main:app --reload

# Parse configuration content
curl -X POST "http://localhost:8000/parse" \
  -H "Content-Type: application/json" \
  -d '{"content": "/title = My Title\n    with continuation\nkey = value"}'

# Get format information
curl "http://localhost:8000/format-info"

# Serve a file (e.g., foo/bar.txt)
curl "http://localhost:8000/foo/bar.txt"
```

### Expected Output

**Request:**
```bash
curl -X POST "http://localhost:8000/parse" \
  -H "Content-Type: application/json" \
  -d '{"content": "/title = My Title\n    with continuation\nkey = value"}'
```

**Response:**
```json
{
  "/title": "My Title with continuation",
  "key": "value"
}
```

### Supported Format

The parser supports the Unix conf-file format with these features:

- **Key-value pairs**: `key = value`
- **Line continuation**: Indented lines continue the previous value
- **Special keys**: Keys starting with `/` (like `/title`, `/all`)
- **Empty values**: `key = ` (empty value)
- **Orphaned lines**: Indented lines without a preceding key are reported

#### Format Examples

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

#### Parser Behavior

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

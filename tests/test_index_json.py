"""index.json: the reader, its schema, and how a directory serves from it."""

import json
import pathlib

import jsonschema
import pytest

from k0sngin import directory, index

SCHEMA = json.loads((pathlib.Path(index.__file__).parent / "schema" / "index-v1.json").read_text())


# --- reading ---

def write(tmp_path, data) -> pathlib.Path:
    path = tmp_path / "index.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


@pytest.mark.parametrize("data", [{"nodes": [1, 2]}, [1, 2, 3], {"version": "1"}, "3"])
def test_other_json_with_the_name_is_not_metadata(tmp_path, data):
    assert index.load_json(write(tmp_path, data)) is None


@pytest.mark.parametrize("data", [
    "{not json",
    {"version": 2},
    {"version": 1, "entries": "nope"},
    {"version": 1, "entries": [{"title": "no name"}]},
    {"version": 1, "entries": [{"name": "a", "links": {"PDF": 3}}]},
    {"version": 1, "k0sngin": {"all": "everything"}},
    {"version": 1, "k0sngin": {"audio": True}},
    {"version": 1, "title": 7},
])
def test_broken_metadata_is_an_error(tmp_path, data):
    with pytest.raises(index.MetadataError):
        index.load_json(write(tmp_path, data))


VALID = [
    {"version": 1},
    {"version": 1, "title": "T", "link": "https://example.org", "description": "d",
     "entries": [{"name": "a", "title": "A", "description": "d", "links": {"PDF": "a.pdf"},
                  "tags": ["x"], "hidden": True, "unknown": 1}],
     "k0sngin": {"all": False, "ignore": [], "css": ["/a.css"], "icon": "/i.gif",
                 "include": "nav.html", "breadcrumbs": True, "layout": "grid",
                 "images": {"thumbnails": True, "width": 150, "columns": 4},
                 "audio": {"cover": "c.jpg", "gap": 1.5},
                 "transformer": {"*.md": "markdown"}, "future": {"x": 1}},
     "decoupage": {"up": ".."}, "other": [1]},
    {"version": 1, "k0sngin": {"all": ["*.txt"], "audio": False}},
]


@pytest.mark.parametrize("data", VALID)
def test_the_reader_and_the_schema_accept_the_same_files(data):
    jsonschema.validate(data, SCHEMA)
    assert index.validate(data) is data


@pytest.mark.parametrize("data", [
    {"version": 2}, {"version": 1, "entries": "nope"},
    {"version": 1, "entries": [{"title": "no name"}]},
    {"version": 1, "k0sngin": {"all": "everything"}},
    {"version": 1, "k0sngin": {"audio": True}}, {"version": 1, "title": 7},
])
def test_the_reader_and_the_schema_reject_the_same_files(data):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, SCHEMA)
    with pytest.raises(index.MetadataError):
        index.validate(data)


def test_k0sngin_settings_become_formatter_arguments():
    formatters = index.from_json(VALID[1])["formatters"]
    assert formatters == {
        "title": {"title": "T", "link": "https://example.org"},
        "all": "", "ignore": "", "css": "/a.css", "icon": "/i.gif",
        "include": "nav.html", "breadcrumbs": "", "template": "grid.html",
        "images": "thumbnails, columns=4, size=150x",
        "audio": "cover=c.jpg, gap=1.5", "transformer": "*.md=markdown"}


def test_all_true_lists_everything_and_a_list_is_globs():
    assert "all" not in index.from_json({"version": 1, "k0sngin": {"all": True}})["formatters"]
    formatters = index.from_json(VALID[2])["formatters"]
    assert (formatters["all"], formatters["audio"]) == ("*.txt", "off")


def test_image_sizes(tmp_path):
    def images(options):
        return index.from_json({"version": 1, "k0sngin": {"images": options}})["formatters"]["images"]
    assert images({"height": 480}) == "size=x480"
    assert images({"width": 160, "height": 160, "thumbnails": True}) == "thumbnails, size=160x160"
    assert images({}) == ""


def test_index_json_wins_and_index_ini_is_the_fallback(site_root):
    assert index.read_index(site_root / "bothformats")["source"] == "json"
    assert index.read_index(site_root / "jsondata")["source"] == "ini"
    assert index.read_index(site_root / "docs")["source"] == "ini"
    assert index.read_index(site_root / "documents" / "plain") is None


# --- serving ---

def test_a_json_directory_shows_titles_descriptions_and_links(client):
    html = client.get("/jsondocs/").text
    assert "<h1>Docs</h1>" in html
    assert '<a href="readme.txt" class="file-link">the readme</a>' in html
    assert "a description" in html
    assert '<a href="report.html" class="file-link">The Report</a>' in html
    assert '<a href="report.pdf" class="file-alt-link">PDF</a>' in html
    assert '/json.css' in html


def test_a_description_is_never_split_again(client):
    """A colon in a named description is just a colon."""
    html = client.get("/jsondocs/").text
    assert '<a href="paper.txt" class="file-link">A Paper</a>' in html
    assert "with details: and a colon" in html
    assert "keeps: its colon" in client.get("/docs/converted/").text


def test_hidden_and_ignored_entries_are_not_listed(client):
    html = client.get("/jsondocs/").text
    assert "secret-draft.txt" not in html
    assert 'href="paper.pdf" class="file-link"' not in html     # ignored by glob
    assert client.get("/jsondocs/secret-draft.txt").status_code == 200  # still served


def test_the_metadata_file_is_hidden_where_index_ini_is(client):
    assert 'href="index.json"' not in client.get("/jsondocs/").text
    # Not ignored anywhere here, so it lists like any file, as index.ini does.
    assert 'href="index.json"' in client.get("/bothformats/").text


def test_data_named_index_json_is_an_ordinary_file(client):
    html = client.get("/jsondata/").text
    assert "<h1>Data</h1>" in html
    assert '<a href="index.json" class="file-link">the data</a>' in html
    assert client.get("/jsondata/index.json").json() == {"nodes": [1, 2, 3]}


def test_index_json_wins_over_index_ini(client):
    html = client.get("/bothformats/").text
    assert "From JSON" in html and "json description" in html
    assert "From INI" not in html and "ini description" not in html


def test_broken_metadata_falls_back_to_a_plain_listing(client):
    response = client.get("/jsonbroken/")
    assert response.status_code == 200
    assert 'href="a.txt"' in response.text


def test_markdown_rendering_can_be_asked_for_in_json(client):
    response = client.get("/jsonmd/page.md")
    assert "<h1>From JSON</h1>" in response.text


# --- how a title inherits ---

def test_a_json_title_names_its_own_directory_only(client):
    html = client.get("/jsondocs/bare/").text
    assert "<h1>Docs</h1>" not in html
    assert "<title>/jsondocs/bare/</title>" in html


def test_a_json_directory_does_not_take_an_ini_parents_title(client):
    html = client.get("/docs/converted/").text
    assert "<h1>Docs</h1>" not in html
    assert "<title>/docs/converted/</title>" in html


def test_an_ini_directory_still_inherits_the_switch_from_a_json_parent(client):
    """Its descriptions are written for the split, so it must still happen."""
    html = client.get("/jsondocs/legacy/").text
    assert '<a href="old.txt" class="file-link">Old Title</a>' in html
    assert "old description" in html
    assert "<h1>Docs</h1>" in html


def test_ini_trees_inherit_titles_as_before(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "a" / "b").mkdir(parents=True)
    (site / "index.ini").write_text("/title = Root\n/links =\n")
    monkeypatch.setattr(directory, "TOP_LEVEL_DIR", site)
    formatters = directory.collect_cascading_formatters(site / "a" / "b")
    assert formatters == {"title": "Root", "links": ""}


def test_a_nearer_json_title_stops_a_further_ini_one(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "a" / "b").mkdir(parents=True)
    (site / "index.ini").write_text("/title = Root\n/css = /root.css\n")
    (site / "a" / "index.json").write_text('{"version": 1, "title": "A"}')
    monkeypatch.setattr(directory, "TOP_LEVEL_DIR", site)
    formatters = directory.collect_cascading_formatters(site / "a" / "b")
    assert formatters == {"css": "/root.css"}

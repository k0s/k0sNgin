"""index.ini -> index.json: the mapping, and the k0sngin-migrate command."""

import io
import json
import pathlib

import jsonschema
import pytest

from k0sngin import directory, index
from k0sngin.migrate import convert, dumps
from k0sngin.scripts import migrate as cli

SCHEMA = json.loads((pathlib.Path(index.__file__).parent / "schema" / "index-v1.json").read_text())


def converted(text: str, in_force=None) -> dict:
    data, _notes = convert(text, in_force)
    jsonschema.validate(data, SCHEMA)
    return data


# --- the directory and its entries ---

def test_title_and_the_title_split():
    data = converted("/title = Docs\na.txt = The Title : the rest: with a colon\nb.txt = plain\n")
    assert data == {"version": 1, "title": "Docs", "entries": [
        {"name": "a.txt", "title": "The Title", "description": "the rest: with a colon"},
        {"name": "b.txt", "description": "plain"}]}


def test_a_title_with_a_url_becomes_a_link():
    assert converted("/title = MozBase: https://wiki.example.org/MozBase\n") == {
        "version": 1, "title": "MozBase", "link": "https://wiki.example.org/MozBase"}
    assert converted("/title = about:jhammel\n")["title"] == "about:jhammel"


def test_without_title_in_force_nothing_is_split():
    assert converted("a.txt = Not a title : just text\n")["entries"] == [
        {"name": "a.txt", "description": "Not a title : just text"}]
    # An empty /title is no title at all, exactly as the server treats it.
    assert converted("/title =\na.txt = x : y\n") == {
        "version": 1, "entries": [{"name": "a.txt", "description": "x : y"}]}


def test_an_inherited_title_still_splits_and_is_not_copied():
    data = converted("a.txt = Title : text\n", {"title": "From the parent"})
    assert data == {"version": 1, "entries": [
        {"name": "a.txt", "title": "Title", "description": "text"}]}


def test_an_empty_title_is_written_as_the_name():
    assert converted("/title = T\ntoc.js = : Table of Contents\n")["entries"] == [
        {"name": "toc.js", "title": "toc.js", "description": "Table of Contents"}]


def test_links_are_lifted_out_of_the_description():
    data = converted("/title = T\n/links =\n"
                     "a.html = A Paper : details; [PDF]=a.pdf\n"
                     "b.html = Just a link; [Source]=https://x.org/b\n")
    assert data["entries"] == [
        {"name": "a.html", "title": "A Paper", "description": "details",
         "links": {"PDF": "a.pdf"}},
        {"name": "b.html", "description": "Just a link",
         "links": {"Source": "https://x.org/b"}}]
    assert "k0sngin" not in data        # /links is only a switch


def test_without_links_in_force_the_text_is_left_alone():
    assert converted("a.html = Text; [PDF]=a.pdf\n")["entries"] == [
        {"name": "a.html", "description": "Text; [PDF]=a.pdf"}]


def test_order_and_empty_descriptions_are_kept():
    data = converted("zebra =\napple = fruit\nmango =\n")
    assert data["entries"] == [{"name": "zebra"},
                               {"name": "apple", "description": "fruit"}, {"name": "mango"}]


# --- the k0sngin namespace ---

@pytest.mark.parametrize("ini, expected", [
    ("/all =", {"all": False}),
    ("/all = *", {"all": ["*"]}),
    ("/all = *.txt, lilly.html", {"all": ["*.txt", "lilly.html"]}),
    ("/ignore = index.ini, .*, index.html", {"ignore": ["index.ini", ".*", "index.html"]}),
    ("/ignore =", {"ignore": []}),
    ("/css = /css/style.css mission.css", {"css": ["/css/style.css", "mission.css"]}),
    ("/icon = /pictures/avatar.gif", {"icon": "/pictures/avatar.gif"}),
    ("/include = site-nav.html", {"include": "site-nav.html"}),
    ("/breadcrumbs =", {"breadcrumbs": True}),
    ("/breadcrumbs = off", {"breadcrumbs": False}),
    ("/images = thumbnails, size=150x, columns=4",
     {"images": {"thumbnails": True, "width": 150, "columns": 4}}),
    ("/images = size=x480", {"images": {"height": 480}}),
    ("/images = thumbnails,size=160x160,columns=5,thumb_dir=t",
     {"images": {"thumbnails": True, "width": 160, "height": 160, "columns": 5,
                 "thumb_dir": "t"}}),
    ("/images =", {"images": {}}),
    ("/audio = cover=front.jpg, gap=1.5", {"audio": {"cover": "front.jpg", "gap": 1.5}}),
    ("/audio =", {"audio": {}}),
    ("/audio = off", {"audio": False}),
    ("/template = sequence.html", {"layout": "sequence"}),
    ("/transformer = *.gv.txt=Graphviz, *.txt=ReST,*.py=text/plain",
     {"transformer": {"*.gv.txt": "Graphviz", "*.txt": "ReST", "*.py": "text/plain"}}),
    ("/transformer =", {"transformer": {}}),
])
def test_directives(ini, expected):
    assert converted(ini + "\n")["k0sngin"] == expected


def test_transformer_order_survives():
    data = converted("/transformer = z=one,a=two,m=three\n")
    assert list(data["k0sngin"]["transformer"]) == ["z", "a", "m"]
    assert list(json.loads(dumps(data))["k0sngin"]["transformer"]) == ["z", "a", "m"]


def test_space_separated_all_is_split_and_reported():
    data, notes = convert("/all = *.wav *.url\n")
    assert data["k0sngin"]["all"] == ["*.wav", "*.url"]
    assert any("separated by spaces" in note for note in notes)
    assert convert("/all = *.wav, *.url\n")[1] == []


def test_ignored_directives_are_carried_verbatim():
    data, notes = convert("/up = ..\n/sort = order=random\n/formatters = all images\n")
    assert data == {"version": 1, "decoupage": {
        "up": "..", "sort": "order=random", "formatters": "all images"}}
    assert any("/up, /sort, /formatters" in note for note in notes)


def test_lines_the_server_drops_are_reported():
    data, notes = convert("a.wav = kept\nb.wav - lost for want of an equals sign\n")
    assert data["entries"] == [{"name": "a.wav", "description": "kept"}]
    assert any("b.wav - lost" in note for note in notes)


# --- round trip: the server reads back what the migration wrote ---

ROUND_TRIPS = [
    "/title = Docs\n/links =\nreadme.txt = the readme : a description\n"
    "notes.txt = just some notes\nreport.html = The Report; [PDF]=report.pdf\n"
    "paper.txt = A Paper : with details; [PDF]=paper.pdf\n",
    "/all = *.txt, x.html\n/ignore = index.ini\n/css = /a.css /b.css\n/icon = /i.gif\n"
    "/include = nav.html\n/breadcrumbs =\n/images = thumbnails, size=150x, columns=4\n"
    "/template = grid.html\n/audio = cover=c.jpg, gap=1.5\n"
    "/transformer = *.md=markdown,*.py=text/plain\n",
    "/all =\n/images = size=x480\n/audio = off\n/breadcrumbs = off\n",
]


@pytest.mark.parametrize("text", ROUND_TRIPS)
def test_formatters_read_back_as_they_were(text):
    """Each directive's value comes back as a string the same formatter
    parses to the same thing."""
    before = index.parse_ini(text)["formatters"]
    after = index.from_json(index.validate(convert(text)[0]))["formatters"]
    for key in ("title", "links"):
        before.pop(key, None), after.pop(key, None)

    def normal(value: str) -> list:
        return sorted(part.strip() for part in value.replace(",", " ").split())
    assert {k: normal(v) for k, v in after.items()} == {k: normal(v) for k, v in before.items()}


def test_a_migrated_directory_renders_the_same_page(tmp_path, monkeypatch):
    """The docs/ fixture, served from index.ini and then from its index.json."""
    from fastapi.templating import Jinja2Templates
    from starlette.requests import Request

    site = tmp_path / "site"
    docs = site / "docs"
    docs.mkdir(parents=True)
    for name in ("readme.txt", "notes.txt", "report.html", "report.pdf", "paper.txt", "paper.pdf"):
        (docs / name).write_text("body\n")
    (docs / "index.ini").write_text(ROUND_TRIPS[0] + "/ignore = index.ini\n")
    monkeypatch.setattr(directory, "TOP_LEVEL_DIR", site)
    templates = Jinja2Templates(directory=str(directory.TEMPLATES_DIR))

    def page() -> str:
        request = Request({"type": "http", "method": "GET", "path": "/docs/",
                           "query_string": b"", "headers": []})
        return directory.serve_directory(docs, request, templates).body.decode()

    before = page()
    assert cli.main(["--write", "--top-level", str(site), str(site)]) == 0
    assert index.read_index(docs)["source"] == "json"
    assert page() == before


# --- the command ---

@pytest.fixture
def tree(tmp_path):
    site = tmp_path / "site"
    (site / "sub").mkdir(parents=True)
    (site / "data").mkdir()
    (site / "index.ini").write_text("/title = Root\na.txt = A : first\n")
    (site / "a.txt").write_text("a\n")
    (site / "sub" / "index.ini").write_text("b.txt = B : inherits the split\ngone.txt = missing\n")
    (site / "sub" / "b.txt").write_text("b\n")
    (site / "data" / "index.ini").write_text("index.json = the data\n")
    (site / "data" / "index.json").write_text('{"nodes": []}\n')
    return site


def run(*args) -> tuple[int, str]:
    out = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(out):
        status = cli.main([str(arg) for arg in args])
    return status, out.getvalue()


def test_the_default_is_a_dry_run(tree):
    status, out = run("--top-level", tree, tree)
    assert status == 0
    assert "2 would write" in out and "1 skipped" in out and "Nothing was written" in out
    assert not (tree / "index.json").exists() and not (tree / "sub" / "index.json").exists()


def test_write_converts_using_the_cascade_and_keeps_index_ini(tree):
    status, out = run("--write", "--top-level", tree, tree)
    assert status == 0 and "2 written" in out
    assert json.loads((tree / "sub" / "index.json").read_text()) == {
        "version": 1, "entries": [
            {"name": "b.txt", "title": "B", "description": "inherits the split"},
            {"name": "gone.txt", "description": "missing"}]}
    assert "1 entries describe names not in the directory (kept): gone.txt" in out
    assert (tree / "index.ini").read_text() == "/title = Root\na.txt = A : first\n"
    assert (tree / "sub" / "index.ini").exists()
    assert not list(tree.rglob(".index-*"))


def test_data_named_index_json_is_never_replaced(tree):
    for flags in ((), ("--force",)):
        status, out = run("--write", *flags, "--top-level", tree, tree)
        assert "is not directory metadata" in out
        assert (tree / "data" / "index.json").read_text() == '{"nodes": []}\n'


def test_existing_files_are_skipped_without_force(tree):
    run("--write", "--top-level", tree, tree)
    (tree / "index.json").write_text('{"version": 1, "title": "Edited by hand"}\n')
    status, out = run("--write", "--top-level", tree, tree)
    assert "already there" in out
    assert "Edited by hand" in (tree / "index.json").read_text()
    run("--write", "--force", "--top-level", tree, tree)
    assert json.loads((tree / "index.json").read_text())["title"] == "Root"


def test_output_is_indented_by_two_spaces(tree):
    run("--write", "--top-level", tree, tree)
    assert (tree / "index.json").read_text() == """{
  "version": 1,
  "title": "Root",
  "entries": [
    {
      "name": "a.txt",
      "title": "A",
      "description": "first"
    }
  ]
}
"""


def test_non_ascii_is_written_as_itself():
    assert dumps({"version": 1, "title": "Forever — samples"}) == (
        '{\n  "version": 1,\n  "title": "Forever — samples"\n}\n')


def test_symlinked_directories_are_followed_once(tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "index.ini").write_text("c.txt = C\n")
    (tree / "linked").symlink_to(outside)
    (tree / "again").symlink_to(outside)
    status, out = run("--write", "--top-level", tree, tree)
    assert (outside / "index.json").exists()
    assert "3 written" in out


def test_a_top_level_is_required(tree, monkeypatch):
    monkeypatch.delenv("K0SNGIN_TOP_LEVEL", raising=False)
    assert cli.main([str(tree)]) == 2

"""Offline release checks for Linux-safe template and local asset references."""

from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit

import pytest

from app import app, load_materials, load_project_info


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class PageAssets(HTMLParser):
    """Collect browser dependencies, including each page's local import map."""

    def __init__(self):
        super().__init__()
        self.urls = set()
        self.imports = {}
        self.in_import_map = False
        self.import_map_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "img", "source") and attrs.get("src"):
            self.urls.add(attrs["src"])
        if tag == "link" and attrs.get("rel") in ("stylesheet", "icon", "preload"):
            self.urls.add(attrs["href"])
        if tag == "script" and attrs.get("type") == "importmap":
            self.in_import_map = True
            self.import_map_text = ""

    def handle_data(self, data):
        if self.in_import_map:
            self.import_map_text += data

    def handle_endtag(self, tag):
        if tag == "script" and self.in_import_map:
            self.imports.update(json.loads(self.import_map_text)["imports"])
            self.in_import_map = False


def assert_exact_path(path):
    """Check actual directory entries, not macOS case-insensitive existence."""
    relative = path.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        assert part in {entry.name for entry in current.iterdir()}, (
            f"Missing or incorrectly capitalized path: {relative}"
        )
        current /= part
    assert current.is_file(), f"Expected a file: {relative}"


def static_path(url):
    parsed = urlsplit(url)
    assert not parsed.scheme and not parsed.netloc, f"Nonlocal asset: {url}"
    path = unquote(parsed.path)
    assert path.startswith("/static/"), f"Unexpected asset URL: {url}"
    candidate = STATIC / path.removeprefix("/static/")
    assert_exact_path(candidate)
    return candidate


def parse_page(client, url):
    parser = PageAssets()
    parser.feed(client.get(url).get_data(as_text=True))
    return parser


@pytest.mark.parametrize("url", ["/", "/compare", "/docs", "/about", "/missing-release-page"])
def test_rendered_page_assets_exist_with_exact_case_and_are_served(url):
    client = app.test_client()
    page = parse_page(client, url)
    assert page.urls
    for asset in page.urls:
        static_path(asset)
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.data, asset


# The project uses quoted static/dynamic ES imports, not a bundler. Inspect
# imported modules recursively so Three.js's indirect core dependency is covered.
MODULE_IMPORT = re.compile(
    r"(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)[\"']([^\"']+)[\"']"
)


@pytest.mark.parametrize("url", ["/", "/compare"])
def test_local_module_import_graph_resolves_with_exact_case(url):
    client = app.test_client()
    page = parse_page(client, url)
    pending = [asset for asset in page.urls if asset.endswith(".js")]
    visited = set()
    while pending:
        asset = pending.pop()
        if asset in visited:
            continue
        visited.add(asset)
        source = static_path(asset).read_text(encoding="utf-8")
        assert client.get(asset).status_code == 200, asset
        for specifier in MODULE_IMPORT.findall(source):
            if specifier.startswith("."):
                dependency = posixpath.normpath(
                    posixpath.join(posixpath.dirname(asset), specifier)
                )
            elif specifier in page.imports:
                dependency = page.imports[specifier]
            else:
                prefixes = [key for key in page.imports
                            if key.endswith("/") and specifier.startswith(key)]
                assert prefixes, f"Unresolved import {specifier!r} in {asset}"
                prefix = max(prefixes, key=len)
                dependency = page.imports[prefix] + specifier[len(prefix):]
            static_path(dependency)
            pending.append(dependency)
    assert "/static/vendor/three/three.core.js" in visited


def test_stylesheet_urls_and_all_katex_fonts_are_present_and_served():
    client = app.test_client()
    referenced_fonts = set()
    for stylesheet in STATIC.rglob("*.css"):
        assert_exact_path(stylesheet)
        source = stylesheet.read_text(encoding="utf-8")
        for match in re.finditer(r"url\(\s*([^)]+?)\s*\)", source):
            value = match.group(1).strip("\"'")
            if value.startswith("data:"):
                continue
            assert not urlsplit(value).scheme, f"Remote stylesheet asset: {value}"
            file = stylesheet.parent / unquote(urlsplit(value).path)
            assert_exact_path(file)
            response = client.get("/static/" + file.relative_to(STATIC).as_posix())
            assert response.status_code == 200, file
            if "fonts" in file.parts:
                referenced_fonts.add(file)
    fonts = {file for file in (STATIC / "vendor/katex/fonts").iterdir() if file.is_file()}
    assert fonts
    assert fonts == referenced_fonts


def test_all_templates_load_and_local_vendor_licenses_are_preserved():
    for name in app.jinja_env.list_templates():
        assert_exact_path(ROOT / "templates" / name)
        app.jinja_env.get_template(name)
    for library in ("three", "katex"):
        license_file = STATIC / "vendor" / library / "LICENSE"
        assert_exact_path(license_file)
        assert "Copyright" in license_file.read_text(encoding="utf-8")


def test_local_json_records_remain_valid_utf8_and_team_images_resolve():
    def reject_constant(value):
        raise ValueError(f"Non-JSON constant: {value}")

    for file in (ROOT / "data").glob("*.json"):
        assert_exact_path(file)
        assert isinstance(json.loads(file.read_text(encoding="utf-8"),
                                     parse_constant=reject_constant), dict)
    assert load_materials()
    project = load_project_info()
    for member in project["team"]:
        assert_exact_path(STATIC / member["image"])

"""Page routing, shared navigation, and page-specific asset checks."""

from html.parser import HTMLParser
import json
import re

import pytest

from app import app, load_project_info


class SiteNavigationParser(HTMLParser):
    """Read the brand and primary links without mixing in page-content links."""

    def __init__(self):
        super().__init__()
        self.in_primary_nav = False
        self.brand = []
        self.links = []
        self.main_ids = []
        self.viewer_div_count = 0
        self.canvas_count = 0
        self.comparison_stages = []
        self.current_link = None
        self.current_kind = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "main":
            self.main_ids.append(attributes.get("id"))
        elif tag == "div" and attributes.get("id") == "viewer":
            self.viewer_div_count += 1
        elif tag == "canvas":
            self.canvas_count += 1
        if tag == "div" and "compare-stage" in attributes.get("class", "").split():
            self.comparison_stages.append(attributes)
        if tag == "nav" and attributes.get("aria-label") == "Primary navigation":
            self.in_primary_nav = True
        if tag == "a":
            classes = attributes.get("class", "").split()
            if "site-brand" in classes:
                self.current_kind = "brand"
            elif self.in_primary_nav:
                self.current_kind = "navigation"
            else:
                return
            self.current_link = {"attributes": attributes, "text": ""}

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            destination = self.brand if self.current_kind == "brand" else self.links
            self.current_link["text"] = " ".join(self.current_link["text"].split())
            destination.append(self.current_link)
            self.current_link = None
            self.current_kind = None
        elif tag == "nav" and self.in_primary_nav:
            self.in_primary_nav = False

    def handle_data(self, data):
        if self.current_link is not None:
            self.current_link["text"] += f" {data} "


@pytest.fixture
def client():
    return app.test_client()


@pytest.mark.parametrize(
    ("path", "title", "active_page"),
    [
        ("/", "Crystal Structure Explorer", "home"),
        ("/compare", "Compare Structures — Crystal Structure Explorer", "compare"),
        ("/docs", "Documentation — Crystal Structure Explorer", "docs"),
        ("/about", "About — Crystal Structure Explorer", "about"),
    ],
)
def test_pages_have_shared_navigation_and_correct_active_state(
    client, path, title, active_page
):
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"<title>{title}</title>" in html
    assert '/static/css/style.css' in html
    assert ('class="app-booting"' in html) == (active_page == "home")

    parser = SiteNavigationParser()
    parser.feed(html)
    assert len(parser.brand) == 1
    brand = parser.brand[0]
    assert brand["attributes"]["href"] == "/"
    assert "Crystal Structure Explorer" in brand["text"]
    assert (brand["attributes"].get("aria-current") == "page") == (
        active_page == "home"
    )

    assert [(link["text"], link["attributes"]["href"]) for link in parser.links] == [
        ("Explorer", "/"),
        ("Compare", "/compare"),
        ("Documentation", "/docs"),
        ("About", "/about"),
    ]
    for link, page_name in zip(parser.links, ("home", "compare", "docs", "about")):
        assert (link["attributes"].get("aria-current") == "page") == (
            active_page == page_name
        )
        assert ("is-active" in link["attributes"].get("class", "").split()) == (
            active_page == page_name
        )


def test_compare_page_has_four_structure_comparison_table(client):
    html = client.get("/compare").get_data(as_text=True)
    parser = SiteNavigationParser()
    parser.feed(html)
    assert parser.main_ids == ["main-content"]
    assert "Compare Crystal Structures" in html
    assert html.count('<table class="comparison-table">') == 1
    assert '<th scope="col">Property</th>' in html
    header = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert header.count('scope="col"') == 5
    for structure in ("SC", "BCC", "FCC", "HCP"):
        assert f'>{structure}</span>' in html
        assert f'>{structure}</span>' in header
    for row in (
        "Effective atoms per cell / prism",
        "Coordination number",
        "Coordination polyhedron",
        "Atomic packing factor",
        "Nearest-neighbour distance",
        "Representative material",
    ):
        assert row in html


def test_documentation_has_contents_and_main_sections(client):
    html = client.get("/docs").get_data(as_text=True)
    parser = SiteNavigationParser()
    parser.feed(html)
    assert parser.main_ids == ["main-content"]
    assert "Documentation" in html
    for section_id in (
        "getting-started",
        "visualization-modes",
        "structures",
        "hcp",
        "materials",
        "architecture",
    ):
        assert f'href="#{section_id}"' in html
        assert f'id="{section_id}"' in html
    for heading in (
        "Getting Started",
        "Visualization Modes",
        "Crystal Structures",
        "Scientific Properties",
        "Data Sources",
        "Software Architecture",
    ):
        assert heading in html
    assert "Cell Lines — All Cells" in html
    assert "Contact Diagonals" in html
    assert "not chemical bonds" in html
    assert "Neighbour Lines" in html
    assert "not chemical bond predictions" in html
    assert "cuboctahedron" in html
    assert "anticuboctahedron" in html
    assert "polyhedron follows the current geometry" in html
    assert "<h3>Fullscreen</h3>" in html
    assert "only the interactive 3D stage" in html
    assert "<kbd>Escape</kbd>" in html
    assert "selected site are preserved" in html

    toc_targets = re.findall(r'href="#([a-z-]+)"', html)
    assert len(toc_targets) == 17
    assert len(set(toc_targets)) == 17
    assert all(f'id="{target}"' in html for target in toc_targets)


def test_documentation_explains_distinct_views_and_correct_cell_accounting(client):
    html = client.get("/docs").get_data(as_text=True)
    assert 'id="visualization-modes"' in html
    for heading in ("Crystal", "Unit Cell", "Coordination", "Stacking"):
        assert f"<h3>{heading}</h3>" in html
    assert "\\frac18" in html
    assert "cubic corner sphere contributes only" in html
    assert "FCC has 12" in html
    assert "ideal HCP has 12" in html
    for sequence in ("AAA along [001]", "ABAB along [001]",
                     "ABCABC along [111]", "ABAB along [0001]"):
        assert sequence in html
    assert "neither SC nor BCC is close-packed" in html
    assert "third-layer registry" in html
    assert "Layer Separation" in html
    assert "exposed cut faces are filled" in html
    assert "does not change site coordinates, the touching radius" in html


def test_documentation_explains_advanced_display_controls_without_new_physics(client):
    html = client.get("/docs").get_data(as_text=True)
    assert "<h3>Advanced Display Controls</h3>" in html
    for control in (
        "Atom Size",
        "Color — Material / Site Role",
        "Neighbour Network",
        "Clip at Cell Walls",
        "Layer Separation",
    ):
        assert f"<dt>{control}</dt>" in html
    assert "Unit Cell has no Atom Size control" in html
    assert "using role metadata from Python" in html
    assert "not different chemical species" in html
    assert "not chemical bond predictions" in html
    assert "100% is natural crystallographic spacing" in html
    assert "the same centres and touching radius" in html


def test_documentation_distinguishes_hcp_cluster_from_scientific_supercell(client):
    html = client.get("/docs").get_data(as_text=True)
    assert "3 × 3 prism cluster" in html
    assert "nine one-prism-high educational cells" in html
    assert "not a 3 × 3 × 3 primitive scientific supercell" in html
    assert "\\mathbf T_1=2\\mathbf a_1+\\mathbf a_2" in html
    assert "\\mathbf T_2=\\mathbf a_1+2\\mathbf a_2" in html
    assert "every educational hexagonal prism" in html
    assert "HCP currently displays one educational prism" not in html


def test_about_page_presents_complete_academic_project_and_equal_team_cards(client):
    html = client.get("/about").get_data(as_text=True)
    parser = SiteNavigationParser()
    parser.feed(html)
    assert parser.main_ids == ["main-content"]
    for heading_id in (
        "about-context-heading", "about-project-heading", "about-team-heading",
        "about-technologies-heading", "about-submission-heading",
    ):
        assert f'id="{heading_id}"' in html
    assert len(re.findall(r"<h1\b", html)) == 1
    assert html.count('class="team-card"') == 2
    for value in (
        "Crystal Structure Explorer",
        "3D Interactive SC-BCC-FCC-HCP Crystal Structure Model",
        "Chandigarh University", "B.Sc. Physics", "Semester 5",
        "Solid State Physics", "24SPT-301",
        "Dr. Sumit Bhardwaj", "Dhiman Das", "24BSP70022",
        "Tanmay Sharma", "24BSP70007",
    ):
        assert value in html
    assert html.count("Project Team Member") == 2
    assert "<dt>Project Type</dt>" not in html
    assert "Team member details to be added" not in html
    assert "Dhiman Dhar Das" not in html
    assert "TEAM_MEMBER_2_NAME" not in html
    assert "TEAM_MEMBER_2_UID" not in html
    assert html.count("<script") == 1
    assert "/static/js/navigation.js" in html


def test_about_connects_exactly_five_previous_courses_without_page_specific_scripts(client):
    response = client.get("/about")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    start = html.index('aria-labelledby="about-coursework-heading"')
    end = html.index('aria-labelledby="about-submission-heading"')
    coursework = html[start:end]
    assert html.index('id="about-technologies-heading"') < start < end
    assert "Connection to Previous Coursework" in coursework
    assert coursework.count('<article class="coursework-card">') == 5
    for course in (
        "Introduction to Scientific Computing", "Introduction to Python Programming",
        "Data Visualization with Python", "Data Science with Python",
        "Web Development with Python",
    ):
        assert f"<h3>{course}</h3>" in coursework
    assert "structured scientific data handling and validation" in coursework
    assert "rather than a Python plotting library" in coursework
    assert html.count("<script") == 1
    assert "/static/js/navigation.js" in html


def test_about_acknowledges_ai_as_implementation_support_with_verification(client):
    html = client.get("/about").get_data(as_text=True)
    assert 'id="about-ai-heading"' in html
    assert "Additional Technologies &amp; AI Assistance" in html
    for technology in ("OpenAI Codex", "JavaScript", "Three.js", "WebGL", "KaTeX"):
        assert technology in html
    assert "Codex served as a development assistant" in html
    assert "scientific results were checked rather than accepted solely from AI output" in html


def test_about_metadata_has_two_complete_members_and_the_actual_technology_stack():
    """Loading the local source also confirms that project.json is valid JSON."""
    project_info = load_project_info()
    assert project_info["project"] == {
        "title": "Crystal Structure Explorer",
        "academic_title": "3D Interactive SC-BCC-FCC-HCP Crystal Structure Model",
        "institution": "Chandigarh University",
        "programme": "B.Sc. Physics",
        "semester": "Semester 5",
        "subject": "Solid State Physics",
        "course_code": "24SPT-301",
        "type": "Core-course group project",
        "submitted_to": "Dr. Sumit Bhardwaj",
    }
    assert project_info["team"] == [
        {"name": "Dhiman Das", "uid": "24BSP70022", "image": "images/team/dhiman.png"},
        {"name": "Tanmay Sharma", "uid": "24BSP70007", "image": "images/team/tanmay.png"},
    ]
    assert project_info["technologies"] == [
        "Python", "NumPy", "Flask", "HTML", "CSS", "JavaScript", "Three.js",
        "KaTeX", "pytest",
    ]


@pytest.mark.parametrize(
    ("name", "image"),
    [("Dhiman Das", "dhiman.png"), ("Tanmay Sharma", "tanmay.png")],
)
def test_about_uses_local_portraits_with_accessible_names(client, name, image):
    html = client.get("/about").get_data(as_text=True)
    image_url = f"/static/images/team/{image}"
    assert f'src="{image_url}"' in html
    assert f'alt="{name}"' in html or f'alt="Portrait of {name}"' in html
    response = client.get(image_url)
    assert response.status_code == 200
    assert response.mimetype == "image/png"


@pytest.mark.parametrize(
    ("section", "field", "invalid_value"),
    [
        ("project", "academic_title", None),
        ("project", "semester", ""),
        ("project", "course_code", 24),
        ("project", "submitted_to", " "),
        ("team", "name", None),
        ("team", "uid", ""),
        ("team", "image", None),
        ("technologies", None, []),
        ("technologies", None, ["Python", None]),
    ],
)
def test_about_metadata_rejects_missing_or_placeholder_values(
    tmp_path, section, field, invalid_value
):
    document = load_project_info()
    if section == "team":
        document["team"][1][field] = invalid_value
    elif section == "project":
        document["project"][field] = invalid_value
    else:
        document["technologies"] = invalid_value
    path = tmp_path / "project.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="project.json"):
        load_project_info(path)


def test_only_four_site_page_routes_are_registered():
    pages = {
        rule.rule for rule in app.url_map.iter_rules()
        if rule.endpoint not in ("static", "health")
        and not rule.rule.startswith("/api/")
    }
    assert pages == {"/", "/compare", "/docs", "/about"}


@pytest.mark.parametrize("path", ["/compare", "/docs", "/about"])
def test_informational_pages_skip_viewer_assets_and_markup(client, path):
    html = client.get(path).get_data(as_text=True)
    parser = SiteNavigationParser()
    parser.feed(html)
    assert "/static/js/app.js" not in html
    assert "/static/js/viewer.js" not in html
    if path == "/compare":
        assert "/static/js/compare-viewers.js" in html
        assert "/static/vendor/three/three.module.js" in html
        assert 'type="importmap"' in html
    else:
        assert "/static/js/compare-viewers.js" not in html
        assert "/static/vendor/three/" not in html
        assert 'type="importmap"' not in html
    assert parser.viewer_div_count == 0
    assert parser.canvas_count == 0


def test_compare_has_four_independent_accessible_single_unit_models(client):
    html = client.get("/compare").get_data(as_text=True)
    parser = SiteNavigationParser()
    parser.feed(html)
    stages = parser.comparison_stages
    assert [stage["data-structure"] for stage in stages] == ["SC", "BCC", "FCC", "HCP"]
    for stage in stages:
        assert "Interactive 3D model" in stage["aria-label"]
        assert stage["aria-describedby"] == "compare-interaction-hint"
        response = client.get(stage["data-model-url"])
        assert response.status_code == 200
        data = response.get_json()
        assert data["parameters"]["a"] == 3
        assert data["parameters"]["supercell_size"] == 1
        assert data["parameters"]["view"] == "crystal"
        assert "material" not in data
        expected = {"SC": (8, 12), "BCC": (9, 12), "FCC": (14, 12), "HCP": (17, 18)}
        count, edge_count = expected[stage["data-structure"]]
        assert data["display"]["site_count"] == count
        assert data["display"]["cell_grid"]["segment_count"] == edge_count
        if data["structure"] == "HCP":
            assert data["parameters"]["display_size"] == 1
    assert "Drag a model to rotate" in html
    assert "Scientific Comparison" in html
    assert html.count('class="comparison-group"') == 4
    assert "Example calculated density" in html
    assert "Primitive cell" in html
    assert "Educational cell / prism volume" in html
    assert "P6₃/mmc" in html


def test_compare_module_is_local_and_page_specific(client):
    response = client.get("/static/js/compare-viewers.js")
    assert response.status_code == 200
    for path in ("/", "/docs", "/about"):
        assert "/static/js/compare-viewers.js" not in client.get(path).get_data(as_text=True)


def test_comparison_header_helper_is_local_and_compare_only(client):
    assert client.get("/static/js/compare-table.js").status_code == 200
    assert "/static/js/compare-table.js" in client.get("/compare").get_data(as_text=True)
    for path in ("/", "/docs", "/about"):
        assert "/static/js/compare-table.js" not in client.get(path).get_data(as_text=True)


def test_page_specific_assets(client):
    home = client.get("/").get_data(as_text=True)
    assert "/static/js/app.js" in home
    assert 'type="importmap"' in home
    assert "/static/vendor/three/three.module.js" in home

    for path in ("/", "/compare", "/docs"):
        html = client.get(path).get_data(as_text=True)
        assert "/static/vendor/katex/katex.min.css" in html
        assert "/static/vendor/katex/katex.min.js" in html

    about = client.get("/about").get_data(as_text=True)
    assert "/static/vendor/katex/" not in about
    assert "/static/js/math.js" not in about
    assert client.get("/static/js/math.js").status_code == 200


@pytest.mark.parametrize("path", ["/", "/compare", "/docs", "/about"])
def test_shared_mobile_navigation_is_accessible_and_progressively_enhanced(client, path):
    html = client.get(path).get_data(as_text=True)
    assert "viewport-fit=cover" in html
    assert html.count('id="site-navigation"') == 1
    assert html.count('class="site-nav-toggle"') == 1
    assert 'aria-controls="site-navigation"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-label="Open navigation"' in html
    assert html.count("/static/js/navigation.js") == 1


def test_shared_navigation_script_is_served_locally(client):
    assert client.get("/static/js/navigation.js").status_code == 200

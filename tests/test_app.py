"""Smoke checks for the Flask page and locally served viewer assets."""

from html.parser import HTMLParser

from app import app


class ViewerToolbarParser(HTMLParser):
    """Collect native buttons and visible labels from the viewer toolbar."""

    def __init__(self):
        super().__init__()
        self.toolbar_depth = 0
        self.toolbar_label = None
        self.buttons = {}
        self.current_button = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div" and attributes.get("role") == "toolbar":
            self.toolbar_depth = 1
            self.toolbar_label = attributes.get("aria-label")
        elif tag == "div" and self.toolbar_depth:
            self.toolbar_depth += 1
        elif tag == "button" and self.toolbar_depth:
            self.current_button = attributes.get("id")
            self.buttons[self.current_button] = {"attributes": attributes, "text": ""}

    def handle_endtag(self, tag):
        if tag == "button":
            self.current_button = None
        elif tag == "div" and self.toolbar_depth:
            self.toolbar_depth -= 1

    def handle_data(self, data):
        if self.current_button:
            self.buttons[self.current_button]["text"] += data


class FullscreenControlParser(HTMLParser):
    """Read the fullscreen target and button without depending on attribute order."""

    def __init__(self):
        super().__init__()
        self.stage = None
        self.button = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div" and attributes.get("id") == "viewer-stage":
            self.stage = attributes
        elif tag == "button" and attributes.get("id") == "toggle-fullscreen":
            self.button = attributes


def test_home_page_and_assets():
    client = app.test_client()
    page = client.get("/")

    assert page.status_code == 200
    assert b"Crystal Structure Explorer" in page.data
    assert b'id="viewer"' in page.data
    assert b'<select id="structure"' in page.data
    assert b'<select id="material"' in page.data
    assert b'Custom / Generic' in page.data
    assert b'<option value="sc"' in page.data
    assert b'<option value="bcc"' in page.data
    assert b'<option value="fcc"' in page.data
    assert b'<option value="hcp"' in page.data
    assert b'id="a-slider"' in page.data
    assert b'id="a-number"' in page.data
    assert b'id="cubic-size"' in page.data
    assert b'id="ratio-slider"' in page.data
    assert b'id="ratio-number"' in page.data
    assert b'id="hcp-cluster-group"' in page.data
    assert b'id="hcp-display-size"' in page.data
    assert b'id="properties"' in page.data
    assert b'id="property-content"' in page.data
    assert b'id="selected-site"' in page.data
    assert b'id="selected-site-content"' in page.data
    assert b'id="clear-selection"' in page.data
    assert b'Click a lattice site in the 3D model to inspect its coordinates.' in page.data
    assert b"/static/css/style.css" in page.data
    assert b'type="module"' in page.data
    assert b"/static/js/app.js" in page.data
    assert b'type="importmap"' in page.data
    assert b"/static/vendor/three/three.module.js" in page.data
    assert b"/static/vendor/three/" in page.data
    assert b"/static/vendor/katex/katex.min.css" in page.data
    assert b"/static/vendor/katex/katex.min.js" in page.data
    assert b"cdn.jsdelivr.net" not in page.data

    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/js/viewer.js").status_code == 200
    assert client.get("/static/js/properties.js").status_code == 200


def test_unit_cell_selection_help_is_available_without_changing_initial_prompt():
    client = app.test_client()
    page = client.get("/")
    inspector = client.get("/static/js/properties.js")
    docs = client.get("/docs")

    # Initial Crystal view stays selectable; the client replaces this prompt
    # with the mode-specific empty state when Unit Cell is chosen.
    assert b'Click a lattice site in the 3D model to inspect its coordinates.' in page.data
    assert inspector.status_code == 200
    assert b'Site selection is disabled in Unit Cell view.' in inspector.data
    assert docs.status_code == 200
    assert b'Site selection is intentionally disabled in Unit Cell view' in docs.data


def test_redesigned_page_keeps_single_functional_dom_hooks():
    page = app.test_client().get("/").data

    # Layout changes must not duplicate IDs used by the existing controls and viewer.
    for element_id in (
        "controls",
        "view-mode-group",
        "view-crystal",
        "view-unit",
        "view-coordination",
        "view-stacking",
        "view-mode-help",
        "structure",
        "material",
        "a-slider",
        "a-number",
        "cubic-size",
        "hcp-display-size",
        "ratio-slider",
        "ratio-number",
        "viewer",
        "viewer-stage",
        "toggle-fullscreen",
        "status",
        "hud-structure",
        "toolbar-summary",
        "reset-view",
        "toggle-axes",
        "toggle-auto-rotate",
        "cell-lines-group",
        "cell-lines-outer",
        "cell-lines-all",
        "cell-lines-off",
        "contact-diagonals",
        "coordination-controls-group",
        "neighbour-lines",
        "coordination-polyhedron",
        "layer-separation-group",
        "layer-separation-slider",
        "layer-separation-number",
        "atom-size-group",
        "atom-size-slider",
        "atom-size-value",
        "color-scheme-group",
        "color-material",
        "color-role",
        "neighbour-network-group",
        "neighbour-network",
        "unit-clip-group",
        "unit-clip",
        "mode-legend",
        "properties",
        "property-content",
        "selected-site",
        "selected-site-content",
        "clear-selection",
    ):
        assert page.count(f'id="{element_id}"'.encode()) == 1

    for control_id in (
        "structure",
        "material",
        "a-slider",
        "a-number",
        "cubic-size",
        "hcp-display-size",
        "ratio-slider",
        "ratio-number",
    ):
        assert f'for="{control_id}"'.encode() in page


def test_viewer_toolbar_has_accessible_controls_and_default_toggle_states():
    parser = ViewerToolbarParser()
    parser.feed(app.test_client().get("/").get_data(as_text=True))

    assert parser.toolbar_label == "Viewer controls"
    assert set(parser.buttons) == {
        "reset-view",
        "toggle-axes",
        "toggle-auto-rotate",
    }

    for button_id, label in (
        ("reset-view", "Reset View"),
        ("toggle-axes", "Axes"),
        ("toggle-auto-rotate", "Auto-Rotate"),
    ):
        button = parser.buttons[button_id]
        assert button["attributes"]["type"] == "button"
        assert button["text"].strip() == label

    assert "aria-pressed" not in parser.buttons["reset-view"]["attributes"]
    for button_id, default in (
        ("toggle-axes", "false"),
        ("toggle-auto-rotate", "false"),
    ):
        assert parser.buttons[button_id]["attributes"]["aria-pressed"] == default


def test_fullscreen_button_targets_stable_stage_and_has_accessible_name():
    page = app.test_client().get("/").get_data(as_text=True)
    parser = FullscreenControlParser()
    parser.feed(page)

    assert '<body class="app-booting">' in page
    assert 'id="viewer-loader"' in page
    assert 'Preparing 3D viewer' in page
    assert parser.stage is not None
    assert parser.button is not None
    assert parser.button["type"] == "button"
    assert parser.button["aria-label"] == "Enter fullscreen"


def test_display_controls_are_accessible_and_start_in_outer_mode():
    page = app.test_client().get("/").get_data(as_text=True)

    assert "Cell Lines" in page
    assert 'id="cell-lines-outer" type="radio" name="cell-lines" value="outer" checked' in page
    assert 'id="cell-lines-all" type="radio" name="cell-lines" value="all"' in page
    assert 'id="cell-lines-off" type="radio" name="cell-lines" value="off"' in page
    assert 'for="cell-lines-outer">Outer</label>' in page
    assert 'for="cell-lines-all">All Cells</label>' in page
    assert 'for="cell-lines-off">Off</label>' in page
    assert 'id="contact-diagonals" type="checkbox"' in page
    assert 'for="contact-diagonals">Contact Diagonals</label>' in page
    assert "not chemical bonds" in page
    assert 'id="toggle-boundary"' not in page


def test_hcp_prism_cluster_control_is_separate_from_cubic_supercell():
    page = app.test_client().get("/").get_data(as_text=True)

    assert 'id="cubic-size"' in page
    assert 'id="hcp-cluster-group" class="control-group" hidden' in page
    assert '<label for="hcp-display-size">Prism Cluster</label>' in page
    assert 'id="hcp-display-size" name="hcp-display-size"' in page
    assert "Basal prism cluster · one prism high" in page
    for size in range(1, 5):
        assert f'<option value="{size}"' in page
        assert f">{size} × {size} prisms</option>" in page
    assert '<option value="2" selected>2 × 2 prisms</option>' in page
    assert 'id="cell-lines-all" type="radio" name="cell-lines" value="all"' in page
    assert "Individual HCP cell grid is not available" not in page

    script = app.test_client().get("/static/js/app.js").get_data(as_text=True)
    assert 'query.set("display_size", String(state.hcpDisplaySize))' in script
    assert 'size: String(state.structure === "HCP" ? 1 : state.cubicSize)' in script
    assert "controls.cellLines.all.disabled" not in script


def test_four_view_modes_and_visual_layer_separation_controls_are_present():
    page = app.test_client().get("/").get_data(as_text=True)

    for mode, label in (
        ("crystal", "Crystal"),
        ("unit", "Unit Cell"),
        ("coordination", "Coordination"),
        ("stacking", "Stacking"),
    ):
        assert f'id="view-{mode}" type="radio" name="view-mode" value="{mode}"' in page
        assert f'for="view-{mode}">{label}</label>' in page

    assert 'id="view-mode-group"' in page
    assert 'id="layer-separation-group"' in page
    assert 'id="layer-separation-slider" type="range" min="100" max="250"' in page
    assert 'id="layer-separation-number" type="number" min="100" max="250"' in page
    assert "larger values separate layers visually" in page

    script = app.test_client().get("/static/js/app.js").get_data(as_text=True)
    assert 'view: state.viewMode' in script
    assert "viewer.setLayerSeparation" in script


def test_coordination_guides_are_native_mode_only_toggles():
    client = app.test_client()
    page = client.get("/").get_data(as_text=True)
    script = client.get("/static/js/app.js").get_data(as_text=True)

    assert 'id="coordination-controls-group" class="control-group" hidden' in page
    assert 'id="neighbour-lines" type="checkbox" checked' in page
    assert 'for="neighbour-lines">Neighbour Lines</label>' in page
    assert 'id="coordination-polyhedron" type="checkbox"' in page
    assert 'for="coordination-polyhedron">Polyhedron</label>' in page
    assert 'controls.coordinationGroup.hidden = state.viewMode !== "coordination"' in script
    assert "viewer?.setNeighbourLinesVisible(viewState.neighbourLines)" in script
    assert "viewer?.setPolyhedronVisible(viewState.polyhedron)" in script


def test_advanced_visual_controls_have_native_inputs_and_defaults():
    client = app.test_client()
    page = client.get("/").get_data(as_text=True)
    script = client.get("/static/js/app.js").get_data(as_text=True)
    styles = client.get("/static/css/style.css").get_data(as_text=True)

    assert 'id="atom-size-slider" type="range" min="30" max="120" step="5" value="100"' in page
    assert 'id="atom-size-value" for="atom-size-slider">100%</output>' in page
    assert 'id="color-material" type="radio" name="color-scheme" value="material" checked' in page
    assert 'id="color-role" type="radio" name="color-scheme" value="role"' in page
    assert 'id="neighbour-network" type="checkbox"' in page
    assert 'id="unit-clip" type="checkbox" checked' in page
    for control in ("atom-size-slider", "color-material", "color-role", "neighbour-network", "unit-clip"):
        assert f'for="{control}"' in page

    assert 'controls.atomSizeGroup.hidden = state.viewMode === "unit"' in script
    assert 'controls.colorSchemeGroup.hidden = !["crystal", "unit"].includes(state.viewMode)' in script
    assert 'controls.neighbourNetworkGroup.hidden = state.viewMode !== "crystal"' in script
    assert 'controls.unitClipGroup.hidden = state.viewMode !== "unit"' in script
    assert 'viewer?.setAtomScale(viewState.atomSize)' in script
    assert 'viewer?.setNeighbourNetworkVisible(viewState.neighbourNetwork)' in script
    assert 'viewer?.setUnitClippingVisible(viewState.unitClip)' in script
    for variable in ("--viz-corner", "--viz-body-center", "--viz-face-center",
                     "--viz-basal-center", "--viz-interior"):
        assert variable in styles


def test_vendored_three_modules_are_served_locally():
    client = app.test_client()

    for path in (
        "/static/vendor/three/three.module.js",
        "/static/vendor/three/three.core.js",
        "/static/vendor/three/controls/OrbitControls.js",
        "/static/vendor/three/LICENSE",
    ):
        assert client.get(path).status_code == 200


def test_vendored_katex_and_font_are_served_locally():
    client = app.test_client()

    for path in (
        "/static/vendor/katex/katex.min.css",
        "/static/vendor/katex/katex.min.js",
        "/static/vendor/katex/fonts/KaTeX_Main-Regular.woff2",
        "/static/vendor/katex/LICENSE",
    ):
        assert client.get(path).status_code == 200

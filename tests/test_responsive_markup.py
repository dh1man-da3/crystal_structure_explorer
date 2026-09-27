"""Native, accessible responsive controls; browser layout is checked manually."""

from html.parser import HTMLParser

import pytest

from app import app


class ControlsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.details_depth = 0
        self.advanced_fields = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element_id = attrs.get("id")
        if element_id:
            self.elements[element_id] = (tag, attrs)
        if tag == "details" and element_id == "advanced-controls":
            self.details_depth = 1
        elif tag == "details" and self.details_depth:
            self.details_depth += 1
        if self.details_depth and element_id:
            self.advanced_fields.add(element_id)

    def handle_endtag(self, tag):
        if tag == "details" and self.details_depth:
            self.details_depth -= 1


def test_compact_controls_use_one_native_disclosure_without_duplicating_inputs():
    html = app.test_client().get("/").get_data(as_text=True)
    parser = ControlsParser()
    parser.feed(html)
    assert parser.elements["advanced-controls"][0] == "details"
    assert "Appearance &amp; display" in html
    for field in ("atom-size-slider", "cubic-size", "hcp-display-size",
                  "cell-lines-all", "layer-separation-slider"):
        assert field in parser.advanced_fields
        assert html.count(f'id="{field}"') == 1
    for field in ("structure", "material", "a-number", "ratio-number", "view-crystal"):
        assert field not in parser.advanced_fields


def test_numeric_fields_offer_appropriate_mobile_keyboards():
    parser = ControlsParser()
    parser.feed(app.test_client().get("/").get_data(as_text=True))
    for field, inputmode in (("a-number", "decimal"), ("ratio-number", "decimal"),
                             ("layer-separation-number", "numeric")):
        tag, attrs = parser.elements[field]
        assert tag == "input"
        assert attrs["type"] == "number"
        assert attrs["inputmode"] == inputmode


@pytest.mark.parametrize("path", ["/", "/compare"])
def test_viewers_have_visible_touch_and_pointer_instructions(path):
    html = app.test_client().get(path).get_data(as_text=True)
    assert 'class="touch-hint"' in html
    assert 'class="pointer-hint"' in html
    assert "Pinch to zoom" in html or "pinch to zoom" in html

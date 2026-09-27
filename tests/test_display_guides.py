"""Python-generated finite-cell guides, distinct from atoms and display sites."""

from collections import Counter
from itertools import chain
import json
import math

import numpy as np
import pytest

from app import app
from crystal_model import (
    generate_display_guides,
    generate_display_sites,
    nearest_neighbor_distance,
)


GRID_COUNTS = {1: 12, 2: 54, 3: 144, 4: 300}
BCC_COUNTS = {1: 4, 2: 32, 3: 108, 4: 256}
FCC_COUNTS = {1: 12, 2: 72, 3: 216, 4: 480}


def _undirected_key(segment):
    return frozenset(tuple(np.round(endpoint, 10)) for endpoint in segment.values())


def _midpoint(segment):
    return (segment["start"] + segment["end"]) / 2


@pytest.mark.parametrize("structure", ["SC", "BCC", "FCC"])
@pytest.mark.parametrize("size, expected_count", GRID_COUNTS.items())
def test_cubic_grid_has_each_unique_one_cell_edge(structure, size, expected_count):
    a = 2.5
    grid = generate_display_guides(structure, a, size)["cell_grid"]
    segments = grid["segments"]
    assert grid["supported"] is True
    assert grid["segment_count"] == len(segments) == expected_count
    assert len({_undirected_key(segment) for segment in segments}) == expected_count

    by_axis = Counter()
    all_endpoints = []
    for segment in segments:
        start, end = segment["start"], segment["end"]
        assert np.linalg.norm(end - start) == pytest.approx(a)
        difference = (end - start) / a
        np.testing.assert_allclose(difference, np.rint(difference), atol=1e-12)
        assert tuple(np.rint(difference)) in {(1.0, 0.0, 0.0),
                                              (0.0, 1.0, 0.0),
                                              (0.0, 0.0, 1.0)}
        by_axis[int(np.argmax(difference))] += 1
        all_endpoints.extend((start, end))
    assert by_axis == {axis: size * (size + 1) ** 2 for axis in range(3)}
    coefficients = np.array(all_endpoints) / a
    np.testing.assert_allclose(coefficients, np.rint(coefficients), atol=1e-12)
    assert np.min(coefficients) == pytest.approx(0)
    assert np.max(coefficients) == pytest.approx(size)


def test_size_three_grid_outlines_three_intervals_and_27_cells():
    segments = generate_display_guides("SC", 3, 3)["cell_grid"]["segments"]
    for axis in range(3):
        # One boundary edge of the block is divided into three one-cell lines.
        origin_edge = [segment for segment in segments if
                       np.allclose(np.delete(segment["start"], axis), 0) and
                       np.allclose(np.delete(segment["end"], axis), 0) and
                       segment["end"][axis] > segment["start"][axis]]
        assert len(origin_edge) == 3
        assert sorted(segment["start"][axis] for segment in origin_edge) == [0, 3, 6]
    assert len(segments) == 3 * 3 * (3 + 1) ** 2  # 3^3 conventional cells.


@pytest.mark.parametrize("size, expected_count", BCC_COUNTS.items())
def test_bcc_body_diagonals_meet_at_display_body_centres(size, expected_count):
    a = 2.8665  # Also catches accidentally hard-coded generic a=3 geometry.
    contact = generate_display_guides("BCC", a, size)["contact_diagonals"]
    segments = contact["segments"]
    assert contact["supported"] is True
    assert contact["kind"] == "body"
    assert contact["segment_count"] == len(segments) == expected_count
    assert len({_undirected_key(segment) for segment in segments}) == expected_count
    centres = {tuple(np.round(site["cartesian"], 10)) for site in
               generate_display_sites("BCC", a, size) if site["role"] == "body_center"}
    midpoints = Counter(tuple(np.round(_midpoint(segment), 10)) for segment in segments)
    assert set(midpoints) == centres
    assert set(midpoints.values()) == {4}
    for segment in segments:
        length = np.linalg.norm(segment["end"] - segment["start"])
        assert length == pytest.approx(math.sqrt(3) * a)
        assert length / 2 == pytest.approx(nearest_neighbor_distance("BCC", a))


@pytest.mark.parametrize("size, expected_count", FCC_COUNTS.items())
def test_fcc_face_diagonals_meet_at_unique_display_face_centres(size, expected_count):
    a = 3.6148
    contact = generate_display_guides("FCC", a, size)["contact_diagonals"]
    segments = contact["segments"]
    assert contact["supported"] is True
    assert contact["kind"] == "face"
    assert contact["segment_count"] == len(segments) == expected_count
    assert len({_undirected_key(segment) for segment in segments}) == expected_count
    face_centres = {tuple(np.round(site["cartesian"], 10)) for site in
                    generate_display_sites("FCC", a, size) if site["role"] == "face_center"}
    midpoints = Counter(tuple(np.round(_midpoint(segment), 10)) for segment in segments)
    assert set(midpoints) == face_centres
    assert set(midpoints.values()) == {2}  # Two full diagonals on each unique face.
    for segment in segments:
        length = np.linalg.norm(segment["end"] - segment["start"])
        assert length == pytest.approx(math.sqrt(2) * a)
        assert length / 2 == pytest.approx(nearest_neighbor_distance("FCC", a))


def test_sc_and_hcp_unsupported_contact_guides_are_explicit():
    sc = generate_display_guides("SC", 3, 3)
    hcp = generate_display_guides("HCP", 3, 1)
    assert sc["cell_grid"]["supported"] is True
    assert sc["contact_diagonals"] == {
        "supported": False, "segment_count": 0, "segments": []
    }
    assert hcp["cell_grid"]["supported"] is True
    assert hcp["cell_grid"]["segment_count"] == 18
    assert hcp["contact_diagonals"] == {
        "supported": False, "segment_count": 0, "segments": []
    }


@pytest.mark.parametrize("structure", ["SC", "BCC", "FCC"])
def test_cubic_guide_endpoints_scale_with_the_python_lattice_constant(structure):
    small = generate_display_guides(structure, 2.1, 2)
    large = generate_display_guides(structure, 4.2, 2)
    for name in ("cell_grid", "contact_diagonals"):
        assert large[name]["segment_count"] == small[name]["segment_count"]
        for small_segment, large_segment in zip(
            small[name]["segments"], large[name]["segments"]
        ):
            for endpoint in ("start", "end"):
                np.testing.assert_allclose(
                    large_segment[endpoint], 2 * small_segment[endpoint]
                )


@pytest.mark.parametrize("structure", ["SC", "BCC", "FCC", "HCP"])
def test_display_guide_input_validation(structure):
    for invalid_a in (0, -1, math.nan, math.inf):
        with pytest.raises(ValueError):
            generate_display_guides(structure, invalid_a, 1)
    for invalid_size in (0, 5, 2.5):
        with pytest.raises((TypeError, ValueError)):
            generate_display_guides(structure, 3, invalid_size)


@pytest.mark.parametrize(
    "structure, expected_contact_count, expected_kind",
    [("sc", 0, None), ("bcc", 108, "body"), ("fcc", 216, "face")],
)
def test_api_exposes_cubic_guide_segments_as_plain_json(
    structure, expected_contact_count, expected_kind
):
    response = app.test_client().get(
        "/api/structure", query_string={"structure": structure, "a": 3, "size": 3}
    )
    assert response.status_code == 200
    data = response.get_json()
    display = data["display"]
    grid = display["cell_grid"]
    contact = display["contact_diagonals"]
    assert grid["supported"] is True
    assert grid["segment_count"] == len(grid["segments"]) == 144
    assert contact["supported"] is (structure != "sc")
    assert contact["segment_count"] == len(contact["segments"]) == expected_contact_count
    if expected_kind:
        assert contact["kind"] == expected_kind
    else:
        assert "kind" not in contact
    for segment in chain(grid["segments"], contact["segments"]):
        assert set(segment) == {"start", "end"}
        for endpoint in segment.values():
            assert len(endpoint) == 3
            assert all(type(value) in (int, float) and math.isfinite(value)
                       for value in endpoint)
    assert json.loads(json.dumps(data, allow_nan=False)) == data


def test_hcp_api_retains_prism_boundary_and_exposes_grid_only():
    response = app.test_client().get("/api/structure?structure=hcp&a=3&size=1")
    assert response.status_code == 200
    display = response.get_json()["display"]
    assert len(display["boundary"]["edges"]) == 18
    assert display["cell_grid"]["supported"] is True
    assert display["cell_grid"]["segment_count"] == 18
    assert display["contact_diagonals"] == {
        "supported": False, "segment_count": 0, "segments": []
    }
    multi = app.test_client().get("/api/structure?structure=hcp&a=3&size=2")
    assert multi.status_code == 200
    assert multi.get_json()["display"]["site_count"] == 17

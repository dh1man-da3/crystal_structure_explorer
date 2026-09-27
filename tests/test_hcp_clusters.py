"""HCP educational prism tiling is separate from primitive-cell physics."""

from collections import Counter
import json
import math

import numpy as np
import pytest

from app import app
from crystal_model import (
    IDEAL_HCP_C_OVER_A,
    fractional_to_cartesian,
    generate_display_guides,
    generate_display_sites,
    generate_hcp_prism_boundary,
    generate_supercell,
    get_lattice_vectors,
)


def _point_key(point):
    return tuple(np.round(point, 10))


def _edge_key(first, second):
    return tuple(sorted((_point_key(first), _point_key(second))))


def _boundary_segment_keys(boundary):
    vertices = boundary["vertices"]
    return [_edge_key(vertices[first], vertices[second])
            for first, second in boundary["edges"]]


def _grid_segment_keys(grid):
    return [_edge_key(segment["start"], segment["end"])
            for segment in grid["segments"]]


def test_hcp_display_tiling_vectors_span_three_primitive_basal_cells():
    a = 3.2
    a1, a2, _ = get_lattice_vectors("HCP", a)
    t1, t2 = 2 * a1 + a2, a1 + 2 * a2
    assert np.linalg.norm(t1) == pytest.approx(math.sqrt(3) * a)
    assert np.linalg.norm(t2) == pytest.approx(math.sqrt(3) * a)
    assert np.dot(t1, t2) / (np.linalg.norm(t1) * np.linalg.norm(t2)) == pytest.approx(0.5)
    assert np.linalg.norm(np.cross(t1, t2)) == pytest.approx(
        3 * np.linalg.norm(np.cross(a1, a2))
    )
    # The generator actually uses these directions for adjacent prism centres.
    centers = [site["cartesian"] for site in
               generate_display_sites("HCP", a, 1, display_size=2)
               if site["role"] == "basal_center" and site["layer"] == "A-bottom"]
    assert len(centers) == 4
    assert {_point_key(center) for center in centers} == {
        _point_key(center) for center in (np.zeros(3), t1, t2, t1 + t2)
    }


@pytest.mark.parametrize(
    "size,sites,corners,basal,interior,grid,outer",
    [
        (1, 17, 12, 2, 3, 18, 18),
        (2, 52, 32, 8, 12, 54, 42),
        (3, 105, 60, 18, 27, 106, 66),
        (4, 176, 96, 32, 48, 174, 90),
    ],
)
def test_hcp_cluster_counts_roles_and_unique_coordinates(
    size, sites, corners, basal, interior, grid, outer
):
    a, ratio = 3.2094, 1.6235
    vectors = get_lattice_vectors("HCP", a, ratio)
    display = generate_display_sites("HCP", a, 1, ratio, display_size=size)
    assert len(display) == sites == 9 * size**2 + 8 * size
    assert [site["index"] for site in display] == list(range(sites))
    assert Counter(site["role"] for site in display) == {
        "corner": corners,
        "basal_center": basal,
        "interior": interior,
    }
    assert Counter(site["layer"] for site in display) == {
        "A-bottom": corners // 2 + basal // 2,
        "B": interior,
        "A-top": corners // 2 + basal // 2,
    }
    fractional = np.array([site["fractional"] for site in display])
    cartesian = np.array([site["cartesian"] for site in display])
    assert len({tuple(row) for row in fractional}) == sites
    assert len({_point_key(row) for row in cartesian}) == sites
    np.testing.assert_allclose(6 * fractional, np.round(6 * fractional))
    np.testing.assert_allclose(cartesian, fractional_to_cartesian(fractional, vectors))
    # Repeated requests must keep site IDs tied to the same coordinates.
    repeated = generate_display_sites("HCP", a, 1, ratio, display_size=size)
    np.testing.assert_allclose([site["fractional"] for site in repeated], fractional)

    guides = generate_display_guides("HCP", a, 1, ratio, display_size=size)
    cell_grid = guides["cell_grid"]
    assert cell_grid["supported"] is True
    assert cell_grid["segment_count"] == len(cell_grid["segments"]) == grid
    grid_keys = _grid_segment_keys(cell_grid)
    assert len(set(grid_keys)) == grid
    for segment in cell_grid["segments"]:
        length = np.linalg.norm(segment["end"] - segment["start"])
        assert min(abs(length - a), abs(length - a * ratio)) < 1e-9
    assert guides["contact_diagonals"] == {
        "supported": False, "segment_count": 0, "segments": []
    }

    boundary = generate_hcp_prism_boundary(a, ratio, display_size=size)
    boundary_keys = _boundary_segment_keys(boundary)
    assert len(boundary_keys) == len(set(boundary_keys)) == outer
    assert set(boundary_keys) <= set(grid_keys)
    vertices = np.array(boundary["vertices"])
    assert len({_point_key(vertex) for vertex in vertices}) == len(vertices)
    corner_points = {_point_key(site["cartesian"]) for site in display
                     if site["role"] == "corner"}
    assert {_point_key(vertex) for vertex in vertices} <= corner_points
    half = len(vertices) // 2
    assert half == 8 * size - 2
    assert sum(np.isclose(vertices[:, 2], 0)) == half
    assert sum(np.isclose(vertices[:, 2], a * ratio)) == half
    vertical = [edge for edge in boundary["edges"]
                if not np.isclose(vertices[edge[0], 2], vertices[edge[1], 2])]
    assert len(vertical) == half
    np.testing.assert_allclose(
        vertices[half:] - vertices[:half], np.tile([0, 0, a * ratio], (half, 1))
    )


def test_shared_hcp_prism_edge_is_once_in_grid_and_absent_from_outer_boundary():
    a = 3.0
    vectors = get_lattice_vectors("HCP", a)
    # Centre 0 and centre T1=2a1+a2 share the basal edge a1 -> a1+a2.
    first = fractional_to_cartesian((1, 0, 0), vectors)
    second = fractional_to_cartesian((1, 1, 0), vectors)
    shared = _edge_key(first, second)
    grid = generate_display_guides("HCP", a, 1, display_size=2)["cell_grid"]
    outer = generate_hcp_prism_boundary(a, display_size=2)
    assert _grid_segment_keys(grid).count(shared) == 1
    assert shared not in _boundary_segment_keys(outer)


@pytest.mark.parametrize("ratio", [1.2, IDEAL_HCP_C_OVER_A, 2.0])
def test_hcp_cluster_layers_and_topology_at_nonideal_ratios(ratio):
    a = 3.0
    sites = generate_display_sites("HCP", a, 1, ratio, display_size=3)
    assert len(sites) == 105
    for layer, height in (("A-bottom", 0), ("B", a * ratio / 2),
                          ("A-top", a * ratio)):
        assert all(site["cartesian"][2] == pytest.approx(height)
                   for site in sites if site["layer"] == layer)
    assert generate_display_guides("HCP", a, 1, ratio, display_size=3)[
        "cell_grid"]["segment_count"] == 106
    assert len(generate_hcp_prism_boundary(a, ratio, display_size=3)["edges"]) == 66


@pytest.mark.parametrize("invalid", [0, -1, 5, 2.5, "2", math.nan, math.inf, True])
def test_hcp_display_size_validation_is_separate_from_scientific_size(invalid):
    with pytest.raises((TypeError, ValueError)):
        generate_display_sites("HCP", 3, 1, display_size=invalid)
    with pytest.raises((TypeError, ValueError)):
        generate_display_guides("HCP", 3, 1, display_size=invalid)
    with pytest.raises((TypeError, ValueError)):
        generate_hcp_prism_boundary(3, display_size=invalid)


@pytest.mark.parametrize(
    "size,site_count,grid_count,outer_count",
    [(1, 17, 18, 18), (2, 52, 54, 42), (3, 105, 106, 66), (4, 176, 174, 90)],
)
def test_hcp_api_cluster_schema_and_intrinsic_properties_are_size_independent(
    size, site_count, grid_count, outer_count
):
    with app.test_client() as client:
        response = client.get("/api/structure", query_string={
            "structure": "hcp", "a": 3.2094, "size": 1,
            "c_over_a": 1.6235, "display_size": size, "material": "magnesium",
        })
        baseline = client.get("/api/structure", query_string={
            "structure": "hcp", "a": 3.2094, "size": 1,
            "c_over_a": 1.6235, "display_size": 1, "material": "magnesium",
        })
    assert response.status_code == baseline.status_code == 200
    data, reference = response.get_json(), baseline.get_json()
    assert data["parameters"]["supercell_size"] == 1
    assert data["parameters"]["display_size"] == size
    assert data["supercell"]["atom_count"] == 2
    assert data["cell"] == reference["cell"]
    assert data["material"] == reference["material"]
    display = data["display"]
    assert display["kind"] == "hcp_prism_cluster"
    assert display["display_size"] == size
    assert display["prism_count"] == size**2
    assert display["effective_atom_count"] == 6 * size**2
    assert display["primitive_cell_count"] == 3 * size**2
    assert display["site_count"] == len(display["sites"]) == site_count
    assert display["cell_grid"]["segment_count"] == grid_count
    assert len(display["boundary"]["edges"]) == outer_count
    assert display["contact_diagonals"]["supported"] is False
    assert display["stacking"] == {
        "sequence": "ABAB",
        "layers": [
            {"label": "A", "height_fraction": 0.0},
            {"label": "B", "height_fraction": 0.5},
            {"label": "A", "height_fraction": 1.0},
        ],
    }
    assert json.loads(json.dumps(data, allow_nan=False)) == data


def test_hcp_api_default_and_independent_scientific_size():
    with app.test_client() as client:
        data = client.get("/api/structure?structure=hcp&a=3&size=2&display_size=3")
        default = client.get("/api/structure?structure=hcp&a=3&size=2")
    assert data.status_code == default.status_code == 200
    assert data.get_json()["supercell"]["atom_count"] == 16
    assert data.get_json()["display"]["site_count"] == 105
    assert default.get_json()["display"]["site_count"] == 17
    assert default.get_json()["parameters"]["display_size"] == 1
    assert len(generate_supercell("HCP", 3, 2)) == 16


@pytest.mark.parametrize("value", ["0", "-1", "5", "2.5", "nan", "inf", "abc", ""])
def test_hcp_api_invalid_display_size_is_json_400(value):
    response = app.test_client().get(
        "/api/structure", query_string={"structure": "hcp", "a": 3, "display_size": value}
    )
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]["code"] == "invalid_parameter"


def test_cubic_api_ignores_hcp_display_size_parameter():
    with app.test_client() as client:
        regular = client.get("/api/structure?structure=fcc&a=3&size=2")
        with_extra = client.get(
            "/api/structure?structure=fcc&a=3&size=2&display_size=not-a-number"
        )
    assert regular.status_code == with_extra.status_code == 200
    assert regular.get_json() == with_extra.get_json()

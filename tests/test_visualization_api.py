"""Flask integration tests for the four educational visualization modes."""

import json
import math

import pytest

from app import app


@pytest.fixture
def client():
    return app.test_client()


@pytest.mark.parametrize("structure", ["sc", "bcc", "fcc", "hcp"])
@pytest.mark.parametrize("view", ["crystal", "unit", "coordination", "stacking"])
def test_each_structure_and_view_returns_json_geometry(client, structure, view):
    response = client.get("/api/structure", query_string={
        "structure": structure, "a": 3, "size": 1, "view": view,
        "display_size": 2 if structure == "hcp" else 1,
    })
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["parameters"]["view"] == view
    assert data["visualization"]["mode"] == view
    assert data["display"]["site_count"] == len(data["display"]["sites"])
    assert data["supercell"]["atom_count"] == len(data["supercell"]["atoms"])
    assert json.loads(json.dumps(data, allow_nan=False)) == data
    if view != "crystal":
        assert data["visualization"]["site_count"] == len(data["visualization"]["sites"])


def test_view_defaults_to_crystal_without_changing_existing_display(client):
    default = client.get("/api/structure?structure=fcc&a=3&size=2").get_json()
    explicit = client.get("/api/structure?structure=fcc&a=3&size=2&view=crystal").get_json()
    assert default == explicit
    assert default["visualization"] == {"mode": "crystal"}
    assert default["display"]["site_count"] == 63
    assert default["display"]["neighbour_network"]["segment_count"] > 0


@pytest.mark.parametrize("structure,size,display_size,ratio,degree", [
    ("sc", 3, None, None, 6),
    ("bcc", 3, None, None, 8),
    ("fcc", 3, None, None, 12),
    ("hcp", 1, 4, None, 12),
    ("hcp", 1, 4, 1.6235, 12),
])
def test_crystal_api_includes_finite_neighbour_network_for_visible_sites(
    client, structure, size, display_size, ratio, degree
):
    parameters = {"structure": structure, "a": 3.1, "size": size, "view": "crystal"}
    if display_size is not None:
        parameters["display_size"] = display_size
    if ratio is not None:
        parameters["c_over_a"] = ratio
    response = client.get("/api/structure", query_string=parameters)
    assert response.status_code == 200
    data = response.get_json()
    assert json.loads(json.dumps(data, allow_nan=False)) == data
    sites = {site["id"]: site for site in data["display"]["sites"]}
    network = data["display"]["neighbour_network"]
    assert network["supported"] is True
    assert len(network["segments"]) == network["segment_count"] > 0
    edges = set()
    degrees = {site_id: 0 for site_id in sites}
    for segment in network["segments"]:
        first, second = segment["start_site_id"], segment["end_site_id"]
        assert first in sites and second in sites and first < second
        assert (first, second) not in edges
        edges.add((first, second))
        degrees[first] += 1
        degrees[second] += 1
        assert segment["start"] == sites[first]["cartesian"]
        assert segment["end"] == sites[second]["cartesian"]
        assert math.isfinite(segment["distance"]) and segment["distance"] > 0
    assert max(degrees.values()) == degree
    if structure == "hcp" and ratio is not None:
        assert len({round(segment["distance"], 8)
                    for segment in network["segments"]}) == 2


@pytest.mark.parametrize("value", ["", "unknown", "supercell", "unit-cell"])
def test_invalid_view_is_json_400(client, value):
    response = client.get("/api/structure", query_string={
        "structure": "sc", "a": 3, "view": value,
    })
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]["code"] == "invalid_parameter"


@pytest.mark.parametrize("structure,count,planes,effective", [
    ("sc", 8, 6, 1), ("bcc", 9, 6, 2),
    ("fcc", 14, 6, 4), ("hcp", 17, 8, 6),
])
def test_unit_view_is_one_cell_independent_of_crystal_display_size(
    client, structure, count, planes, effective
):
    data = client.get("/api/structure", query_string={
        "structure": structure, "a": 3, "size": 4, "display_size": 4,
        "view": "unit",
    }).get_json()
    unit = data["visualization"]
    assert unit["site_count"] == count
    assert len(unit["clipping_planes"]) == planes
    assert unit["physical_radius"] == pytest.approx(data["cell"]["touching_radius"])
    assert unit["accounting"]["effective_atom_count"] == effective
    assert unit["boundary"]["edges"]
    if structure == "hcp":
        assert data["display"]["site_count"] == 176
        assert data["supercell"]["atom_count"] == 128


@pytest.mark.parametrize("structure,cn", [
    ("sc", 6), ("bcc", 8), ("fcc", 12), ("hcp", 12),
])
def test_coordination_view_has_one_center_and_exact_shell(client, structure, cn):
    data = client.get("/api/structure", query_string={
        "structure": structure, "a": 3, "view": "coordination",
    }).get_json()
    shell = data["visualization"]
    assert shell["coordination_number"] == cn
    assert shell["site_count"] == cn + 1
    assert len(shell["guide_segments"]) == cn
    assert shell["sites"][0]["role"] == "central"
    assert all(site["role"] == "neighbor" for site in shell["sites"][1:])
    assert shell["polyhedron"]["supported"] is True
    assert shell["polyhedron"]["vertex_count"] == cn
    assert shell["polyhedron"]["faces"]
    assert shell["polyhedron"]["edges"]
    assert sum(group["count"] for group in shell["distance_groups"]) == cn
    assert json.loads(json.dumps(shell, allow_nan=False)) == shell


@pytest.mark.parametrize("structure,direction,sequence,site_count", [
    ("sc", "[001]", "AAA…", 75),
    ("bcc", "[001]", "ABAB…", 75),
    ("fcc", "[111]", "ABCABC…", 57),
    ("hcp", "[0001]", "ABAB…", 57),
])
def test_stacking_view_reports_natural_layers(client, structure, direction, sequence,
                                               site_count):
    data = client.get("/api/structure", query_string={
        "structure": structure, "a": 3, "view": "stacking",
    }).get_json()
    stacking = data["visualization"]
    assert stacking["direction"] == direction
    assert stacking["sequence"] == sequence
    assert stacking["site_count"] == site_count
    assert len(stacking["layers"]) == 3
    assert math.isfinite(stacking["natural_spacing"])
    assert stacking["natural_spacing"] > 0


@pytest.mark.parametrize("structure,material_id,a", [
    ("sc", "alpha-polonium", 3.359),
    ("bcc", "alpha-iron", 2.8665),
    ("fcc", "copper", 3.6148),
    ("hcp", "magnesium", 3.2094),
])
def test_material_properties_are_invariant_across_visualization_modes(
    client, structure, material_id, a
):
    parameters = {
        "structure": structure, "a": a, "size": 1, "material": material_id,
    }
    if structure == "hcp":
        parameters.update(c_over_a=5.2105 / 3.2094, display_size=3)
    results = [client.get("/api/structure", query_string={**parameters, "view": view}).get_json()
               for view in ("crystal", "unit", "coordination", "stacking")]
    assert all(result["cell"] == results[0]["cell"] for result in results)
    assert all(result["material"] == results[0]["material"] for result in results)
    assert all(result["supercell"] == results[0]["supercell"] for result in results)
    assert all(result["material"]["id"] == material_id for result in results)
    if structure == "hcp":
        assert results[1]["visualization"]["site_count"] == 17
        assert results[0]["display"]["site_count"] == 105


@pytest.mark.parametrize("structure", ["sc", "bcc", "fcc", "hcp"])
def test_scientific_sections_do_not_change_with_view_mode(client, structure):
    parameters = {"structure": structure, "a": 3.2, "size": 2}
    if structure == "hcp":
        parameters.update(c_over_a=1.5, display_size=3)
    results = [client.get("/api/structure", query_string={**parameters, "view": view}).get_json()
               for view in ("crystal", "unit", "coordination", "stacking")]
    crystal_display = {key: value for key, value in results[0]["display"].items()
                       if key != "neighbour_network"}
    for result in results[1:]:
        assert result["cell"] == results[0]["cell"]
        assert result["supercell"] == results[0]["supercell"]
        assert result["display"] == crystal_display
        assert "neighbour_network" not in result["display"]

"""The comparison page must stay aligned with the scientific model and catalog."""

import pytest

from app import app, load_materials
from comparison_data import build_comparison
import crystal_model as crystal
from visualization_geometry import build_visualization


@pytest.fixture
def comparison():
    return build_comparison(load_materials())


def test_comparison_uses_model_properties(comparison):
    entries = comparison["structures"]
    assert [item["code"] for item in entries] == ["SC", "BCC", "FCC", "HCP"]
    for item in entries:
        code = item["code"]
        assert item["basis_atom_count"] == crystal.basis_atom_count(code)
        assert item["display_cell_atom_count"] == crystal.display_cell_atom_count(code)
        assert item["coordination_number"] == crystal.coordination_number(code)
        assert item["packing_factor"] == pytest.approx(crystal.packing_factor(code, 1))
        assert item["nearest_neighbor_per_a"] == pytest.approx(
            crystal.nearest_neighbor_distance(code, 1)
        )
        assert item["touching_radius_per_a"] == pytest.approx(
            crystal.touching_radius(code, 1)
        )
        assert item["single_cell_visible_site_count"] == len(
            crystal.generate_display_sites(code, 1, 1)
        )


def test_hcp_counts_and_ideal_geometry_are_explicit(comparison):
    hcp = comparison["structures"][-1]
    assert hcp["basis_atom_count"] == 2
    assert hcp["display_cell_atom_count"] == 6
    assert hcp["single_cell_visible_site_count"] == 17
    assert hcp["packing_factor"] == pytest.approx(0.7404804897)
    assert comparison["ideal_hcp_c_over_a"] == crystal.IDEAL_HCP_C_OVER_A


def test_comparison_names_ideal_coordination_polyhedra(comparison):
    assert {
        item["code"]: item["coordination_polyhedron"]
        for item in comparison["structures"]
    } == {
        "SC": "Octahedron",
        "BCC": "Cube",
        "FCC": "Cuboctahedron",
        "HCP": "Anticuboctahedron (ideal)",
    }


def test_representative_materials_come_from_catalog(comparison):
    materials = {item["structure"].upper(): item for item in load_materials()}
    for item in comparison["structures"]:
        preset = materials[item["code"]]
        assert item["material_name"] == preset["name"]
        assert item["material_symbol"] == preset["symbol"]
        assert item["space_group_symbol"] == preset["space_group"]["symbol"]
        assert item["space_group_number"] == preset["space_group"]["number"]
        assert item["material_lattice_a"] == preset["lattice"]["a_angstrom"]
        assert item["material_atomic_mass_note"] == preset.get("atomic_mass_note")
        assert item["material_conditions"] == preset["conditions"]


@pytest.mark.parametrize("code", ["SC", "BCC", "FCC", "HCP"])
def test_material_example_density_matches_authoritative_api(comparison, code):
    item = next(entry for entry in comparison["structures"] if entry["code"] == code)
    preset = next(entry for entry in load_materials()
                  if entry["structure"].upper() == code)
    query = {
        "structure": code,
        "a": item["material_lattice_a"],
        "material": preset["id"],
    }
    if code == "HCP":
        query["c_over_a"] = item["material_lattice_c_over_a"]
    response = app.test_client().get("/api/structure", query_string=query)
    assert response.status_code == 200
    data = response.get_json()
    assert item["material_density_g_cm3"] == pytest.approx(
        data["material"]["theoretical_density_g_cm3"]
    )
    assert item["material_lattice_c"] == pytest.approx(data["parameters"]["c"])
    assert item["material_lattice_c_over_a"] == pytest.approx(
        data["parameters"]["c_over_a"]
    )


def test_hcp_material_example_uses_measured_catalog_parameters(comparison):
    hcp = comparison["structures"][-1]
    magnesium = load_materials()[-1]
    assert hcp["material_lattice_c"] == magnesium["lattice"]["c_angstrom"]
    assert hcp["material_lattice_c_over_a"] == pytest.approx(
        magnesium["lattice"]["c_over_a"]
    )
    assert hcp["material_lattice_c_over_a"] != comparison["ideal_hcp_c_over_a"]


@pytest.mark.parametrize("code", ["SC", "BCC", "FCC", "HCP"])
def test_comparison_cell_volumes_follow_model_helpers(comparison, code):
    item = next(entry for entry in comparison["structures"] if entry["code"] == code)
    vectors = crystal.get_lattice_vectors(code, 1)
    assert item["scientific_cell_volume_per_a3"] == pytest.approx(
        crystal.cell_volume(vectors)
    )
    assert item["educational_cell_volume_per_a3"] == pytest.approx(
        crystal.display_cell_volume(code, 1)
    )
    if code == "HCP":
        assert item["educational_cell_volume_per_a3"] == pytest.approx(
            3 * item["scientific_cell_volume_per_a3"]
        )
        assert item["scientific_volume_tex"] != item["educational_volume_tex"]
    else:
        assert item["scientific_volume_tex"] == item["educational_volume_tex"]


@pytest.mark.parametrize("code", ["SC", "BCC", "FCC", "HCP"])
def test_comparison_stacking_agrees_with_explorer(comparison, code):
    item = next(entry for entry in comparison["structures"] if entry["code"] == code)
    stacking = build_visualization(code, 1, "stacking")
    assert stacking["sequence"] in item["stacking"]
    assert stacking["direction"] in item["stacking"]
    if code == "BCC":
        assert "not close-packed" in item["stacking"]


def test_comparison_exposes_geometry_and_material_presentation_metadata(comparison):
    for item in comparison["structures"]:
        for key in ("full_name", "packing_character", "contact_direction",
                    "site_roles", "repetition", "scientific_volume_tex",
                    "educational_volume_tex", "nearest_tex", "radius_tex"):
            assert isinstance(item[key], str) and item[key].strip()
        assert item["material_density_g_cm3"] > 0
    assert [entry["contact_direction"] for entry in comparison["structures"]] == [
        "Cube edge", "Body diagonal", "Face diagonal", "Close-packed neighbour directions"
    ]


def test_comparison_rejects_ambiguous_or_missing_presets():
    materials = load_materials()
    with pytest.raises(ValueError, match="Missing representative material"):
        build_comparison(materials[:-1])
    with pytest.raises(ValueError, match="Multiple representative presets"):
        build_comparison([*materials, materials[0]])


def test_comparison_page_uses_a_dedicated_mini_viewer_module():
    response = app.test_client().get("/compare")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Compare Crystal Structures" in html
    assert '<table class="comparison-table">' in html
    assert "Computational basis atoms" in html
    assert "Coordination polyhedron" in html
    assert "Anticuboctahedron (ideal)" in html
    assert "js/math.js" in html
    assert "js/compare-viewers.js" in html
    assert "js/viewer.js" not in html
    assert "js/app.js" not in html

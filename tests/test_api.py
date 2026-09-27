"""Flask JSON API checks; the scientific formulas are tested separately."""

from collections import Counter
from itertools import product
import json
import math

import numpy as np
import pytest

import app as flask_app
from app import app
from crystal_model import IDEAL_HCP_C_OVER_A, fractional_to_cartesian


@pytest.fixture
def client():
    return app.test_client()


@pytest.mark.parametrize(
    ("structure", "basis_count", "display_count", "coordination", "distance", "apf"),
    [
        ("sc", 1, 1, 6, 2.0, math.pi / 6),
        ("bcc", 2, 2, 8, math.sqrt(3), math.sqrt(3) * math.pi / 8),
        ("fcc", 4, 4, 12, math.sqrt(2), math.pi / (3 * math.sqrt(2))),
        ("hcp", 2, 6, 12, 2.0, math.pi / (3 * math.sqrt(2))),
    ],
)
def test_structure_response(
    client, structure, basis_count, display_count, coordination, distance, apf
):
    response = client.get(
        "/api/structure", query_string={"structure": structure, "a": "2", "size": "1"}
    )

    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["structure"] == structure.upper()
    assert data["units"]["length"] == "angstrom"
    assert data["units"]["volume"] == "angstrom^3"
    assert data["parameters"]["a"] == 2.0
    assert data["parameters"]["supercell_size"] == 1

    cell = data["cell"]
    assert len(cell["lattice_vectors"]) == 3
    assert all(len(vector) == 3 for vector in cell["lattice_vectors"])
    assert len(cell["basis_fractional"]) == basis_count
    assert cell["basis_atom_count"] == basis_count
    assert cell["display_cell_atom_count"] == display_count
    assert cell["coordination_number"] == coordination
    assert cell["nearest_neighbor_distance"] == pytest.approx(distance)
    assert cell["touching_radius"] == pytest.approx(distance / 2)
    assert cell["packing_factor"] == pytest.approx(apf)

    atoms = data["supercell"]["atoms"]
    assert data["supercell"]["atom_count"] == basis_count
    assert len(atoms) == basis_count
    assert [atom["id"] for atom in atoms] == list(range(basis_count))
    for atom in atoms:
        assert len(atom["fractional"]) == 3
        assert len(atom["cartesian"]) == 3
        assert atom["cell"] == [0, 0, 0]
        assert 0 <= atom["basis_index"] < basis_count
        assert all(type(value) in (int, float) for value in atom["cartesian"])

    if structure == "hcp":
        assert data["parameters"]["c_over_a"] == pytest.approx(IDEAL_HCP_C_OVER_A)
        assert data["parameters"]["c"] == pytest.approx(2 * IDEAL_HCP_C_OVER_A)
        assert cell["volume"] == pytest.approx(2 * math.sqrt(3) * 2 * IDEAL_HCP_C_OVER_A)
        assert cell["display_cell_volume"] == pytest.approx(3 * cell["volume"])
    else:
        assert data["parameters"]["c_over_a"] is None
        assert data["parameters"]["c"] is None
        assert cell["volume"] == pytest.approx(8)
        assert cell["display_cell_volume"] == pytest.approx(cell["volume"])

    assert "material" not in data


def test_materials_endpoint_serves_four_local_presets(client):
    response = client.get("/api/materials")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert set(data) == {"materials"}
    assert {material["id"] for material in data["materials"]} == {
        "alpha-polonium", "alpha-iron", "copper", "magnesium"
    }
    assert json.loads(json.dumps(data, allow_nan=False)) == data


@pytest.mark.parametrize(
    ("material_id", "structure", "a", "mass", "density"),
    [
        ("alpha-polonium", "sc", 3.359, 208.9824308, 9.156487),
        ("alpha-iron", "bcc", 2.8665, 55.845, 7.874220),
        ("copper", "fcc", 3.6148, 63.546, 8.936027),
        ("magnesium", "hcp", 3.2094, 24.305, 1.736669),
    ],
)
def test_material_aware_structure_response(
    client, material_id, structure, a, mass, density
):
    query = {"structure": structure, "a": a, "size": 1, "material": material_id}
    if structure == "hcp":
        query["c_over_a"] = 5.2105 / 3.2094
    response = client.get("/api/structure", query_string=query)
    assert response.status_code == 200
    data = response.get_json()
    material = data["material"]
    assert material["id"] == material_id
    assert material["name"]
    assert material["atomic_mass_g_mol"] == pytest.approx(mass)
    assert material["theoretical_density_g_cm3"] == pytest.approx(density, abs=0.00001)
    assert material["space_group"]["number"] > 0
    assert material["conditions"] and material["phase_note"]
    assert len(material["sources"]) >= 2
    if material_id == "alpha-polonium":
        assert "Po-209" in material["atomic_mass_note"]
    assert data["parameters"]["a"] == pytest.approx(a)
    assert data["cell"]["basis_atom_count"] == (2 if structure == "hcp" else
                                                    {"sc": 1, "bcc": 2, "fcc": 4}[structure])
    assert data["display"]["site_count"] == (17 if structure == "hcp" else
                                                {"sc": 8, "bcc": 9, "fcc": 14}[structure])
    if structure == "hcp":
        assert data["parameters"]["c"] == pytest.approx(5.2105)
        assert data["cell"]["display_cell_volume"] == pytest.approx(
            3 * data["cell"]["volume"]
        )


def test_material_query_preserves_authoritative_geometry_and_size_invariance(client):
    base = client.get(
        "/api/structure",
        query_string={"structure": "fcc", "a": 3.6148, "size": 1, "material": "copper"},
    ).get_json()
    larger = client.get(
        "/api/structure",
        query_string={"structure": "fcc", "a": 3.6148, "size": 3, "material": "copper"},
    ).get_json()
    changed_a = client.get(
        "/api/structure",
        query_string={"structure": "fcc", "a": 3.7, "size": 1, "material": "copper"},
    ).get_json()
    assert larger["supercell"]["atom_count"] == 108
    assert larger["cell"] == base["cell"]
    assert larger["material"] == base["material"]
    assert changed_a["parameters"]["a"] == 3.7
    assert changed_a["cell"]["volume"] == pytest.approx(3.7**3)
    assert changed_a["material"]["theoretical_density_g_cm3"] < (
        base["material"]["theoretical_density_g_cm3"]
    )


@pytest.mark.parametrize(
    ("query", "message_fragment"),
    [
        ({"structure": "fcc", "a": 3.6148, "material": "unknown"}, "Unknown material"),
        ({"structure": "bcc", "a": 2.8665, "material": "copper"}, "incompatible"),
        ({"structure": "fcc", "a": 3.6148, "material": ""}, "material"),
    ],
)
def test_material_query_errors_are_clean_400s(client, query, message_fragment):
    response = client.get("/api/structure", query_string=query)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_parameter"
    assert message_fragment in response.get_json()["error"]["message"]


def test_fcc_size_two_has_32_unique_atoms(client):
    response = client.get("/api/structure?structure=fcc&a=3.61&size=2")
    assert response.status_code == 200
    data = response.get_json()
    atoms = data["supercell"]["atoms"]
    assert data["parameters"]["supercell_size"] == 2
    assert data["supercell"]["atom_count"] == len(atoms) == 32
    assert [atom["id"] for atom in atoms] == list(range(32))
    positions = [tuple(atom["cartesian"]) for atom in atoms]
    assert len(set(positions)) == 32
    assert data["cell"]["display_cell_atom_count"] == 4


def test_sc_size_three_keeps_27_scientific_positions(client):
    response = client.get("/api/structure?structure=sc&a=3&size=3")
    assert response.status_code == 200
    data = response.get_json()

    assert data["parameters"]["supercell_size"] == 3
    atoms = data["supercell"]["atoms"]
    assert data["supercell"]["atom_count"] == len(atoms) == 27
    assert {tuple(atom["cartesian"]) for atom in atoms} == set(
        product((0.0, 3.0, 6.0), repeat=3)
    )

    # The full three-cell boundary reaches 3a, beyond the generated basis sites.
    vectors = data["cell"]["lattice_vectors"]
    assert [
        [data["parameters"]["supercell_size"] * component for component in vector]
        for vector in vectors
    ] == [[9.0, 0.0, 0.0], [0.0, 9.0, 0.0], [0.0, 0.0, 9.0]]


@pytest.mark.parametrize(
    ("structure", "scientific_count", "display_count"),
    [("sc", 27, 64), ("bcc", 54, 91), ("fcc", 108, 172)],
)
def test_cubic_size_three_has_separate_scientific_and_display_positions(
    client, structure, scientific_count, display_count
):
    response = client.get(
        "/api/structure", query_string={"structure": structure, "a": "3", "size": "3"}
    )
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()

    scientific_atoms = data["supercell"]["atoms"]
    display_sites = data["display"]["sites"]
    assert data["supercell"]["atom_count"] == len(scientific_atoms) == scientific_count
    assert data["display"]["site_count"] == len(display_sites) == display_count
    assert [site["id"] for site in display_sites] == list(range(display_count))
    assert all(len(site["fractional"]) == len(site["cartesian"]) == 3 for site in display_sites)

    # Finite-cell boundary sites supplement, rather than replace, the periodic positions.
    scientific_positions = {tuple(atom["cartesian"]) for atom in scientific_atoms}
    display_positions = {tuple(site["cartesian"]) for site in display_sites}
    assert scientific_positions <= display_positions
    assert len(display_positions) == display_count
    assert all(
        type(coordinate) in (int, float)
        for site in display_sites
        for coordinate in site["cartesian"]
    )


@pytest.mark.parametrize(
    ("structure", "expected_roles"),
    [
        ("sc", {"corner": 8}),
        ("bcc", {"corner": 8, "body_center": 1}),
        ("fcc", {"corner": 8, "face_center": 6}),
        ("hcp", {"corner": 12, "basal_center": 2, "interior": 3}),
    ],
)
def test_api_display_sites_have_selection_metadata_and_scientific_coordinates(
    client, structure, expected_roles
):
    response = client.get(
        "/api/structure", query_string={"structure": structure, "a": 3.2, "size": 1}
    )
    assert response.status_code == 200
    data = response.get_json()
    sites = data["display"]["sites"]
    vectors = data["cell"]["lattice_vectors"]
    assert [site["id"] for site in sites] == list(range(len(sites)))
    assert Counter(site["role"] for site in sites) == expected_roles
    for site in sites:
        assert len(site["fractional"]) == len(site["cartesian"]) == 3
        assert all(type(value) in (int, float) and math.isfinite(value)
                   for value in (*site["fractional"], *site["cartesian"]))
        np.testing.assert_allclose(
            site["cartesian"], fractional_to_cartesian(site["fractional"], vectors)
        )
        if structure == "hcp":
            assert site["layer"] in {"A-bottom", "B", "A-top"}
        else:
            assert "layer" not in site


@pytest.mark.parametrize(
    ("structure", "a", "size", "scientific_count", "display_count"),
    [
        ("sc", 2.5, 4, 64, 125),
        ("bcc", 4.2, 2, 16, 35),
        ("fcc", 5.0, 1, 4, 14),
    ],
)
def test_cubic_api_accepts_live_parameter_values(
    client, structure, a, size, scientific_count, display_count
):
    response = client.get(
        "/api/structure",
        query_string={"structure": structure, "a": a, "size": size},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["parameters"]["a"] == pytest.approx(a)
    assert data["parameters"]["supercell_size"] == size
    assert (
        data["supercell"]["atom_count"]
        == len(data["supercell"]["atoms"])
        == scientific_count
    )
    assert (
        data["display"]["site_count"]
        == len(data["display"]["sites"])
        == display_count
    )
    assert json.loads(json.dumps(data, allow_nan=False)) == data


def test_hcp_api_accepts_live_a_and_ratio_for_one_prism(client):
    response = client.get(
        "/api/structure",
        query_string={"structure": "hcp", "a": 3.2, "size": 1, "c_over_a": 1.5},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["parameters"]["a"] == pytest.approx(3.2)
    assert data["parameters"]["c_over_a"] == pytest.approx(1.5)
    assert data["parameters"]["c"] == pytest.approx(4.8)
    assert data["supercell"]["atom_count"] == 2
    assert data["display"]["site_count"] == len(data["display"]["sites"]) == 17
    middle_heights = [
        site["cartesian"][2]
        for site in data["display"]["sites"]
        if site["layer"] == "B"
    ]
    top_heights = [
        site["cartesian"][2]
        for site in data["display"]["sites"]
        if site["layer"] == "A-top"
    ]
    boundary_top_heights = [
        vertex[2] for vertex in data["display"]["boundary"]["vertices"][6:]
    ]
    assert middle_heights == pytest.approx([2.4] * 3)
    assert top_heights == pytest.approx([4.8] * 7)
    assert boundary_top_heights == pytest.approx([4.8] * 6)
    assert json.loads(json.dumps(data, allow_nan=False)) == data


def test_hcp_size_two_has_16_primitive_basis_atoms(client):
    response = client.get("/api/structure?structure=hcp&a=3.21&size=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["cell"]["basis_atom_count"] == 2
    assert data["cell"]["display_cell_atom_count"] == 6
    assert data["cell"]["coordination_number"] == 12
    assert data["supercell"]["atom_count"] == len(data["supercell"]["atoms"]) == 16
    assert len({tuple(atom["cartesian"]) for atom in data["supercell"]["atoms"]}) == 16
    # Scientific size and educational display size are independent.
    assert data["parameters"]["display_size"] == 1
    assert data["display"]["prism_count"] == 1
    assert data["display"]["site_count"] == 17


def test_hcp_size_one_has_separate_prism_display(client):
    response = client.get("/api/structure?structure=hcp&a=3&size=1")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()

    assert data["parameters"]["c_over_a"] == pytest.approx(IDEAL_HCP_C_OVER_A)
    assert data["parameters"]["display_size"] == 1
    assert data["cell"]["basis_atom_count"] == 2
    assert data["cell"]["display_cell_atom_count"] == 6
    assert data["supercell"]["atom_count"] == 2

    display = data["display"]
    assert display["kind"] == "hcp_prism_cluster"
    assert display["display_size"] == 1
    assert display["prism_count"] == 1
    assert display["effective_atom_count"] == 6
    assert display["primitive_cell_count"] == 3
    sites = display["sites"]
    assert display["site_count"] == len(sites) == 17
    assert [site["id"] for site in sites] == list(range(17))
    assert Counter(site["role"] for site in sites) == {
        "corner": 12,
        "basal_center": 2,
        "interior": 3,
    }
    assert Counter(site["layer"] for site in sites) == {
        "A-bottom": 7,
        "B": 3,
        "A-top": 7,
    }
    assert all(len(site["fractional"]) == len(site["cartesian"]) == 3 for site in sites)

    boundary = display["boundary"]
    assert len(boundary["vertices"]) == 12
    assert all(len(vertex) == 3 for vertex in boundary["vertices"])
    assert len(boundary["edges"]) == 18
    assert all(len(edge) == 2 and all(0 <= index < 12 for index in edge)
               for edge in boundary["edges"])
    assert len({tuple(sorted(edge)) for edge in boundary["edges"]}) == 18
    # Flask has serialized every NumPy array/scalar as ordinary JSON values.
    assert json.loads(json.dumps(data, allow_nan=False)) == data


def test_custom_hcp_ratio(client):
    response = client.get(
        "/api/structure?structure=HCP&a=3.21&size=2&c_over_a=1.5"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["parameters"]["c_over_a"] == 1.5
    assert data["parameters"]["c"] == pytest.approx(3.21 * 1.5)
    assert data["supercell"]["atom_count"] == 16


def test_custom_hcp_ratio_sets_prism_height(client):
    response = client.get(
        "/api/structure?structure=hcp&a=3.21&size=1&c_over_a=1.5"
    )
    assert response.status_code == 200
    data = response.get_json()
    height = 3.21 * 1.5
    assert data["parameters"]["c"] == pytest.approx(height)
    vertices = data["display"]["boundary"]["vertices"]
    assert [vertex[2] for vertex in vertices[:6]] == pytest.approx([0] * 6)
    assert [vertex[2] for vertex in vertices[6:]] == pytest.approx([height] * 6)


def test_default_size_and_case_insensitive_structure(client):
    upper = client.get("/api/structure?structure=FCC&a=2").get_json()
    lower = client.get("/api/structure?structure=fcc&a=2").get_json()
    assert upper == lower
    assert upper["parameters"]["supercell_size"] == 1
    assert upper["supercell"]["atom_count"] == 4


def test_c_over_a_is_ignored_for_non_hcp(client):
    response = client.get("/api/structure?structure=sc&a=2&c_over_a=not-a-number")
    assert response.status_code == 200
    assert response.get_json()["parameters"]["c_over_a"] is None


@pytest.mark.parametrize(
    "query",
    [
        "a=2",  # missing structure
        "structure=diamond&a=2",
        "structure=sc",  # missing a
        "structure=sc&a=0",
        "structure=sc&a=-2",
        "structure=sc&a=abc",
        "structure=sc&a=nan",
        "structure=sc&a=inf",
        "structure=sc&a=2&size=0",
        "structure=sc&a=2&size=-1",
        "structure=sc&a=2&size=5",
        "structure=sc&a=2&size=2.5",
        "structure=sc&a=2&size=abc",
        "structure=hcp&a=2&c_over_a=0",
        "structure=hcp&a=2&c_over_a=-1",
        "structure=hcp&a=2&c_over_a=nan",
        "structure=hcp&a=2&c_over_a=inf",
        "structure=hcp&a=2&c_over_a=abc",
    ],
)
def test_invalid_request_returns_json_400(client, query):
    response = client.get(f"/api/structure?{query}")
    assert response.status_code == 400
    assert response.is_json
    error = response.get_json()["error"]
    assert error["code"] == "invalid_parameter"
    assert isinstance(error["message"], str)
    assert error["message"]


def test_unexpected_model_failure_is_json_500_not_invalid_input(client, monkeypatch):
    def broken_model(*args):
        raise RuntimeError("private failure detail")

    monkeypatch.setattr(flask_app.crystal, "packing_factor", broken_model)
    response = client.get("/api/structure?structure=sc&a=2")
    assert response.status_code == 500
    assert response.is_json
    assert response.get_json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert b"private failure detail" not in response.data

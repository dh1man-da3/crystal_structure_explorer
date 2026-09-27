"""Checks of cell geometry, packing, atom generation, and input validation."""

from collections import Counter
import math
from itertools import product

import numpy as np
import pytest

from crystal_model import (
    AVOGADRO_CONSTANT,
    IDEAL_HCP_C_OVER_A,
    basis_atom_count,
    cell_volume,
    coordination_number,
    display_cell_atom_count,
    display_cell_volume,
    fractional_to_cartesian,
    generate_display_sites,
    generate_hcp_prism_boundary,
    generate_supercell,
    get_basis,
    get_lattice_vectors,
    nearest_neighbor_distance,
    packing_factor,
    theoretical_density,
    touching_radius,
)


@pytest.mark.parametrize(
    ("structure", "basis", "count", "coordination", "distance", "apf"),
    [
        ("SC", [[0, 0, 0]], 1, 6, 2, math.pi / 6),
        ("BCC", [[0, 0, 0], [0.5, 0.5, 0.5]], 2, 8,
         math.sqrt(3), math.sqrt(3) * math.pi / 8),
        ("FCC", [[0, 0, 0], [0, 0.5, 0.5], [0.5, 0, 0.5],
                  [0.5, 0.5, 0]], 4, 12, math.sqrt(2),
         math.pi / (3 * math.sqrt(2))),
    ],
)
def test_cubic_properties(structure, basis, count, coordination, distance, apf):
    a = 2
    np.testing.assert_allclose(get_lattice_vectors(structure, a), np.eye(3) * a)
    np.testing.assert_allclose(get_basis(structure), basis)
    assert basis_atom_count(structure) == count
    assert basis_atom_count(structure) == len(get_basis(structure))
    assert display_cell_atom_count(structure) == count
    assert coordination_number(structure) == coordination
    assert cell_volume(get_lattice_vectors(structure, a)) == pytest.approx(a**3)
    assert nearest_neighbor_distance(structure, a) == pytest.approx(distance)
    assert touching_radius(structure, a) == pytest.approx(distance / 2)
    assert packing_factor(structure, a) == pytest.approx(apf)


def test_fractional_to_cartesian_uses_row_vectors():
    vectors = np.array([[2, 0, 0], [-1, math.sqrt(3), 0], [0, 0, 4]])
    np.testing.assert_allclose(
        fractional_to_cartesian([0.5, 0.5, 0.25], vectors),
        [0.5, math.sqrt(3) / 2, 1],
    )
    np.testing.assert_allclose(
        fractional_to_cartesian([[1, 0, 0], [0, 1, 0]], vectors),
        vectors[:2],
    )


@pytest.mark.parametrize("structure,count", [("SC", 8), ("BCC", 16),
                                            ("FCC", 32)])
def test_cubic_supercells_have_unique_positions(structure, count):
    atoms = generate_supercell(structure, 2, 2)
    assert len(atoms) == count
    assert [atom["index"] for atom in atoms] == list(range(count))
    positions = np.array([atom["cartesian"] for atom in atoms])
    assert len(np.unique(np.round(positions, 12), axis=0)) == count
    for atom in atoms:
        np.testing.assert_allclose(
            atom["cartesian"],
            fractional_to_cartesian(atom["fractional"],
                                    get_lattice_vectors(structure, 2)),
        )


@pytest.mark.parametrize(
    ("structure", "size", "display_count", "scientific_count"),
    [
        ("SC", 1, 8, 1), ("SC", 2, 27, 8),
        ("SC", 3, 64, 27), ("SC", 4, 125, 64),
        ("BCC", 1, 9, 2), ("BCC", 2, 35, 16),
        ("BCC", 3, 91, 54), ("BCC", 4, 189, 128),
        ("FCC", 1, 14, 4), ("FCC", 2, 63, 32),
        ("FCC", 3, 172, 108), ("FCC", 4, 365, 256),
    ],
)
def test_cubic_display_sites_close_cells_without_changing_scientific_atoms(
    structure, size, display_count, scientific_count
):
    a = 2.75
    sites = generate_display_sites(structure, a, size)
    atoms = generate_supercell(structure, a, size)
    assert len(sites) == display_count
    assert len(atoms) == scientific_count
    assert [site["index"] for site in sites] == list(range(display_count))

    fractional = np.array([site["fractional"] for site in sites])
    cartesian = np.array([site["cartesian"] for site in sites])
    assert len({tuple(row) for row in fractional}) == display_count
    assert len({tuple(row) for row in cartesian}) == display_count
    assert np.all((0 <= fractional) & (fractional <= size))
    np.testing.assert_allclose(
        cartesian, fractional_to_cartesian(fractional,
                                            get_lattice_vectors(structure, a))
    )

    # The display includes all eight outer corners, including the far faces.
    displayed = {tuple(row) for row in fractional}
    assert set(product((0.0, float(size)), repeat=3)) <= displayed
    # Every periodic scientific position is present among the visible sites.
    assert {tuple(atom["fractional"]) for atom in atoms} <= displayed


@pytest.mark.parametrize(
    ("structure", "extra_sites"),
    [
        ("SC", []),
        ("BCC", [(0.5, 0.5, 0.5)]),
        ("FCC", [
            (0.5, 0.5, 0), (0.5, 0.5, 1),
            (0.5, 0, 0.5), (0.5, 1, 0.5),
            (0, 0.5, 0.5), (1, 0.5, 0.5),
        ]),
    ],
)
def test_single_cubic_display_cell_has_exact_corners_and_centers(
    structure, extra_sites
):
    sites = generate_display_sites(structure, 2, 1)
    expected = set(product((0.0, 1.0), repeat=3)) | set(extra_sites)
    assert {tuple(site["fractional"]) for site in sites} == expected
    assert {tuple(site["cartesian"]) for site in sites} == {
        tuple(2 * coordinate for coordinate in position) for position in expected
    }


@pytest.mark.parametrize(
    ("structure", "expected_roles"),
    [
        ("SC", {"corner": 8}),
        ("BCC", {"corner": 8, "body_center": 1}),
        ("FCC", {"corner": 8, "face_center": 6}),
    ],
)
def test_single_cubic_display_cell_has_correct_site_roles(structure, expected_roles):
    sites = generate_display_sites(structure, 3, 1)
    assert Counter(site["role"] for site in sites) == expected_roles


@pytest.mark.parametrize(
    ("structure", "size"),
    [("SC", 4), ("BCC", 4), ("FCC", 4), ("HCP", 1)],
)
def test_display_sites_have_unique_ids_and_finite_coordinates(structure, size):
    sites = generate_display_sites(structure, 3, size)
    assert [site["index"] for site in sites] == list(range(len(sites)))
    for site in sites:
        assert np.asarray(site["fractional"]).shape == (3,)
        assert np.asarray(site["cartesian"]).shape == (3,)
        assert np.all(np.isfinite(site["fractional"]))
        assert np.all(np.isfinite(site["cartesian"]))
        assert site["role"] in {
            "corner", "body_center", "face_center", "basal_center", "interior"
        }


@pytest.mark.parametrize(
    ("structure", "role", "fractional"),
    [
        ("SC", "corner", (1, 1, 1)),
        ("BCC", "body_center", (0.5, 0.5, 0.5)),
        ("FCC", "face_center", (0.5, 0.5, 0)),
        ("HCP", "interior", (2 / 3, 1 / 3, 0.5)),
    ],
)
def test_representative_display_site_coordinates_match_lattice_vectors(
    structure, role, fractional
):
    a = 3.2
    site = next(
        site for site in generate_display_sites(structure, a, 1)
        if site["role"] == role and np.allclose(site["fractional"], fractional)
    )
    np.testing.assert_allclose(
        site["cartesian"],
        fractional_to_cartesian(site["fractional"], get_lattice_vectors(structure, a)),
    )


@pytest.mark.parametrize("structure", ["SC", "BCC", "FCC"])
def test_cubic_display_and_cell_volume_scale_with_lattice_constant(structure):
    small_a, large_a, size = 2.0, 4.0, 2
    small_sites = generate_display_sites(structure, small_a, size)
    large_sites = generate_display_sites(structure, large_a, size)
    assert len(small_sites) == len(large_sites)
    np.testing.assert_allclose(
        [site["fractional"] for site in large_sites],
        [site["fractional"] for site in small_sites],
    )
    np.testing.assert_allclose(
        [site["cartesian"] for site in large_sites],
        2 * np.array([site["cartesian"] for site in small_sites]),
    )
    assert cell_volume(get_lattice_vectors(structure, large_a)) == pytest.approx(
        8 * cell_volume(get_lattice_vectors(structure, small_a))
    )


def test_cubic_display_names_are_case_insensitive():
    assert len(generate_display_sites(" fCc ", 2, 1)) == 14


@pytest.mark.parametrize(
    ("structure", "a", "size"),
    [
        ("diamond", 2, 1),
        ("SC", 0, 1), ("SC", math.nan, 1), ("SC", math.inf, 1),
        ("SC", 2, 0), ("SC", 2, 5), ("SC", 2, 1.5),
    ],
)
def test_invalid_cubic_display_parameters(structure, a, size):
    with pytest.raises((TypeError, ValueError)):
        generate_display_sites(structure, a, size)


def test_names_are_case_insensitive():
    np.testing.assert_allclose(get_basis("fCc"), get_basis("FCC"))
    assert coordination_number(" sc ") == 6


@pytest.mark.parametrize("structure", ["diamond", "", 5, None])
def test_invalid_structure(structure):
    with pytest.raises((TypeError, ValueError)):
        get_basis(structure)


@pytest.mark.parametrize("a", [0, -1, math.nan, math.inf, -math.inf, "2", True])
def test_invalid_lattice_constant(a):
    with pytest.raises((TypeError, ValueError)):
        get_lattice_vectors("SC", a)


@pytest.mark.parametrize("size", [0, -1, 1.5, 5, "2", True])
def test_invalid_supercell_size(size):
    with pytest.raises((TypeError, ValueError)):
        generate_supercell("BCC", 2, size)


@pytest.mark.parametrize("ratio", [0, -1, math.nan, math.inf, "1.6", True])
def test_invalid_hcp_ratio(ratio):
    with pytest.raises((TypeError, ValueError)):
        get_lattice_vectors("HCP", 2, ratio)


def test_invalid_coordinate_arrays():
    with pytest.raises(ValueError):
        fractional_to_cartesian([1, 2], np.eye(3))
    with pytest.raises(ValueError):
        fractional_to_cartesian([0, 0, 0], np.zeros((3, 3, 3)))
    with pytest.raises(ValueError):
        cell_volume(np.zeros((3, 3)))


def test_ideal_ratio_constant():
    assert IDEAL_HCP_C_OVER_A == pytest.approx(math.sqrt(8 / 3))


@pytest.mark.parametrize("structure", ["SC", "BCC", "FCC"])
def test_cubic_display_volume_equals_computational_volume(structure):
    assert display_cell_volume(structure, 3.2) == pytest.approx(3.2**3)


def test_hcp_display_prism_has_three_primitive_cell_volumes():
    a, c = 3.2094, 5.2105
    primitive = cell_volume(get_lattice_vectors("HCP", a, c / a))
    prism = display_cell_volume("HCP", a, c / a)
    assert primitive == pytest.approx(math.sqrt(3) * a**2 * c / 2)
    assert prism == pytest.approx(3 * primitive)
    assert prism == pytest.approx(3 * math.sqrt(3) * a**2 * c / 2)


def test_hcp_density_agrees_for_two_atom_primitive_and_six_atom_prism():
    a, c, mass = 3.2094, 5.2105, 24.305
    primitive = cell_volume(get_lattice_vectors("HCP", a, c / a))
    prism = display_cell_volume("HCP", a, c / a)
    primitive_density = 2 * mass / (AVOGADRO_CONSTANT * primitive * 1e-24)
    prism_density = 6 * mass / (AVOGADRO_CONSTANT * prism * 1e-24)
    actual = theoretical_density("HCP", a, mass, c / a)
    assert actual == pytest.approx(primitive_density)
    assert actual == pytest.approx(prism_density)
    assert actual == pytest.approx(1.738, abs=0.005)


@pytest.mark.parametrize(
    ("structure", "a", "mass", "expected"),
    [
        ("SC", 3.359, 208.9824308, 9.16),
        ("BCC", 2.8665, 55.845, 7.875),
        ("FCC", 3.6148, 63.546, 8.936),
    ],
)
def test_cubic_theoretical_densities_are_physically_reasonable(
    structure, a, mass, expected
):
    assert theoretical_density(structure, a, mass) == pytest.approx(expected, abs=0.02)


@pytest.mark.parametrize("mass", [0, -1, float("nan"), float("inf"), "55.845", True])
def test_density_rejects_invalid_atomic_mass(mass):
    with pytest.raises((ValueError, TypeError)):
        theoretical_density("BCC", 2.8665, mass)


def test_hcp_primitive_geometry_and_ideal_properties():
    a = 2.0
    ratio = IDEAL_HCP_C_OVER_A
    c = a * ratio
    vectors = get_lattice_vectors("HCP", a, ratio)

    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), [a, a, c])
    assert np.dot(vectors[0], vectors[1]) / a**2 == pytest.approx(-0.5)
    np.testing.assert_allclose(vectors[2], [0, 0, c])
    assert cell_volume(vectors) == pytest.approx(math.sqrt(3) * a**2 * c / 2)

    basis = get_basis("HCP")
    assert basis.shape == (2, 3)
    assert basis_atom_count("HCP") == len(basis)
    np.testing.assert_allclose(basis, [[0, 0, 0], [2 / 3, 1 / 3, 0.5]])
    # The B-layer site sits a/sqrt(3) across the basal plane and c/2 above.
    np.testing.assert_allclose(
        fractional_to_cartesian(basis[1], vectors),
        [a / 2, math.sqrt(3) * a / 6, c / 2],
    )
    assert basis_atom_count("HCP") == 2
    assert display_cell_atom_count("HCP") == 6  # Three primitive cells per prism.
    assert coordination_number("HCP") == 12
    assert nearest_neighbor_distance("HCP", a, ratio) == pytest.approx(a)
    assert touching_radius("HCP", a, ratio) == pytest.approx(a / 2)
    assert packing_factor("HCP", a, ratio) == pytest.approx(
        math.pi / (3 * math.sqrt(2))
    )


def test_hcp_supercell_uses_unique_primitive_basis_positions():
    atoms = generate_supercell("HCP", 2, 2)
    assert len(atoms) == 2 * 2**3 == 16
    positions = np.array([atom["cartesian"] for atom in atoms])
    assert len(np.unique(np.round(positions, 12), axis=0)) == 16
    assert atoms[0]["cell"] == (0, 0, 0)
    assert atoms[0]["basis_index"] == 0
    assert atoms[1]["basis_index"] == 1


def test_ideal_hcp_has_twelve_equal_nearest_neighbors():
    vectors = get_lattice_vectors("HCP", 1)
    basis = get_basis("HCP")
    distances = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                for basis_index, position in enumerate(basis):
                    if (i, j, k, basis_index) == (0, 0, 0, 0):
                        continue
                    offset = position + [i, j, k] - basis[0]
                    distances.append(np.linalg.norm(offset @ vectors))
    assert sum(np.isclose(distances, 1.0)) == 12


@pytest.mark.parametrize(
    ("ratio", "expected_distance"),
    [
        (1.0, math.sqrt(1 / 3 + 1 / 4)),
        (2.0, 1.0),
        (0.5, 0.5),
    ],
)
def test_nonideal_hcp_nearest_neighbor_and_packing(ratio, expected_distance):
    a = 1.0
    distance = nearest_neighbor_distance("HCP", a, ratio)
    assert distance == pytest.approx(expected_distance)
    expected_apf = 2 * (4 / 3) * math.pi * (distance / 2)**3 / (
        math.sqrt(3) * a**3 * ratio / 2
    )
    assert packing_factor("HCP", a, ratio) == pytest.approx(expected_apf)


def test_hcp_prism_display_counts_and_roles_are_not_scientific_counts():
    sites = generate_display_sites("HCP", 3, 1)
    assert len(sites) == 17
    assert [site["index"] for site in sites] == list(range(17))
    assert sum(site["role"] == "corner" for site in sites) == 12
    assert sum(site["role"] == "basal_center" for site in sites) == 2
    assert sum(site["role"] == "interior" for site in sites) == 3
    assert sum(site["layer"] == "A-bottom" for site in sites) == 7
    assert sum(site["layer"] == "B" for site in sites) == 3
    assert sum(site["layer"] == "A-top" for site in sites) == 7
    assert basis_atom_count("HCP") == 2
    scientific_atoms = generate_supercell("HCP", 3, 1)
    assert len(scientific_atoms) == 2
    assert {tuple(atom["fractional"]) for atom in scientific_atoms} <= {
        tuple(site["fractional"]) for site in sites
    }
    assert len(generate_supercell("HCP", 3, 2)) == 16
    assert display_cell_atom_count("HCP") == 6


def test_hcp_prism_basal_layers_form_regular_aligned_hexagons():
    a = 3.0
    c = a * IDEAL_HCP_C_OVER_A
    sites = generate_display_sites("HCP", a, 1)
    bottom = np.array([site["cartesian"] for site in sites
                       if site["layer"] == "A-bottom" and site["role"] == "corner"])
    top = np.array([site["cartesian"] for site in sites
                    if site["layer"] == "A-top" and site["role"] == "corner"])
    bottom_center = next(site["cartesian"] for site in sites
                         if site["layer"] == "A-bottom" and site["role"] == "basal_center")
    top_center = next(site["cartesian"] for site in sites
                      if site["layer"] == "A-top" and site["role"] == "basal_center")

    np.testing.assert_allclose(np.linalg.norm(bottom - bottom_center, axis=1), a)
    np.testing.assert_allclose(np.linalg.norm(top - top_center, axis=1), a)
    np.testing.assert_allclose(
        np.linalg.norm(np.roll(bottom, -1, axis=0) - bottom, axis=1), a
    )
    np.testing.assert_allclose(
        np.linalg.norm(np.roll(top, -1, axis=0) - top, axis=1), a
    )
    np.testing.assert_allclose(top - bottom, np.tile([0, 0, c], (6, 1)))
    np.testing.assert_allclose(top_center - bottom_center, [0, 0, c])


def test_hcp_prism_middle_sites_match_basis_and_ideal_contacts():
    a = 3.0
    c = a * IDEAL_HCP_C_OVER_A
    sites = generate_display_sites("HCP", a, 1)
    middle_sites = [site for site in sites if site["role"] == "interior"]
    middle = np.array([site["cartesian"] for site in middle_sites])
    bottom = np.array([site["cartesian"] for site in sites
                       if site["layer"] == "A-bottom"])
    top = np.array([site["cartesian"] for site in sites
                    if site["layer"] == "A-top"])
    polygon = bottom[:6, :2]

    np.testing.assert_allclose(middle[:, 2], c / 2)
    assert any(np.allclose(site["fractional"], get_basis("HCP")[1])
               for site in middle_sites)
    np.testing.assert_allclose(
        np.linalg.norm(np.roll(middle, -1, axis=0) - middle, axis=1), a
    )
    for point in middle:
        # A point is inside this counterclockwise convex hexagon when it is
        # to the left of every directed boundary edge.
        for index in range(6):
            edge = polygon[(index + 1) % 6] - polygon[index]
            offset = point[:2] - polygon[index]
            cross_z = edge[0] * offset[1] - edge[1] * offset[0]
            assert cross_z > 0
        # An ideal B atom touches three A atoms below and three above.
        assert sum(np.isclose(np.linalg.norm(bottom - point, axis=1), a)) == 3
        assert sum(np.isclose(np.linalg.norm(top - point, axis=1), a)) == 3


def test_hcp_prism_boundary_has_eighteen_edges_through_corner_sites():
    a = 2.75
    boundary = generate_hcp_prism_boundary(a)
    vertices = boundary["vertices"]
    edges = boundary["edges"]
    assert vertices.shape == (12, 3)
    assert len(edges) == 18
    assert len({tuple(sorted(edge)) for edge in edges}) == 18
    assert all(len(edge) == 2 and 0 <= index < 12
               for edge in edges for index in edge)
    np.testing.assert_allclose(vertices[:6, 2], 0)
    np.testing.assert_allclose(vertices[6:, 2], a * IDEAL_HCP_C_OVER_A)
    corner_sites = [site["cartesian"] for site in generate_display_sites("HCP", a, 1)
                    if site["role"] == "corner"]
    assert {tuple(position) for position in vertices} == {
        tuple(position) for position in corner_sites
    }


def test_hcp_prism_sites_are_unique_and_use_tested_coordinate_conversion():
    a = 2.7
    ratio = 1.8
    sites = generate_display_sites("HCP", a, 1, ratio)
    fractional = np.array([site["fractional"] for site in sites])
    cartesian = np.array([site["cartesian"] for site in sites])
    assert len({tuple(row) for row in fractional}) == 17
    assert len({tuple(row) for row in cartesian}) == 17
    np.testing.assert_allclose(
        cartesian, fractional_to_cartesian(fractional,
                                            get_lattice_vectors("HCP", a, ratio))
    )
    boundary = generate_hcp_prism_boundary(a, ratio)
    np.testing.assert_allclose(boundary["vertices"][6:, 2], a * ratio)


def test_hcp_prism_scales_with_a_at_fixed_ratio():
    ratio = 1.5
    small_a, large_a = 2.0, 4.0
    small_sites = generate_display_sites("HCP", small_a, 1, ratio)
    large_sites = generate_display_sites("HCP", large_a, 1, ratio)
    assert len(small_sites) == len(large_sites) == 17
    np.testing.assert_allclose(
        [site["fractional"] for site in large_sites],
        [site["fractional"] for site in small_sites],
    )
    np.testing.assert_allclose(
        [site["cartesian"] for site in large_sites],
        2 * np.array([site["cartesian"] for site in small_sites]),
    )
    np.testing.assert_allclose(
        get_lattice_vectors("HCP", large_a, ratio),
        2 * get_lattice_vectors("HCP", small_a, ratio),
    )
    np.testing.assert_allclose(
        generate_hcp_prism_boundary(large_a, ratio)["vertices"],
        2 * generate_hcp_prism_boundary(small_a, ratio)["vertices"],
    )


@pytest.mark.parametrize("ratio", [1.4, 1.8])
def test_nonideal_hcp_prism_keeps_layers_and_unique_sites(ratio):
    a = 3.0
    c = get_lattice_vectors("HCP", a, ratio)[2, 2]
    sites = generate_display_sites("HCP", a, 1, ratio)
    assert len(sites) == 17
    positions = np.array([site["cartesian"] for site in sites])
    assert len(np.unique(np.round(positions, 12), axis=0)) == 17
    for layer, expected_height, expected_count in (
        ("A-bottom", 0.0, 7),
        ("B", c / 2, 3),
        ("A-top", c, 7),
    ):
        heights = [site["cartesian"][2] for site in sites if site["layer"] == layer]
        assert len(heights) == expected_count
        np.testing.assert_allclose(heights, expected_height)
    boundary = generate_hcp_prism_boundary(a, ratio)["vertices"]
    np.testing.assert_allclose(boundary[:6, 2], 0)
    np.testing.assert_allclose(boundary[6:, 2], c)


@pytest.mark.parametrize("size", [2, 3, 4])
def test_hcp_scientific_size_does_not_control_prism_display_size(size):
    assert len(generate_supercell("HCP", 3, size)) == 2 * size**3
    assert len(generate_display_sites("HCP", 3, size)) == 17


@pytest.mark.parametrize("ratio", [0, -1, math.nan, math.inf, "1.6", True])
def test_invalid_hcp_prism_ratio(ratio):
    with pytest.raises((TypeError, ValueError)):
        generate_display_sites("HCP", 3, 1, ratio)
    with pytest.raises((TypeError, ValueError)):
        generate_hcp_prism_boundary(3, ratio)

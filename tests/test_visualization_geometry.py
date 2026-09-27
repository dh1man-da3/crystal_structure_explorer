"""Mode geometry stays scientific in Python and is ready for JSON responses."""

import json
from collections import Counter
from itertools import product
from math import sqrt

import numpy as np
import pytest

from crystal_model import (
    IDEAL_HCP_C_OVER_A,
    fractional_to_cartesian,
    generate_display_sites,
    get_basis,
    get_lattice_vectors,
    nearest_neighbor_distance,
    touching_radius,
)
from visualization_geometry import build_visualization, generate_neighbour_network


@pytest.mark.parametrize("structure", ("SC", "BCC", "FCC", "HCP"))
@pytest.mark.parametrize("view", ("crystal", "unit", "coordination", "stacking"))
def test_every_view_is_plain_json(structure, view):
    data = build_visualization(structure, 3.0, view)
    assert data["mode"] == view
    json.dumps(data, allow_nan=False)


@pytest.mark.parametrize(
    "structure,site_count,effective,terms,planes",
    [
        ("SC", 8, 1, [("corner", 8, 1, 8)], 6),
        ("BCC", 9, 2, [("corner", 8, 1, 8), ("body_center", 1, 1, 1)], 6),
        ("FCC", 14, 4, [("corner", 8, 1, 8), ("face_center", 6, 1, 2)], 6),
        ("HCP", 17, 6, [("corner", 12, 1, 6),
                         ("basal_center", 2, 1, 2), ("interior", 3, 1, 1)], 8),
    ],
)
def test_unit_cell_count_accounting_radius_and_clipping(
    structure, site_count, effective, terms, planes
):
    a = 3.1
    result = build_visualization(structure, a, "unit")
    assert result["site_count"] == len(result["sites"]) == site_count
    assert len(result["clipping_planes"]) == planes
    assert result["physical_radius"] == pytest.approx(touching_radius(structure, a))
    accounting = result["accounting"]
    assert accounting["effective_atom_count"] == effective
    assert [(term["role"], term["count"], term["share_numerator"],
             term["share_denominator"]) for term in accounting["terms"]] == terms
    assert sum(count * numerator / denominator
               for _, count, numerator, denominator in terms) == effective
    assert Counter(site["role"] for site in result["sites"]) == {
        role: count for role, count, _, _ in terms
    }
    assert [site["id"] for site in result["sites"]] == list(range(site_count))

    # All cell-boundary vertices lie inside every Python-provided half-space.
    vertices = result["boundary"]["vertices"]
    assert len(vertices) == (12 if structure == "HCP" else 8)
    assert len(result["boundary"]["edges"]) == (18 if structure == "HCP" else 12)
    for plane in result["clipping_planes"]:
        normal = np.array(plane["normal"])
        assert np.linalg.norm(normal) == pytest.approx(1)
        signed = np.array(vertices) @ normal + plane["constant"]
        assert signed.min() >= -1e-10
        assert np.min(np.abs(signed)) < 1e-10


@pytest.mark.parametrize("structure,guide_count", (("SC", 0), ("BCC", 4),
                                                  ("FCC", 12), ("HCP", 0)))
def test_unit_contact_diagonals_are_for_only_one_cell(structure, guide_count):
    guides = build_visualization(structure, 3, "unit")["contact_diagonals"]
    assert guides["segment_count"] == len(guides["segments"]) == guide_count
    assert guides["supported"] is (structure in ("BCC", "FCC"))


@pytest.mark.parametrize("structure", ("SC", "BCC", "FCC", "HCP"))
def test_unit_site_coordinates_use_original_lattice_frame(structure):
    a = 4.3
    vectors = get_lattice_vectors(structure, a)
    for site in build_visualization(structure, a, "unit")["sites"]:
        np.testing.assert_allclose(
            site["cartesian"], fractional_to_cartesian(site["fractional"], vectors)
        )


@pytest.mark.parametrize(
    "structure,first,second",
    [
        ("SC", (0, 0, 0), (1, 0, 0)),
        ("BCC", (0, 0, 0), (0.5, 0.5, 0.5)),
        ("FCC", (0, 0, 0), (0.5, 0.5, 0)),
        ("HCP", (0, 0, 0), (2 / 3, 1 / 3, 0.5)),
    ],
)
def test_ideal_unit_cell_has_representative_tangent_spheres(structure, first, second):
    view = build_visualization(structure, 3.4, "unit")
    sites = view["sites"]
    first_site = next(site for site in sites
                      if np.allclose(site["fractional"], first))
    second_site = next(site for site in sites
                       if np.allclose(site["fractional"], second))
    distance = np.linalg.norm(np.array(first_site["cartesian"]) -
                              np.array(second_site["cartesian"]))
    assert distance == pytest.approx(2 * view["physical_radius"])


@pytest.mark.parametrize("ratio", (1.4, 1.8))
def test_nonideal_hcp_unit_radius_uses_actual_shortest_contact(ratio):
    a = 3.2
    view = build_visualization("HCP", a, "unit", ratio)
    assert view["site_count"] == 17
    assert len(view["clipping_planes"]) == 8
    assert view["physical_radius"] == pytest.approx(
        touching_radius("HCP", a, ratio))


@pytest.mark.parametrize("structure,neighbors", (("SC", 6), ("BCC", 8),
                                                  ("FCC", 12), ("HCP", 12)))
def test_coordination_shell_counts_and_distances(structure, neighbors):
    a = 3.2
    result = build_visualization(structure, a, "coordination")
    sites = result["sites"]
    assert len(sites) == result["site_count"] == neighbors + 1
    assert result["coordination_number"] == neighbors
    assert result["center_id"] == 0
    assert sites[0]["role"] == "central"
    assert all(site["role"] == "neighbor" for site in sites[1:])
    assert [site["id"] for site in sites] == list(range(neighbors + 1))
    assert len({tuple(site["fractional"]) for site in sites}) == neighbors + 1
    assert len(result["guide_segments"]) == neighbors
    vectors = get_lattice_vectors(structure, a)
    center = np.array(sites[0]["cartesian"])
    for site, guide in zip(sites[1:], result["guide_segments"]):
        np.testing.assert_allclose(
            site["cartesian"], fractional_to_cartesian(site["fractional"], vectors)
        )
        assert site["distance_from_center"] == pytest.approx(
            np.linalg.norm(np.array(site["cartesian"]) - center)
        )
        np.testing.assert_allclose(guide["start"], center)
        np.testing.assert_allclose(guide["end"], site["cartesian"])
    assert result["min_distance"] == pytest.approx(
        min(site["distance_from_center"] for site in sites[1:]))
    assert result["max_distance"] == pytest.approx(
        max(site["distance_from_center"] for site in sites[1:]))
    assert result["min_distance"] == pytest.approx(a if structure in ("SC", "HCP")
                                                  else sqrt(3) * a / 2 if structure == "BCC"
                                                  else a / sqrt(2))


@pytest.mark.parametrize("ratio", (1.4, 1.8))
def test_nonideal_hcp_keeps_standard_twelve_site_shell_with_actual_distances(ratio):
    a = 3.0
    result = build_visualization("HCP", a, "coordination", ratio)
    neighbors = result["sites"][1:]
    basal = [site for site in neighbors if site["fractional"][2] == 0]
    upper = [site for site in neighbors if site["fractional"][2] == 0.5]
    lower = [site for site in neighbors if site["fractional"][2] == -0.5]
    assert (len(basal), len(upper), len(lower)) == (6, 3, 3)
    assert all(site["distance_from_center"] == pytest.approx(a) for site in basal)
    assert all(site["distance_from_center"] == pytest.approx(upper[0]["distance_from_center"])
               for site in upper + lower)
    assert result["max_distance"] > result["min_distance"]


@pytest.mark.parametrize("structure,ratio", [
    ("SC", IDEAL_HCP_C_OVER_A),
    ("BCC", IDEAL_HCP_C_OVER_A),
    ("FCC", IDEAL_HCP_C_OVER_A),
    ("HCP", 1.2),
    ("HCP", IDEAL_HCP_C_OVER_A),
    ("HCP", 1.6235),
    ("HCP", 1.633),
    ("HCP", 2.0),
])
def test_coordination_polyhedron_is_closed_convex_and_outward(structure, ratio):
    view = build_visualization(structure, 3.0, "coordination", ratio)
    hull = view["polyhedron"]
    points = np.asarray([site["cartesian"] for site in view["sites"][1:]])
    faces = hull["faces"]
    edges = [tuple(edge) for edge in hull["edges"]]
    assert hull["supported"] is True
    assert hull["vertex_count"] == len(points) == view["coordination_number"]
    assert hull["face_count"] == len(faces) > 0
    assert hull["edge_count"] == len(edges) > 0
    assert len({tuple(point) for point in points}) == len(points)
    assert len({tuple(sorted(face)) for face in faces}) == len(faces)
    assert len(set(edges)) == len(edges)
    assert all(start < end for start, end in edges)
    assert len(points) - len(edges) + len(faces) == 2
    assert {vertex for face in faces for vertex in face} == set(range(len(points)))

    edge_occurrences = Counter()
    center = points.mean(axis=0)
    for face in faces:
        assert len(face) >= 3 and len(set(face)) == len(face)
        assert all(0 <= index < len(points) for index in face)
        face_points = points[face]
        normal = np.cross(face_points[1] - face_points[0],
                          face_points[2] - face_points[0])
        normal /= np.linalg.norm(normal)
        assert np.dot(normal, face_points.mean(axis=0) - center) > 0
        signed = (points - face_points[0]) @ normal
        assert np.max(signed) < 1e-8  # all vertices lie inside this face plane
        assert np.max(np.abs(signed[face])) < 1e-8  # face is planar
        for start, end in zip(face, face[1:] + face[:1]):
            edge_occurrences[tuple(sorted((start, end)))] += 1
    assert set(edges) == set(edge_occurrences)
    assert set(edge_occurrences.values()) == {2}


@pytest.mark.parametrize("structure,name,vertices,edges,faces,face_sizes", [
    ("SC", "Octahedron", 6, 12, 8, {3: 8}),
    ("BCC", "Cube", 8, 12, 6, {4: 6}),
    ("FCC", "Cuboctahedron", 12, 24, 14, {3: 8, 4: 6}),
    ("HCP", "Anticuboctahedron", 12, 24, 14, {3: 8, 4: 6}),
])
def test_ideal_coordination_polyhedron_topology(
    structure, name, vertices, edges, faces, face_sizes
):
    hull = build_visualization(structure, 3, "coordination")["polyhedron"]
    assert (hull["name"], hull["vertex_count"], hull["edge_count"],
            hull["face_count"]) == (name, vertices, edges, faces)
    assert Counter(map(len, hull["faces"])) == face_sizes


@pytest.mark.parametrize("ratio", (1.2, 1.6235, 2.0))
def test_nonideal_hcp_polyhedron_name_and_distance_groups(ratio):
    view = build_visualization("HCP", 3, "coordination", ratio)
    assert view["polyhedron"]["name"] == "Distorted HCP 12-neighbour polyhedron"
    assert sorted(group["count"] for group in view["distance_groups"]) == [6, 6]
    assert all(np.isfinite(group["distance"]) for group in view["distance_groups"])


@pytest.mark.parametrize("structure,cn", (("SC", 6), ("BCC", 8),
                                          ("FCC", 12), ("HCP", 12)))
def test_coordination_distance_groups_and_connections(structure, cn):
    view = build_visualization(structure, 4.1, "coordination")
    assert len(view["guide_segments"]) == cn
    assert sum(group["count"] for group in view["distance_groups"]) == cn
    assert len(view["distance_groups"]) == 1
    assert view["distance_groups"][0]["count"] == cn
    center = tuple(view["sites"][0]["cartesian"])
    assert all(tuple(segment["start"]) == center for segment in view["guide_segments"])
    assert {tuple(segment["end"]) for segment in view["guide_segments"]} == {
        tuple(site["cartesian"]) for site in view["sites"][1:]
    }


@pytest.mark.parametrize("structure,size,ratio,interior_degree", [
    ("SC", 3, IDEAL_HCP_C_OVER_A, 6),
    ("BCC", 3, IDEAL_HCP_C_OVER_A, 8),
    ("FCC", 3, IDEAL_HCP_C_OVER_A, 12),
    ("HCP", 4, IDEAL_HCP_C_OVER_A, 12),
    ("HCP", 4, 1.6235, 12),  # Mg-like non-ideal c/a
    ("HCP", 4, 1.2, 12),
    ("HCP", 4, 2.0, 12),
])
def test_crystal_network_has_unique_real_display_endpoints_and_interior_shell(
    structure, size, ratio, interior_degree
):
    a = 3.1
    sites = generate_display_sites(structure, a, size, ratio,
                                   display_size=size if structure == "HCP" else 1)
    network = generate_neighbour_network(structure, a, sites, ratio)
    assert network["supported"] is True
    assert network["segment_count"] == len(network["segments"]) > 0
    assert network == generate_neighbour_network(structure, a, sites, ratio)
    by_id = {site["index"]: site for site in sites}
    assert len(by_id) == len(sites)
    edges = set()
    degrees = Counter()
    for segment in network["segments"]:
        start_id, end_id = segment["start_site_id"], segment["end_site_id"]
        assert start_id in by_id and end_id in by_id and start_id < end_id
        assert (start_id, end_id) not in edges
        edges.add((start_id, end_id))
        degrees.update((start_id, end_id))
        np.testing.assert_allclose(segment["start"], by_id[start_id]["cartesian"])
        np.testing.assert_allclose(segment["end"], by_id[end_id]["cartesian"])
        assert np.all(np.isfinite(segment["start"]))
        assert np.all(np.isfinite(segment["end"]))
        assert np.isfinite(segment["distance"]) and segment["distance"] > 0
        assert segment["distance"] == pytest.approx(np.linalg.norm(
            np.asarray(segment["end"]) - segment["start"]))
        if structure != "HCP":
            assert segment["distance"] == pytest.approx(
                nearest_neighbor_distance(structure, a), rel=1e-9)
        elif ratio == IDEAL_HCP_C_OVER_A:
            assert segment["distance"] == pytest.approx(a, rel=1e-9)
    assert max(degrees.values()) == interior_degree
    if structure == "HCP":
        # The one-prism-high cluster can contain a complete shell around a
        # middle B site; basal-boundary A sites naturally have fewer links.
        assert any(site["role"] == "interior" and degrees[site["index"]] == 12
                   for site in sites)
        if ratio != IDEAL_HCP_C_OVER_A:
            assert any(segment["distance"] < a - 1e-6 or
                       segment["distance"] > a + 1e-6
                       for segment in network["segments"])
            assert any(segment["distance"] == pytest.approx(a)
                       for segment in network["segments"])


@pytest.mark.parametrize("structure,expected", [
    ("SC", 12), ("BCC", 8), ("FCC", 36),
])
def test_one_cubic_display_cell_has_expected_network_edge_count(structure, expected):
    sites = generate_display_sites(structure, 3.0, 1)
    network = generate_neighbour_network(structure, 3.0, sites)
    assert network["segment_count"] == expected


def test_fcc_and_hcp_twelve_neighbour_layer_registries_differ():
    """HCP upper/lower triangles align; FCC (111) triangles are staggered."""
    def triangle_projections(structure, axis):
        points = np.asarray([site["cartesian"] for site in
                             build_visualization(structure, 3, "coordination")["sites"][1:]])
        heights = points @ axis
        lower = points[np.isclose(heights, heights.min())]
        upper = points[np.isclose(heights, heights.max())]
        assert len(lower) == len(upper) == 3
        return lower - np.outer(lower @ axis, axis), upper - np.outer(upper @ axis, axis)

    hcp_bottom, hcp_top = triangle_projections("HCP", np.array([0., 0., 1.]))
    fcc_bottom, fcc_top = triangle_projections("FCC", np.ones(3) / sqrt(3))
    assert all(any(np.allclose(lower, upper) for upper in hcp_top)
               for lower in hcp_bottom)
    assert all(not any(np.allclose(lower, upper) for upper in fcc_top)
               for lower in fcc_bottom)


@pytest.mark.parametrize(
    "structure,layer_count,labels,sequence,direction,spacing",
    [
        ("SC", 25, ("A", "A", "A"), "AAA…", "[001]", 3.0),
        ("BCC", 25, ("A", "B", "A"), "ABAB…", "[001]", 1.5),
        ("FCC", 19, ("A", "B", "C"), "ABCABC…", "[111]", sqrt(3)),
        ("HCP", 19, ("A", "B", "A"), "ABAB…", "[0001]",
         3 * IDEAL_HCP_C_OVER_A / 2),
    ],
)
def test_stacking_layer_counts_sequence_spacing_and_coordinates(
    structure, layer_count, labels, sequence, direction, spacing
):
    a = 3.0
    result = build_visualization(structure, a, "stacking")
    sites = result["sites"]
    axis = np.array(result["axis"])
    assert np.linalg.norm(axis) == pytest.approx(1)
    assert result["natural_spacing"] == pytest.approx(spacing)
    assert result["sequence"] == sequence
    assert result["direction"] == direction
    assert [item["label"] for item in result["layers"]] == list(labels)
    assert result["site_count"] == len(sites) == 3 * layer_count
    assert Counter(site["layer_index"] for site in sites) == {0: layer_count,
                                                              1: layer_count,
                                                              2: layer_count}
    vectors = get_lattice_vectors(structure, a)
    for site in sites:
        assert site["role"] == "layer_site"
        assert site["layer_label"] == labels[site["layer_index"]]
        assert np.dot(site["cartesian"], axis) == pytest.approx(
            site["layer_index"] * spacing)
        np.testing.assert_allclose(
            site["cartesian"], fractional_to_cartesian(site["fractional"], vectors)
        )
    assert len({tuple(site["fractional"]) for site in sites}) == len(sites)


@pytest.mark.parametrize("structure", ("SC", "BCC", "FCC"))
def test_cubic_stacking_sites_are_real_cubic_lattice_positions(structure):
    basis = get_basis(structure)
    for site in build_visualization(structure, 3, "stacking")["sites"]:
        reduced = np.mod(site["fractional"], 1)
        assert any(np.allclose(reduced, basis_position) for basis_position in basis)


def test_fcc_stacking_has_true_triangular_planes_and_distinct_abc_registries():
    a = 3.0
    result = build_visualization("FCC", a, "stacking")
    layers = [[site for site in result["sites"] if site["layer_index"] == index]
              for index in range(3)]
    axis = np.array(result["axis"])
    centers = [next(site for site in layer
                    if tuple(site["fractional"]) in ((0., 0., 0.),
                                                      (0.5, 0.5, 0.),
                                                      (1., 0.5, 0.5)))
               for layer in layers]
    for layer, center in zip(layers, centers):
        distances = [np.linalg.norm(np.array(site["cartesian"]) - center["cartesian"])
                     for site in layer if site is not center]
        assert sum(np.isclose(distances, a / sqrt(2))) == 6
    lateral = [np.array(site["cartesian"]) -
               np.dot(site["cartesian"], axis) * axis for site in centers]
    assert not np.allclose(lateral[0], lateral[1])
    assert not np.allclose(lateral[1], lateral[2])
    assert not np.allclose(lateral[0], lateral[2])
    # A fourth FCC (111) layer at a1+a2+a3 has the original A registry.
    fourth = sum(get_lattice_vectors("FCC", a))
    np.testing.assert_allclose(fourth - np.dot(fourth, axis) * axis, lateral[0])


def test_fcc_stacking_basis_vectors_are_true_sixty_degree_neighbours():
    a = 3.2
    vectors = get_lattice_vectors("FCC", a)
    axis = np.array(build_visualization("FCC", a, "stacking")["axis"])
    first = (vectors[0] - vectors[1]) / 2
    second = (vectors[0] - vectors[2]) / 2
    assert np.dot(first, axis) == pytest.approx(0)
    assert np.dot(second, axis) == pytest.approx(0)
    assert np.linalg.norm(first) == pytest.approx(a / sqrt(2))
    assert np.linalg.norm(second) == pytest.approx(a / sqrt(2))
    assert np.dot(first, second) / (np.linalg.norm(first) *
                                     np.linalg.norm(second)) == pytest.approx(0.5)


def test_bcc_middle_layer_is_half_shifted_and_outer_layers_align():
    view = build_visualization("BCC", 3, "stacking")
    centers = [next(site for site in view["sites"]
                    if site["layer_index"] == layer and
                    np.allclose(site["fractional"], fractional))
               for layer, fractional in enumerate(((0, 0, 0),
                                                     (0.5, 0.5, 0.5),
                                                     (0, 0, 1)))]
    np.testing.assert_allclose(
        np.array(centers[1]["cartesian"]) -
        view["natural_spacing"] * np.array(view["axis"]),
        (get_lattice_vectors("BCC", 3)[0] + get_lattice_vectors("BCC", 3)[1]) / 2,
    )
    np.testing.assert_allclose(
        np.array(centers[2]["cartesian"]) - 2 * view["natural_spacing"] *
        np.array(view["axis"]),
        centers[0]["cartesian"],
    )


@pytest.mark.parametrize("ratio", (1.4, IDEAL_HCP_C_OVER_A, 1.8))
def test_hcp_stacking_tracks_actual_basis_and_nonideal_c(ratio):
    a = 3.2
    result = build_visualization("HCP", a, "stacking", ratio)
    centers = [next(site for site in result["sites"]
                    if site["layer_index"] == index and
                    np.allclose(site["fractional"], fractional))
               for index, fractional in enumerate(((0, 0, 0),
                                                     get_basis("HCP")[1],
                                                     (0, 0, 1)))]
    assert centers[1]["layer_label"] == "B"
    assert result["natural_spacing"] == pytest.approx(a * ratio / 2)
    assert result["axis"] == pytest.approx([0, 0, 1])


@pytest.mark.parametrize("view", ("bad", "", "density"))
def test_unsupported_view_is_rejected(view):
    with pytest.raises(ValueError, match="view must"):
        build_visualization("SC", 3, view)

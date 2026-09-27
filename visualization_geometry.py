"""Python-generated geometry for the Explorer's four educational views.

All coordinates in this module use the scientific lattice frame. Lattice
vectors are rows and ``cartesian = fractional @ lattice_vectors``. The browser
may centre or separate layers for presentation, but must not change these
reported crystallographic coordinates.
"""

from itertools import combinations, product

import numpy as np

from crystal_model import (
    IDEAL_HCP_C_OVER_A,
    coordination_number,
    display_cell_atom_count,
    fractional_to_cartesian,
    generate_display_guides,
    generate_display_sites,
    generate_hcp_prism_boundary,
    get_basis,
    get_lattice_vectors,
    nearest_neighbor_distance,
    touching_radius,
)


_ACCOUNTING = {
    "SC": (("corner", 8, 1, 8),),
    "BCC": (("corner", 8, 1, 8), ("body_center", 1, 1, 1)),
    "FCC": (("corner", 8, 1, 8), ("face_center", 6, 1, 2)),
    "HCP": (
        ("corner", 12, 1, 6),
        ("basal_center", 2, 1, 2),
        ("interior", 3, 1, 1),
    ),
}


def _site(index, fractional, vectors, role, **metadata):
    """Make one JSON-native site without rounding its scientific coordinates."""
    position = np.asarray(fractional, dtype=float)
    result = {
        "id": index,
        "fractional": position.tolist(),
        "cartesian": fractional_to_cartesian(position, vectors).tolist(),
        "role": role,
    }
    result.update(metadata)
    return result


def _cubic_boundary(vectors):
    """The twelve edges of one cubic conventional cell."""
    corners = list(product((0.0, 1.0), repeat=3))
    index = {corner: number for number, corner in enumerate(corners)}
    edges = []
    for corner in corners:
        for axis in range(3):
            if corner[axis] == 0:
                far = list(corner)
                far[axis] = 1.0
                edges.append([index[corner], index[tuple(far)]])
    return {
        "vertices": fractional_to_cartesian(corners, vectors).tolist(),
        "edges": edges,
    }


def _cubic_clipping_planes(vectors):
    """Six inward planes for 0 <= fractional coordinate <= 1.

    A plane is the half-space ``normal · r + constant >= 0``. The columns
    of the inverse lattice matrix are the gradients of fractional u, v, w.
    """
    inverse = np.linalg.inv(vectors)
    planes = []
    for axis in range(3):
        gradient = inverse[:, axis]
        length = float(np.linalg.norm(gradient))
        inward = gradient / length
        planes.append({"normal": inward.tolist(), "constant": 0.0})
        planes.append({"normal": (-inward).tolist(), "constant": 1 / length})
    return planes


def _hcp_clipping_planes(sites, vectors):
    """Six regular-hexagon sides plus bottom and top basal planes.

    The corner sites themselves define each side, so these planes stay
    consistent with the established educational-prism display geometry.
    """
    bottom = np.array(next(site["cartesian"] for site in sites
                           if site["role"] == "basal_center"
                           and site["layer"] == "A-bottom"))
    top = np.array(next(site["cartesian"] for site in sites
                        if site["role"] == "basal_center"
                        and site["layer"] == "A-top"))
    corners = [np.array(site["cartesian"]) for site in sites
               if site["role"] == "corner" and site["layer"] == "A-bottom"]
    corners.sort(key=lambda point: np.arctan2(point[1] - bottom[1],
                                              point[0] - bottom[0]))
    planes = []
    for start, end in zip(corners, corners[1:] + corners[:1]):
        edge = end - start
        normal = np.array((-edge[1], edge[0], 0.0))
        normal /= np.linalg.norm(normal)
        if np.dot(normal, bottom - start) < 0:
            normal = -normal
        planes.append({"normal": normal.tolist(),
                       "constant": -float(np.dot(normal, start))})
    vertical = vectors[2] / np.linalg.norm(vectors[2])
    planes.extend((
        {"normal": vertical.tolist(), "constant": -float(np.dot(vertical, bottom))},
        {"normal": (-vertical).tolist(), "constant": float(np.dot(vertical, top))},
    ))
    return planes


def _unit_view(name, a, ratio, vectors):
    display_sites = generate_display_sites(name, a, 1, ratio, display_size=1)
    sites = [_site(site["index"], site["fractional"], vectors,
                   site["role"], **({"layer": site["layer"]}
                                    if "layer" in site else {}))
             for site in display_sites]
    if name == "HCP":
        prism = generate_hcp_prism_boundary(a, ratio, display_size=1)
        boundary = {
            "vertices": np.asarray(prism["vertices"]).tolist(),
            "edges": np.asarray(prism["edges"], dtype=int).tolist(),
        }
        planes = _hcp_clipping_planes(sites, vectors)
    else:
        boundary = _cubic_boundary(vectors)
        planes = _cubic_clipping_planes(vectors)
    terms = [
        {
            "role": role,
            "count": count,
            "share_numerator": numerator,
            "share_denominator": denominator,
        }
        for role, count, numerator, denominator in _ACCOUNTING[name]
    ]
    contact = generate_display_guides(name, a, 1, ratio,
                                      display_size=1)["contact_diagonals"]
    contact = {
        **contact,
        "segments": [
            {"start": np.asarray(segment["start"]).tolist(),
             "end": np.asarray(segment["end"]).tolist()}
            for segment in contact["segments"]
        ],
    }
    return {
        "mode": "unit",
        "sites": sites,
        "site_count": len(sites),
        "boundary": boundary,
        "clipping_planes": planes,
        "physical_radius": float(touching_radius(name, a, ratio)),
        "contact_diagonals": contact,
        "accounting": {
            "terms": terms,
            "effective_atom_count": display_cell_atom_count(name),
        },
    }


def _candidate_lattice_sites(name, vectors):
    """Positions near the central basis atom, including neighbouring cells."""
    basis = get_basis(name)
    candidates = []
    for translation in product(range(-2, 3), repeat=3):
        for basis_index, basis_position in enumerate(basis):
            if translation == (0, 0, 0) and basis_index == 0:
                continue
            fractional = np.array(translation, dtype=float) + basis_position
            cartesian = fractional_to_cartesian(fractional, vectors)
            candidates.append((fractional, float(np.linalg.norm(cartesian)), basis_index))
    return candidates


def _coordination_polyhedron(neighbours, name, c_over_a):
    """Convex hull of the small (6–12 point) coordination shell.

    Faces and edges refer to zero-based positions in ``neighbours``; the
    central atom is deliberately not a vertex. Coordinates are normalized
    before plane tests, making the tolerance independent of lattice scale.
    Coplanar triangles are merged into one polygonal face.
    """
    points = np.asarray([site["cartesian"] for site in neighbours], dtype=float)
    center = points.mean(axis=0)
    scale = float(np.max(np.linalg.norm(points - center, axis=1)))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("coordination shell cannot form a polyhedron")
    points = (points - center) / scale
    tolerance = 1e-9
    face_sets = set()
    faces = []

    # Each hull plane contains at least one non-collinear triple. Testing all
    # triples is clear and inexpensive for the project's small neighbour shells.
    for i, j, k in combinations(range(len(points)), 3):
        normal = np.cross(points[j] - points[i], points[k] - points[i])
        normal_length = float(np.linalg.norm(normal))
        if normal_length <= tolerance:
            continue
        normal /= normal_length
        signed = (points - points[i]) @ normal
        if signed.min() < -tolerance and signed.max() > tolerance:
            continue
        vertex_indices = tuple(index for index, distance in enumerate(signed)
                               if abs(distance) <= tolerance)
        if vertex_indices in face_sets:
            continue
        face_sets.add(vertex_indices)

        face_center = points[list(vertex_indices)].mean(axis=0)
        if np.dot(normal, face_center) < 0:
            normal = -normal  # outward from the shell's interior
        first_axis = points[vertex_indices[0]] - face_center
        first_axis /= np.linalg.norm(first_axis)
        second_axis = np.cross(normal, first_axis)
        ordered = sorted(vertex_indices,
                         key=lambda index: (float(np.arctan2(
                             np.dot(points[index] - face_center, second_axis),
                             np.dot(points[index] - face_center, first_axis))), index))
        start = ordered.index(min(ordered))
        faces.append(ordered[start:] + ordered[:start])

    faces.sort(key=lambda face: tuple(sorted(face)))
    edges = sorted({(min(start, end), max(start, end))
                    for face in faces
                    for start, end in zip(face, face[1:] + face[:1])})
    names = {"SC": "Octahedron", "BCC": "Cube", "FCC": "Cuboctahedron"}
    if name == "HCP":
        ideal = abs(c_over_a - IDEAL_HCP_C_OVER_A) <= 1e-4
        shape_name = ("Anticuboctahedron" if ideal
                      else "Distorted HCP 12-neighbour polyhedron")
    else:
        shape_name = names[name]
    return {
        "supported": True,
        "name": shape_name,
        "vertex_count": len(points),
        "edge_count": len(edges),
        "face_count": len(faces),
        "faces": faces,
        "edges": [list(edge) for edge in edges],
    }


def _distance_groups(neighbours, a):
    """Group numerically equal shell distances, retaining actual geometry."""
    distances = sorted(site["distance_from_center"] for site in neighbours)
    tolerance = 1e-9 * a
    groups = []
    for distance in distances:
        if groups and abs(distance - groups[-1]["distance"]) <= tolerance:
            count = groups[-1]["count"] + 1
            groups[-1] = {"distance": (groups[-1]["distance"] * (count - 1)
                                       + distance) / count, "count": count}
        else:
            groups.append({"distance": distance, "count": 1})
    return groups


def _coordination_neighbours(name, a, vectors):
    """Return the standard first shell around the basis atom at the origin.

    HCP deliberately retains its six basal and six adjacent-layer neighbours
    when a non-ideal c/a splits their distances. Crystal-mode network lines
    reuse these same relative positions, rather than redefining the shell.
    """
    candidates = _candidate_lattice_sites(name, vectors)
    expected = coordination_number(name)
    if name == "HCP":
        # For non-ideal c/a the standard twelve geometric neighbours do not
        # generally lie at one distance. Keep six in-plane A sites and three
        # B sites on each adjacent layer; report their actual distances.
        # Round only for deterministic tie ordering, never for coordinates or
        # reported distances. Equal-distance sites then use lattice indices.
        key = lambda item: (round(item[1] / a, 10), tuple(item[0]))
        in_plane = sorted((item for item in candidates
                           if item[2] == 0 and abs(item[0][2]) < 1e-12),
                          key=key)[:6]
        above = sorted((item for item in candidates
                        if item[2] == 1 and abs(item[0][2] - 0.5) < 1e-12),
                       key=key)[:3]
        below = sorted((item for item in candidates
                        if item[2] == 1 and abs(item[0][2] + 0.5) < 1e-12),
                       key=key)[:3]
        neighbours = in_plane + above + below
    else:
        nearest = nearest_neighbor_distance(name, a)
        tolerance = max(1e-10 * nearest, 1e-12)
        neighbours = [item for item in candidates
                      if abs(item[1] - nearest) <= tolerance]
    if len(neighbours) != expected:
        raise ValueError("could not construct the expected coordination shell")
    return neighbours


def _coordination_view(name, a, ratio, vectors):
    """One central atom and its standard shell, not a finite conventional cell."""
    neighbours = _coordination_neighbours(name, a, vectors)
    expected = coordination_number(name)

    sites = [_site(0, (0, 0, 0), vectors, "central", distance_from_center=0.0)]
    for fractional, distance, _ in neighbours:
        sites.append(_site(len(sites), fractional, vectors, "neighbor",
                           distance_from_center=distance))
    origin = sites[0]["cartesian"]
    segments = [{"start": origin, "end": site["cartesian"]}
                for site in sites[1:]]
    distances = [site["distance_from_center"] for site in sites[1:]]
    polyhedron = _coordination_polyhedron(sites[1:], name, ratio)
    return {
        "mode": "coordination",
        "sites": sites,
        "site_count": len(sites),
        "center_id": 0,
        "coordination_number": expected,
        "guide_segments": segments,
        "min_distance": min(distances),
        "max_distance": max(distances),
        "distance_groups": _distance_groups(sites[1:], a),
        "polyhedron": polyhedron,
    }


def _sixth_lattice_key(fractional):
    """Exact integer key for this project's HCP display coefficients.

    HCP prism sites and primitive-basis shell offsets are multiples of 1/6
    in the established lattice-vector convention. Comparing these integer
    keys avoids raw floating-point equality when identifying neighbours.
    """
    return tuple(int(round(6 * value)) for value in fractional)


def generate_neighbour_network(structure, a, display_sites,
                               c_over_a=IDEAL_HCP_C_OVER_A):
    """Connect first-shell pairs among the finite Crystal display sites.

    This is visualization-only geometry: the edges do not imply chemical
    bonds and do not change the periodic scientific supercell. Cubic pairs
    use their actual nearest-neighbour distance. HCP uses the standard 12-site
    shell's fractional offsets, preserving both distance groups for non-ideal
    c/a. Each undirected edge appears once in stable display-site ID order.
    """
    vectors = get_lattice_vectors(structure, a, c_over_a)
    name = structure.strip().upper()
    if name == "HCP":
        shell = _coordination_neighbours(name, a, vectors)
        basal_offsets = {_sixth_lattice_key(fractional)
                         for fractional, _, basis_index in shell
                         if basis_index == 0}
        cross_offsets = {_sixth_lattice_key(fractional)
                         for fractional, _, basis_index in shell
                         if basis_index == 1}
        site_keys = [_sixth_lattice_key(site["fractional"])
                     for site in display_sites]
        is_b_site = [site["role"] == "interior" for site in display_sites]
    else:
        nearest = nearest_neighbor_distance(name, a)
        tolerance = 1e-9 * nearest

    segments = []
    for first_index, first in enumerate(display_sites):
        first_point = np.asarray(first["cartesian"], dtype=float)
        for second_index in range(first_index + 1, len(display_sites)):
            second = display_sites[second_index]
            second_point = np.asarray(second["cartesian"], dtype=float)
            distance = float(np.linalg.norm(second_point - first_point))
            if name == "HCP":
                first_key, second_key = site_keys[first_index], site_keys[second_index]
                if is_b_site[first_index] == is_b_site[second_index]:
                    offset = tuple(second_key[axis] - first_key[axis]
                                   for axis in range(3))
                    connected = offset in basal_offsets
                else:
                    a_key, b_key = ((second_key, first_key)
                                    if is_b_site[first_index]
                                    else (first_key, second_key))
                    offset = tuple(b_key[axis] - a_key[axis]
                                   for axis in range(3))
                    connected = offset in cross_offsets
            else:
                connected = abs(distance - nearest) <= tolerance
            if connected:
                segments.append({
                    "start_site_id": int(first["index"]),
                    "end_site_id": int(second["index"]),
                    "start": first_point.tolist(),
                    "end": second_point.tolist(),
                    "distance": distance,
                })
    return {"supported": True, "segment_count": len(segments),
            "segments": segments}


def _hex_patch_indices(radius=2):
    """Nineteen axial-index positions in a radius-two triangular patch."""
    return [(i, j) for i, j in product(range(-radius, radius + 1), repeat=2)
            if max(abs(i), abs(j), abs(i + j)) <= radius]


def _stacking_view(name, a, ratio, vectors):
    """Three actual crystallographic layers with natural, un-exploded positions."""
    zero = np.zeros(3)
    if name == "SC":
        centers = (zero, np.array((0., 0., 1.)), np.array((0., 0., 2.)))
        labels, sequence, direction = ("A", "A", "A"), "AAA…", "[001]"
        in_plane = (np.array((1., 0., 0.)), np.array((0., 1., 0.)))
        indices = list(product(range(-2, 3), repeat=2))
        normal = vectors[2]
    elif name == "BCC":
        centers = (zero, np.array((0.5, 0.5, 0.5)), np.array((0., 0., 1.)))
        labels, sequence, direction = ("A", "B", "A"), "ABAB…", "[001]"
        in_plane = (np.array((1., 0., 0.)), np.array((0., 1., 0.)))
        indices = list(product(range(-2, 3), repeat=2))
        normal = vectors[2]
    elif name == "FCC":
        # Each centre is an actual FCC site in consecutive occupied (111)
        # planes. The fourth layer centre (1,1,1) restores A registry.
        centers = (zero, np.array((0.5, 0.5, 0.)), np.array((1., 0.5, 0.5)))
        labels, sequence, direction = ("A", "B", "C"), "ABCABC…", "[111]"
        in_plane = (np.array((0.5, -0.5, 0.)),
                    np.array((0.5, 0., -0.5)))
        indices = _hex_patch_indices()
        normal = vectors.sum(axis=0)
    else:
        centers = (zero, get_basis("HCP")[1], np.array((0., 0., 1.)))
        labels, sequence, direction = ("A", "B", "A"), "ABAB…", "[0001]"
        in_plane = (np.array((1., 0., 0.)), np.array((1., 1., 0.)))
        indices = _hex_patch_indices()
        normal = vectors[2]

    axis = normal / np.linalg.norm(normal)
    heights = [float(np.dot(fractional_to_cartesian(center, vectors), axis))
               for center in centers]
    spacing = heights[1] - heights[0]
    if spacing <= 0 or not np.isclose(heights[2] - heights[1], spacing):
        raise ValueError("stacking layers are not equally spaced")
    sites = []
    for layer_index, (center, label) in enumerate(zip(centers, labels)):
        for i, j in indices:
            fractional = center + i * in_plane[0] + j * in_plane[1]
            sites.append(_site(len(sites), fractional, vectors, "layer_site",
                               layer_index=layer_index, layer_label=label))
    return {
        "mode": "stacking",
        "sites": sites,
        "site_count": len(sites),
        "layers": [{"index": index, "label": label}
                   for index, label in enumerate(labels)],
        "axis": axis.tolist(),
        "natural_spacing": float(spacing),
        "direction": direction,
        "sequence": sequence,
        "physical_radius": float(touching_radius(name, a, ratio)),
    }


def build_visualization(structure, a, view="crystal",
                        c_over_a=IDEAL_HCP_C_OVER_A):
    """Return JSON-native geometry for one educational visualization mode.

    Crystal mode continues using the existing ``display`` response. This
    function only marks that mode; the three additional modes supply their
    own site geometry and metadata. Scientific properties are unchanged.
    """
    vectors = get_lattice_vectors(structure, a, c_over_a)
    name = structure.strip().upper()
    if not isinstance(view, str):
        raise TypeError("view must be a string")
    mode = view.strip().lower()
    if mode == "crystal":
        return {"mode": "crystal"}
    if mode == "unit":
        return _unit_view(name, a, c_over_a, vectors)
    if mode == "coordination":
        return _coordination_view(name, a, c_over_a, vectors)
    if mode == "stacking":
        return _stacking_view(name, a, c_over_a, vectors)
    raise ValueError("view must be crystal, unit, coordination, or stacking")

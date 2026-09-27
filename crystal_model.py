"""Geometry of the four crystal structures used by this project.

Lattice vectors are the *rows* of a 3 x 3 array. A fractional row vector
``(u, v, w)`` becomes a Cartesian row vector by ``fractional @ vectors``.
All lengths use the same unit as ``a`` (for example, ångströms).

The HCP vectors enclose a two-atom primitive hexagonal cell. The familiar
six-atom hexagonal prism contains three such cells, so HCP supercells use a
two-atom basis. The educational prism display includes shared boundary sites;
those visible copies do not add unique scientific positions.
"""

from itertools import product
from numbers import Integral, Real

import numpy as np


_CUBIC_BASES = {
    "SC": ((0, 0, 0),),
    "BCC": ((0, 0, 0), (0.5, 0.5, 0.5)),
    "FCC": (
        (0, 0, 0),
        (0, 0.5, 0.5),
        (0.5, 0, 0.5),
        (0.5, 0.5, 0),
    ),
}

# Full visible sites of one conventional cubic cell, in half-lattice units.
# The shared faces, edges, and corners are deduplicated after tiling cells.
_CUBIC_CORNERS = tuple(product((0, 2), repeat=3))
_CUBIC_DISPLAY_SITES = {
    "SC": _CUBIC_CORNERS,
    "BCC": (*_CUBIC_CORNERS, (1, 1, 1)),
    "FCC": (
        *_CUBIC_CORNERS,
        (1, 1, 0), (1, 1, 2),
        (1, 0, 1), (1, 2, 1),
        (0, 1, 1), (2, 1, 1),
    ),
}

_COORDINATION_NUMBERS = {"SC": 6, "BCC": 8, "FCC": 12, "HCP": 12}
IDEAL_HCP_C_OVER_A = float(np.sqrt(8 / 3))
AVOGADRO_CONSTANT = 6.02214076e23  # mol^-1, exact SI definition


def _structure_name(structure):
    if not isinstance(structure, str):
        raise TypeError("structure must be a string")
    name = structure.strip().upper()
    if name not in _COORDINATION_NUMBERS:
        raise ValueError("structure must be SC, BCC, FCC, or HCP")
    return name


def _positive_finite(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return float(value)


def _supercell_size(size):
    if isinstance(size, (bool, np.bool_)) or not isinstance(size, Integral):
        raise TypeError("size must be an integer from 1 to 4")
    if not 1 <= size <= 4:
        raise ValueError("size must be an integer from 1 to 4")
    return int(size)


def get_lattice_vectors(structure, a, c_over_a=IDEAL_HCP_C_OVER_A):
    """Return lattice vectors as rows; HCP uses a 120-degree primitive cell."""
    name = _structure_name(structure)
    a = _positive_finite(a, "a")
    if name == "HCP":
        ratio = _positive_finite(c_over_a, "c_over_a")
        vectors = np.array(
            [[a, 0, 0], [-a / 2, np.sqrt(3) * a / 2, 0], [0, 0, a * ratio]],
            dtype=float,
        )
        if not np.all(np.isfinite(vectors)):
            raise ValueError("a * c_over_a must be finite")
        return vectors
    return np.eye(3) * a


def get_basis(structure):
    """Return fractional basis coordinates; HCP's primitive basis has 2 atoms."""
    name = _structure_name(structure)
    if name == "HCP":
        return np.array(((0, 0, 0), (2 / 3, 1 / 3, 0.5)), dtype=float)
    return np.array(_CUBIC_BASES[name], dtype=float)


def fractional_to_cartesian(fractional, lattice_vectors):
    """Convert a length-3 vector or N x 3 array using ``fractional @ vectors``."""
    coordinates = np.asarray(fractional, dtype=float)
    vectors = np.asarray(lattice_vectors, dtype=float)
    if coordinates.ndim not in (1, 2) or coordinates.shape[-1] != 3:
        raise ValueError("fractional must have shape (3,) or (N, 3)")
    if vectors.shape != (3, 3) or not np.all(np.isfinite(vectors)):
        raise ValueError("lattice_vectors must be a finite 3 x 3 array")
    if not np.all(np.isfinite(coordinates)):
        raise ValueError("fractional coordinates must be finite")
    return coordinates @ vectors


def cell_volume(lattice_vectors):
    """Return the positive parallelepiped volume from the determinant."""
    vectors = np.asarray(lattice_vectors, dtype=float)
    if vectors.shape != (3, 3) or not np.all(np.isfinite(vectors)):
        raise ValueError("lattice_vectors must be a finite 3 x 3 array")
    volume = abs(float(np.linalg.det(vectors)))
    if volume <= 0 or not np.isfinite(volume):
        raise ValueError("lattice vectors must enclose a finite positive volume")
    return volume


def basis_atom_count(structure):
    """Return atoms in the computational basis used by ``generate_supercell``."""
    return len(get_basis(structure))


def display_cell_atom_count(structure):
    """Return the textbook cell count shown in the educational property panel.

    The HCP hexagonal prism has 12 corners shared six ways (2 atoms),
    2 basal-face atoms shared two ways (1), and 3 interior atoms: 6 total.
    This is distinct from the two-atom primitive translational basis.
    """
    name = _structure_name(structure)
    return 6 if name == "HCP" else basis_atom_count(name)


def display_cell_volume(structure, a, c_over_a=IDEAL_HCP_C_OVER_A):
    """Return the visible conventional-cell volume in ångström cubed.

    The HCP educational hexagonal prism contains three computational
    primitive cells. Cubic structures display their computational cells.
    """
    name = _structure_name(structure)
    primitive_or_conventional = cell_volume(get_lattice_vectors(name, a, c_over_a))
    return 3 * primitive_or_conventional if name == "HCP" else primitive_or_conventional


def theoretical_density(structure, a, atomic_mass_g_mol,
                        c_over_a=IDEAL_HCP_C_OVER_A):
    """Return monatomic theoretical density in g/cm³.

    Atom count and volume both refer to the computational cell. In HCP that
    is the two-atom primitive cell, not the six-atom display prism.
    """
    name = _structure_name(structure)
    mass = _positive_finite(atomic_mass_g_mol, "atomic_mass_g_mol")
    volume_angstrom3 = cell_volume(get_lattice_vectors(name, a, c_over_a))
    # 1 Å³ = 10^-24 cm³. Keep this factor in the numerator to avoid
    # premature underflow for very small but still valid cell volumes.
    density = (basis_atom_count(name) * mass / AVOGADRO_CONSTANT) * 1e24 / volume_angstrom3
    if not np.isfinite(density) or density <= 0:
        raise ValueError("theoretical density must be finite and greater than zero")
    return float(density)


def coordination_number(structure):
    """Return standard coordination; HCP's value assumes the ideal c/a ratio."""
    return _COORDINATION_NUMBERS[_structure_name(structure)]


def generate_supercell(structure, a, size, c_over_a=IDEAL_HCP_C_OVER_A):
    """Generate unique basis positions in an N x N x N cell array.

    The HCP array consists of primitive cells, so it contains ``2 * N**3``
    atoms, not ``6 * N**3`` atoms from the larger hexagonal prism.
    """
    name = _structure_name(structure)
    size = _supercell_size(size)
    vectors = get_lattice_vectors(name, a, c_over_a)
    basis = get_basis(name)
    atoms = []
    for cell in product(range(size), repeat=3):
        for basis_index, position in enumerate(basis):
            fractional = position + cell
            atoms.append(
                {
                    "index": len(atoms),
                    "basis_index": basis_index,
                    "cell": cell,
                    "fractional": fractional,
                    "cartesian": fractional_to_cartesian(fractional, vectors),
                }
            )
    return atoms


def generate_display_sites(structure, a, size, c_over_a=IDEAL_HCP_C_OVER_A,
                           display_size=1):
    """Return finite display sites, distinct from periodic scientific atoms.

    Unlike ``generate_supercell``, this visualization-only set includes the
    shared boundary sites. It is not an effective atom count. For HCP,
    ``size`` still describes the independent primitive scientific supercell;
    ``display_size`` gives an N x N, one-prism-high basal display cluster.

    Cubic fractional positions use the scientific lattice vectors and may
    range from 0 through ``size`` on each axis. Half-integer coordinates are
    stored as integer keys until after deduplication. HCP prism positions
    are also expressed in the primitive lattice coordinates, so some basal
    fractional components are negative around the centered hexagon.
    """
    name = _structure_name(structure)
    size = _supercell_size(size)
    if name == "HCP":
        display_size = _hcp_display_size(display_size)
        vectors = get_lattice_vectors(name, a, c_over_a)
        return _generate_hcp_cluster_display_sites(vectors, display_size)
    vectors = get_lattice_vectors(name, a)

    seen = set()
    sites = []
    for cell in product(range(size), repeat=3):
        for local_site in _CUBIC_DISPLAY_SITES[name]:
            key = tuple(2 * cell[axis] + local_site[axis] for axis in range(3))
            if key in seen:
                continue
            seen.add(key)
            fractional = np.array(key, dtype=float) / 2
            sites.append(
                {
                    "index": len(sites),
                    "fractional": fractional,
                    "cartesian": fractional_to_cartesian(fractional, vectors),
                    "role": (
                        "corner" if local_site in _CUBIC_CORNERS else
                        "body_center" if name == "BCC" else "face_center"
                    ),
                }
            )
    return sites


def _display_segment(start, end, vectors):
    """Convert two lattice-vector coefficient triples into one display line."""
    return {
        "start": fractional_to_cartesian(start, vectors),
        "end": fractional_to_cartesian(end, vectors),
    }


def _generate_cubic_cell_grid(vectors, size):
    """Each unique one-cell edge of an N x N x N conventional cubic block.

    For each lattice direction there are N edges at each of (N+1)^2
    transverse grid positions: 3 N (N+1)^2 segments altogether.
    """
    segments = []
    for axis in range(3):
        ranges = [range(size + 1) for _ in range(3)]
        ranges[axis] = range(size)
        for position in product(*ranges):
            start = np.array(position, dtype=float)
            end = start.copy()
            end[axis] += 1
            segments.append(_display_segment(start, end, vectors))
    return segments


def _generate_cubic_contact_diagonals(structure, vectors, size):
    """BCC body or FCC unique-face diagonals for geometric contact guides.

    These thin construction lines are not chemical bonds. Each full diagonal
    crosses a body- or face-centred *display site* at its midpoint.
    """
    segments = []
    if structure == "BCC":
        local_diagonals = (
            ((0, 0, 0), (1, 1, 1)),
            ((1, 0, 0), (0, 1, 1)),
            ((0, 1, 0), (1, 0, 1)),
            ((0, 0, 1), (1, 1, 0)),
        )
        for cell in product(range(size), repeat=3):
            translation = np.array(cell, dtype=float)
            for first, second in local_diagonals:
                segments.append(_display_segment(
                    translation + first, translation + second, vectors
                ))
    elif structure == "FCC":
        # Enumerate each square face once: two in-plane cell indices and one
        # fixed plane index. This avoids duplicate guides on shared faces.
        for first_axis, second_axis, fixed_axis in ((0, 1, 2), (0, 2, 1), (1, 2, 0)):
            first_step = np.eye(3)[first_axis]
            second_step = np.eye(3)[second_axis]
            for plane in range(size + 1):
                for first, second in product(range(size), repeat=2):
                    corner = np.zeros(3)
                    corner[first_axis] = first
                    corner[second_axis] = second
                    corner[fixed_axis] = plane
                    segments.append(_display_segment(
                        corner, corner + first_step + second_step, vectors
                    ))
                    segments.append(_display_segment(
                        corner + first_step, corner + second_step, vectors
                    ))
    return segments


def generate_display_guides(structure, a, size, c_over_a=IDEAL_HCP_C_OVER_A,
                            display_size=1):
    """Return visualization-only cell edges and cubic contact diagonals.

    Segment endpoints use the original crystallographic Cartesian frame, not
    a viewer-centred frame. HCP's grid contains every educational prism edge;
    its contact diagonals remain unsupported because they are not analogous
    to the cubic body/face diagonals. SC has a grid but no contact diagonals.
    """
    name = _structure_name(structure)
    size = _supercell_size(size)
    vectors = get_lattice_vectors(name, a, c_over_a)

    def unavailable():
        return {"supported": False, "segment_count": 0, "segments": []}

    if name == "HCP":
        display_size = _hcp_display_size(display_size)
        grid = [
            _display_segment(np.array(first) / 6, np.array(second) / 6, vectors)
            for first, second in _hcp_cluster_grid_keys(display_size)
        ]
        return {
            "cell_grid": {"supported": True, "segment_count": len(grid), "segments": grid},
            "contact_diagonals": unavailable(),
        }

    grid = _generate_cubic_cell_grid(vectors, size)
    cell_grid = {"supported": True, "segment_count": len(grid), "segments": grid}
    if name == "SC":
        contact = unavailable()
    else:
        diagonals = _generate_cubic_contact_diagonals(name, vectors, size)
        contact = {
            "supported": True,
            "kind": "body" if name == "BCC" else "face",
            "segment_count": len(diagonals),
            "segments": diagonals,
        }
    return {"cell_grid": cell_grid, "contact_diagonals": contact}


def _hcp_prism_corner_fractional():
    """Six cyclic basal vertices for the 120-degree primitive HCP vectors.

    The coordinates are ±a1, ±a2, and ±(a1+a2). Their Cartesian positions
    form a regular hexagon of circumradius and edge length ``a``.
    """
    return np.array(
        ((1, 0, 0), (1, 1, 0), (0, 1, 0),
         (-1, 0, 0), (-1, -1, 0), (0, -1, 0)),
        dtype=float,
    )


def _hcp_display_size(display_size):
    """Validate the separate one-prism-high HCP display-cluster size."""
    if isinstance(display_size, (bool, np.bool_)) or not isinstance(display_size, Integral):
        raise TypeError("display_size must be an integer from 1 to 4")
    if not 1 <= display_size <= 4:
        raise ValueError("display_size must be an integer from 1 to 4")
    return int(display_size)


def _hcp_prism_centers_sixths(display_size):
    """Prism centres in sixths of (a1, a2, a3).

    Centre translations are T1 = 2a1+a2 and T2 = a1+2a2, not a1/a2.
    Their integer basal determinant is 3, so one prism spans three primitive
    basal cells. Iteration order also gives reproducible display IDs.
    """
    for p, q in product(range(display_size), repeat=2):
        yield (6 * (2 * p + q), 6 * (p + 2 * q), 0)


def _hcp_local_site_keys_sixths():
    """One prism's exact role-tagged positions in sixth-lattice units."""
    ring = [tuple(int(value) for value in 6 * position)
            for position in _hcp_prism_corner_fractional()]
    primitive_b = get_basis("HCP")[1]
    # Translations of the actual primitive B atom give the three sites
    # inside this centered hexagonal prism. No new HCP basis is invented.
    middle = (primitive_b, primitive_b - (1, 0, 0), primitive_b - (1, 1, 0))
    middle_keys = [tuple(int(round(6 * component)) for component in position)
                   for position in middle]
    return (
        [(key, "corner", "A-bottom") for key in ring]
        + [((0, 0, 0), "basal_center", "A-bottom")]
        + [(key, "interior", "B") for key in middle_keys]
        + [(tuple((key[0], key[1], 6)), "corner", "A-top") for key in ring]
        + [((0, 0, 6), "basal_center", "A-top")]
    )


def _generate_hcp_cluster_display_sites(vectors, display_size):
    """Tile complete prisms, deduplicating shared sites before conversion."""
    # A dict retains first-seen order. Unlike a set iteration, site IDs are
    # stable, including for the original one-prism API response.
    unique = {}
    for center in _hcp_prism_centers_sixths(display_size):
        for local, role, layer in _hcp_local_site_keys_sixths():
            key = tuple(center[axis] + local[axis] for axis in range(3))
            if key in unique and unique[key] != (role, layer):
                raise ValueError("shared HCP display sites have inconsistent roles")
            unique.setdefault(key, (role, layer))
    sites = []
    for key, (role, layer) in unique.items():
        fractional = np.array(key, dtype=float) / 6
        sites.append(
            {
                "index": len(sites),
                "fractional": fractional,
                "cartesian": fractional_to_cartesian(fractional, vectors),
                "role": role,
                "layer": layer,
            }
        )
    return sites


def _canonical_segment(first, second):
    """Undirected edge key in exact sixth-lattice coordinates."""
    return tuple(sorted((first, second)))


def _hcp_prism_ring_sixths():
    return [tuple(int(value) for value in 6 * position)
            for position in _hcp_prism_corner_fractional()]


def _hcp_cluster_grid_keys(display_size):
    """Each unique bottom, top, or vertical edge of all tiled prisms."""
    ring = _hcp_prism_ring_sixths()
    unique = {}
    for center in _hcp_prism_centers_sixths(display_size):
        bottom = [tuple(center[axis] + corner[axis] for axis in range(3))
                  for corner in ring]
        top = [(point[0], point[1], 6) for point in bottom]
        for index in range(6):
            next_index = (index + 1) % 6
            for first, second in (
                (bottom[index], bottom[next_index]),
                (top[index], top[next_index]),
                (bottom[index], top[index]),
            ):
                unique.setdefault(_canonical_segment(first, second), (first, second))
    return list(unique.values())


def _hcp_cluster_perimeter_keys(display_size):
    """Basal edges shared once form the exterior of the tiled prism union."""
    ring = _hcp_prism_ring_sixths()
    counts = {}
    for center in _hcp_prism_centers_sixths(display_size):
        bottom = [tuple(center[axis] + corner[axis] for axis in range(3))
                  for corner in ring]
        for index in range(6):
            edge = _canonical_segment(bottom[index], bottom[(index + 1) % 6])
            counts[edge] = counts.get(edge, 0) + 1
    return [edge for edge, count in counts.items() if count == 1]


def generate_hcp_prism_boundary(a, c_over_a=IDEAL_HCP_C_OVER_A,
                                display_size=1):
    """Return the outer wireframe of an N x N educational HCP prism cluster.

    The first half of vertices are bottom perimeter corners; the second half
    are their top copies. Edges are zero-based vertex-index pairs. Internal
    shared basal edges are omitted, unlike the complete ``cell_grid``.
    """
    display_size = _hcp_display_size(display_size)
    vectors = get_lattice_vectors("HCP", a, c_over_a)
    perimeter = _hcp_cluster_perimeter_keys(display_size)
    bottom_keys = dict.fromkeys(point for edge in perimeter for point in edge)
    bottom = list(bottom_keys)
    bottom_index = {point: index for index, point in enumerate(bottom)}
    top = [(point[0], point[1], 6) for point in bottom]
    vertices = fractional_to_cartesian(
        np.array(bottom + top, dtype=float) / 6, vectors
    )
    half = len(bottom)
    edges = []
    for first, second in perimeter:
        first_index, second_index = bottom_index[first], bottom_index[second]
        edges.extend(((first_index, second_index),
                      (first_index + half, second_index + half)))
    edges.extend((index, index + half) for index in range(half))
    return {"vertices": vertices, "edges": edges}


def nearest_neighbor_distance(structure, a, c_over_a=IDEAL_HCP_C_OVER_A):
    """Return the shortest atom separation in the infinite periodic crystal."""
    name = _structure_name(structure)
    vectors = get_lattice_vectors(name, a, c_over_a)
    if name == "SC":
        return float(a)
    if name == "BCC":
        return float(np.sqrt(3) * a / 2)
    if name == "FCC":
        return float(a / np.sqrt(2))

    # HCP's closest atom may lie in a neighbouring cell, above or below.
    basis = get_basis(name)
    distances = []
    for translation in product((-1, 0, 1), repeat=3):
        for basis_index, atom in enumerate(basis):
            if basis_index == 0 and translation == (0, 0, 0):
                continue
            offset = atom + translation - basis[0]
            distance = np.linalg.norm(fractional_to_cartesian(offset, vectors))
            distances.append(distance)
    return float(min(distances))


def touching_radius(structure, a, c_over_a=IDEAL_HCP_C_OVER_A):
    """Hard-sphere radius when nearest neighbouring atoms just touch."""
    return nearest_neighbor_distance(structure, a, c_over_a) / 2


def packing_factor(structure, a, c_over_a=IDEAL_HCP_C_OVER_A):
    """Sphere volume divided by cell volume, using current touching radius.

    For non-ideal HCP this is the density of equal spheres just touching at
    the shortest separation; coordination is not necessarily 12 then.
    """
    name = _structure_name(structure)
    vectors = get_lattice_vectors(name, a, c_over_a)
    count = basis_atom_count(name)
    radius = touching_radius(name, a, c_over_a)
    return float(count * (4 / 3) * np.pi * radius**3 / cell_volume(vectors))

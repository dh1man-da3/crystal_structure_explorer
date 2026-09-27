"""Presentation data for comparing the four supported structures.

Numerical properties come from :mod:`crystal_model`. The descriptive text and
symbolic relations below are presentation metadata, not a second calculator.
Generic HCP properties describe the ideal c/a ratio. The separate real-material
example uses the magnesium preset's measured, slightly non-ideal parameters.
"""

import crystal_model as crystal


_DESCRIPTIONS = {
    "SC": {
        "full_name": "Simple Cubic",
        "crystal_system": "Cubic",
        "cell_description": "Conventional cube",
        "stacking": "AAA… along [001]",
        "packing_character": "Open cubic packing",
        "contact_direction": "Cube edge",
        "site_roles": "Corner",
        "repetition": "N × N × N conventional cells",
        "scientific_volume_tex": r"a^3",
        "scientific_volume_fallback": "a³",
        "educational_volume_tex": r"a^3",
        "educational_volume_fallback": "a³",
        "coordination_polyhedron": "Octahedron",
        "nearest_tex": r"d_{\mathrm{nn}}=a",
        "nearest_fallback": "dₙₙ = a",
        "radius_tex": r"r=\frac{a}{2}",
        "radius_fallback": "r = a/2",
        "geometry_tex": r"a=b=c,\quad \alpha=\beta=\gamma=90^\circ",
        "geometry_fallback": "a = b = c; all angles 90°",
        "summary": "Only the cube corners are lattice sites. It is a particularly clear starting point for understanding shared corners.",
        "feature": "Corner-only cubic lattice",
    },
    "BCC": {
        "full_name": "Body-Centred Cubic",
        "crystal_system": "Cubic",
        "cell_description": "Conventional cube",
        "stacking": "ABAB… along [001] (not close-packed)",
        "packing_character": "Non-close-packed",
        "contact_direction": "Body diagonal",
        "site_roles": "Corner + body centre",
        "repetition": "N × N × N conventional cells",
        "scientific_volume_tex": r"a^3",
        "scientific_volume_fallback": "a³",
        "educational_volume_tex": r"a^3",
        "educational_volume_fallback": "a³",
        "coordination_polyhedron": "Cube",
        "nearest_tex": r"d_{\mathrm{nn}}=\frac{\sqrt{3}}{2}a",
        "nearest_fallback": "dₙₙ = √3 a/2",
        "radius_tex": r"r=\frac{\sqrt{3}}{4}a",
        "radius_fallback": "r = √3 a/4",
        "geometry_tex": r"a=b=c,\quad \alpha=\beta=\gamma=90^\circ",
        "geometry_fallback": "a = b = c; all angles 90°",
        "summary": "Each conventional cube has a lattice site at its body center as well as shared corner sites.",
        "feature": "Corner and body-center sites",
    },
    "FCC": {
        "full_name": "Face-Centred Cubic",
        "crystal_system": "Cubic",
        "cell_description": "Conventional cube",
        "stacking": "ABCABC… along [111]",
        "packing_character": "Close-packed",
        "contact_direction": "Face diagonal",
        "site_roles": "Corner + face centre",
        "repetition": "N × N × N conventional cells",
        "scientific_volume_tex": r"a^3",
        "scientific_volume_fallback": "a³",
        "educational_volume_tex": r"a^3",
        "educational_volume_fallback": "a³",
        "coordination_polyhedron": "Cuboctahedron",
        "nearest_tex": r"d_{\mathrm{nn}}=\frac{a}{\sqrt{2}}",
        "nearest_fallback": "dₙₙ = a/√2",
        "radius_tex": r"r=\frac{a}{2\sqrt{2}}",
        "radius_fallback": "r = a/(2√2)",
        "geometry_tex": r"a=b=c,\quad \alpha=\beta=\gamma=90^\circ",
        "geometry_fallback": "a = b = c; all angles 90°",
        "summary": "Each conventional cube has sites at its corners and face centers. Close-packed planes follow an ABC sequence.",
        "feature": "Corner and face-center sites",
    },
    "HCP": {
        "full_name": "Hexagonal Close-Packed",
        "crystal_system": "Hexagonal",
        "cell_description": "Educational hexagonal prism",
        "stacking": "ABAB… along [0001]",
        "packing_character": "Close-packed (ideal)",
        "contact_direction": "Close-packed neighbour directions",
        "site_roles": "Corner + basal centre + interior",
        "repetition": "N × N educational prisms in the basal plane, one prism high",
        "scientific_volume_tex": r"\frac{\sqrt{3}}{2}a^2c",
        "scientific_volume_fallback": "(√3/2)a²c (primitive)",
        "educational_volume_tex": r"\frac{3\sqrt{3}}{2}a^2c",
        "educational_volume_fallback": "(3√3/2)a²c (prism)",
        "coordination_polyhedron": "Anticuboctahedron (ideal)",
        "nearest_tex": r"d_{\mathrm{nn}}=a\quad\text{(ideal)}",
        "nearest_fallback": "dₙₙ = a (ideal)",
        "radius_tex": r"r=\frac{a}{2}\quad\text{(ideal)}",
        "radius_fallback": "r = a/2 (ideal)",
        "geometry_tex": r"\gamma=120^\circ,\quad (c/a)_{\rm ideal}=\sqrt{8/3}",
        "geometry_fallback": "γ = 120°; ideal c/a = √(8/3)",
        "summary": "Hexagonal basal layers alternate in an ABAB sequence. The familiar prism is a larger educational display than the two-atom primitive cell.",
        "feature": "Alternating close-packed layers",
    },
}


def build_comparison(materials):
    """Return template-ready structure summaries from model and local presets.

    The model's computational basis uses cubic conventional cells but HCP's
    primitive cell. The separate display-cell count uses the textbook HCP
    hexagonal prism, which has six effective atoms.
    """
    preset_by_structure = {}
    for material in materials:
        code = material["structure"].upper()
        if code in preset_by_structure:
            raise ValueError(f"Multiple representative presets for {code}")
        preset_by_structure[code] = material

    structures = []
    for code, description in _DESCRIPTIONS.items():
        if code not in preset_by_structure:
            raise ValueError(f"Missing representative material for {code}")
        material = preset_by_structure[code]
        lattice = material["lattice"]
        material_a = lattice["a_angstrom"]
        material_ratio = None
        material_c = None
        if code == "HCP":
            # Match the catalog's measured c where supplied, rather than
            # replacing it with ideal HCP geometry in the material example.
            material_ratio = (
                lattice["c_angstrom"] / material_a
                if "c_angstrom" in lattice else lattice["c_over_a"]
            )
            material_c = lattice.get("c_angstrom", material_a * material_ratio)
        # a=1 Å gives dimensionless coefficients for the relations in the
        # table; APF itself is independent of this scale. HCP uses ideal c/a.
        reference_a = 1.0
        reference_vectors = crystal.get_lattice_vectors(code, reference_a)
        structures.append(
            {
                "code": code,
                **description,
                "basis_atom_count": crystal.basis_atom_count(code),
                "display_cell_atom_count": crystal.display_cell_atom_count(code),
                "coordination_number": crystal.coordination_number(code),
                "packing_factor": crystal.packing_factor(code, reference_a),
                "nearest_neighbor_per_a": crystal.nearest_neighbor_distance(
                    code, reference_a
                ),
                "touching_radius_per_a": crystal.touching_radius(code, reference_a),
                "single_cell_visible_site_count": len(
                    crystal.generate_display_sites(code, reference_a, 1)
                ),
                "scientific_cell_volume_per_a3": crystal.cell_volume(reference_vectors),
                "educational_cell_volume_per_a3": crystal.display_cell_volume(
                    code, reference_a
                ),
                "material_name": material["name"],
                "material_symbol": material["symbol"],
                "material_lattice_a": material_a,
                "material_lattice_c": material_c,
                "material_lattice_c_over_a": material_ratio,
                "material_density_g_cm3": crystal.theoretical_density(
                    code, material_a, material["atomic_mass_g_mol"],
                    material_ratio if code == "HCP" else crystal.IDEAL_HCP_C_OVER_A,
                ),
                "material_atomic_mass_note": material.get("atomic_mass_note"),
                "material_conditions": material["conditions"],
                "space_group_symbol": material["space_group"]["symbol"],
                "space_group_number": material["space_group"]["number"],
            }
        )
    return {
        "structures": structures,
        "ideal_hcp_c_over_a": crystal.IDEAL_HCP_C_OVER_A,
    }

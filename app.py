"""Flask pages, curated elemental materials, and the crystal-model API."""

import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

import crystal_model as crystal
import visualization_geometry as visualization
from comparison_data import build_comparison

app = Flask(__name__)
# Gunicorn imports this module; only the explicit local launch below may opt in.
app.debug = False
MATERIALS_PATH = Path(__file__).resolve().parent / "data" / "materials.json"
PROJECT_PATH = Path(__file__).resolve().parent / "data" / "project.json"
_MATERIAL_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class MaterialCatalogError(RuntimeError):
    """The local curated data is missing or malformed (a developer error)."""


def _material_text(value, location):
    if not isinstance(value, str) or not value.strip():
        raise MaterialCatalogError(f"{location} must be a nonempty string")
    return value


def _material_positive_number(value, location):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MaterialCatalogError(f"{location} must be a positive finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise MaterialCatalogError(f"{location} must be a positive finite number")


def validate_materials(document):
    """Validate local provenance and parameters; return canonical catalog rows.

    This intentionally rejects a bad curated entry rather than dropping it.
    The returned structures use lowercase names for selector/API consistency.
    """
    if not isinstance(document, dict) or not isinstance(document.get("materials"), list):
        raise MaterialCatalogError("materials catalog must contain a 'materials' list")
    if not document["materials"]:
        raise MaterialCatalogError("materials catalog must contain at least one material")

    materials = []
    ids = set()
    for index, entry in enumerate(document["materials"]):
        location = f"materials[{index}]"
        if not isinstance(entry, dict):
            raise MaterialCatalogError(f"{location} must be an object")
        material_id = _material_text(entry.get("id"), f"{location}.id")
        if not _MATERIAL_ID.fullmatch(material_id):
            raise MaterialCatalogError(f"{location}.id must be a lowercase slug")
        if material_id in ids:
            raise MaterialCatalogError(f"duplicate material id '{material_id}'")
        ids.add(material_id)
        _material_text(entry.get("name"), f"{location}.name")
        _material_text(entry.get("symbol"), f"{location}.symbol")
        raw_structure = _material_text(entry.get("structure"), f"{location}.structure")
        structure = raw_structure.upper()
        if structure not in ("SC", "BCC", "FCC", "HCP"):
            raise MaterialCatalogError(f"{location}.structure must be SC, BCC, FCC, or HCP")
        atomic_number = entry.get("atomic_number")
        if type(atomic_number) is not int or atomic_number < 1:
            raise MaterialCatalogError(f"{location}.atomic_number must be a positive integer")
        _material_positive_number(entry.get("atomic_mass_g_mol"),
                                  f"{location}.atomic_mass_g_mol")
        if "atomic_mass_note" in entry:
            _material_text(entry["atomic_mass_note"], f"{location}.atomic_mass_note")

        lattice = entry.get("lattice")
        if not isinstance(lattice, dict):
            raise MaterialCatalogError(f"{location}.lattice must be an object")
        _material_positive_number(lattice.get("a_angstrom"),
                                  f"{location}.lattice.a_angstrom")
        if "c_angstrom" in lattice:
            _material_positive_number(lattice["c_angstrom"],
                                      f"{location}.lattice.c_angstrom")
        if "c_over_a" in lattice:
            _material_positive_number(lattice["c_over_a"],
                                      f"{location}.lattice.c_over_a")
        if structure == "HCP":
            if "c_angstrom" not in lattice and "c_over_a" not in lattice:
                raise MaterialCatalogError(
                    f"{location}.lattice requires c_angstrom or c_over_a for HCP"
                )
            if "c_angstrom" in lattice and "c_over_a" in lattice and not math.isclose(
                lattice["c_angstrom"] / lattice["a_angstrom"],
                lattice["c_over_a"], rel_tol=1e-3
            ):
                raise MaterialCatalogError(f"{location}.lattice c/a values disagree")

        group = entry.get("space_group")
        if not isinstance(group, dict):
            raise MaterialCatalogError(f"{location}.space_group must be an object")
        _material_text(group.get("symbol"), f"{location}.space_group.symbol")
        number = group.get("number")
        if type(number) is not int or not 1 <= number <= 230:
            raise MaterialCatalogError(f"{location}.space_group.number must be 1–230")
        _material_text(entry.get("phase_note"), f"{location}.phase_note")
        _material_text(entry.get("conditions"), f"{location}.conditions")

        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            raise MaterialCatalogError(f"{location}.sources must be a nonempty list")
        for source_index, source in enumerate(sources):
            source_location = f"{location}.sources[{source_index}]"
            if not isinstance(source, dict):
                raise MaterialCatalogError(f"{source_location} must be an object")
            _material_text(source.get("property"), f"{source_location}.property")
            _material_text(source.get("name"), f"{source_location}.name")
            url = _material_text(source.get("url"), f"{source_location}.url")
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                raise MaterialCatalogError(f"{source_location}.url must be an HTTP(S) URL")
            if "reference" in source:
                _material_text(source["reference"], f"{source_location}.reference")

        materials.append({**entry, "structure": structure.lower()})
    return materials


def load_materials(path=None):
    """Read the offline catalog and fail explicitly if it is malformed."""
    path = MATERIALS_PATH if path is None else Path(path)

    def reject_non_json_constant(value):
        raise MaterialCatalogError(f"materials catalog contains non-JSON value {value}")

    try:
        with path.open(encoding="utf-8") as catalog_file:
            document = json.load(catalog_file, parse_constant=reject_non_json_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterialCatalogError(f"Cannot load materials catalog at {path}: {exc}") from exc
    return validate_materials(document)


@app.get("/")
def index():
    return render_template(
        "index.html", active_page="home", ideal_hcp_ratio=crystal.IDEAL_HCP_C_OVER_A
    )


@app.get("/health")
def health():
    """Report that Flask is responsive without loading data or calculating geometry."""
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def page_not_found(_error):
    return render_template("errors/404.html", active_page=None), 404


@app.errorhandler(500)
def server_error(_error):
    # Flask logs the underlying exception; do not expose it in the response.
    return render_template("errors/500.html", active_page=None), 500


@app.get("/compare")
def compare():
    """Compare the four structures using values from the scientific model."""
    return render_template(
        "compare.html", active_page="compare",
        comparison=build_comparison(load_materials()),
    )


@app.get("/docs")
def docs():
    return render_template("docs.html", active_page="docs")


def load_project_info(path=PROJECT_PATH):
    """Load the small editable project/team record used by the About page."""
    with Path(path).open(encoding="utf-8") as project_file:
        data = json.load(project_file)
    if not isinstance(data, dict) or not isinstance(data.get("project"), dict):
        raise ValueError("project.json needs a project object")
    for field in (
        "title", "academic_title", "institution", "programme", "semester",
        "subject", "course_code", "type", "submitted_to",
    ):
        value = data["project"].get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"project.json needs a nonempty project.{field}")
    if not isinstance(data.get("team"), list) or len(data["team"]) != 2:
        raise ValueError("project.json needs exactly two team members")
    for member in data["team"]:
        if not isinstance(member, dict) or any(
            not isinstance(member.get(field), str) or not member[field].strip()
            for field in ("name", "uid", "image")
        ):
            raise ValueError("project.json team entries need nonempty names, UIDs, and images")
    technologies = data.get("technologies")
    if not isinstance(technologies, list) or not technologies or any(
        not isinstance(value, str) or not value.strip() for value in technologies
    ):
        raise ValueError("project.json needs a nonempty technologies list of strings")
    return data


@app.get("/about")
def about():
    return render_template(
        "about.html", active_page="about", project_info=load_project_info()
    )


def _positive_float(raw, name):
    """Parse a required positive finite query value."""
    if raw is None or not raw.strip():
        raise ValueError(f"Missing required parameter '{name}'.")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"Parameter '{name}' must be a number.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Parameter '{name}' must be finite and greater than zero.")
    return value


def _size(raw, name="size"):
    """Parse a supported integer size (1 through 4)."""
    try:
        size = int(raw)
    except ValueError as exc:
        raise ValueError(f"Parameter '{name}' must be an integer from 1 to 4.") from exc
    if size not in (1, 2, 3, 4):
        raise ValueError(f"Parameter '{name}' must be an integer from 1 to 4.")
    return size


def _invalid_parameter(message):
    return jsonify({"error": {"code": "invalid_parameter", "message": message}}), 400


def _internal_error():
    return jsonify(
        {"error": {"code": "internal_error", "message": "Internal server error."}}
    ), 500


@app.get("/api/materials")
def api_materials():
    """Serve curated local elemental presets without external requests."""
    try:
        return jsonify({"materials": load_materials()})
    except Exception:
        app.logger.exception("Cannot serve local materials catalog")
        return _internal_error()


@app.get("/api/structure")
def api_structure():
    """Return calculated geometry for one structure; lengths are in ångströms."""
    try:
        return _structure_response()
    except Exception:
        app.logger.exception("Unexpected structure API error")
        return _internal_error()


def _structure_response():
    try:
        view = request.args.get("view", "crystal").strip().lower()
        if view not in ("crystal", "unit", "coordination", "stacking"):
            raise ValueError("Parameter 'view' must be crystal, unit, coordination, or stacking.")
        raw_structure = request.args.get("structure")
        if raw_structure is None or not raw_structure.strip():
            raise ValueError("Missing required parameter 'structure'.")
        structure = raw_structure.strip().upper()
        basis = crystal.get_basis(structure)  # Also validates the structure name.
        material_id = request.args.get("material")
        if material_id is not None:
            material_id = material_id.strip()
            if not material_id:
                raise ValueError("Parameter 'material' must be a material ID.")
        a = _positive_float(request.args.get("a"), "a")
        size = _size(request.args.get("size", "1"))
        # HCP display_size is independent of the primitive scientific size.
        # As with c_over_a, a supplied value is ignored for cubic structures.
        display_size = (
            _size(request.args.get("display_size", "1"), "display_size")
            if structure == "HCP" else None
        )
        ratio = (
            _positive_float(request.args.get("c_over_a"), "c_over_a")
            if structure == "HCP" and "c_over_a" in request.args
            else crystal.IDEAL_HCP_C_OVER_A
        )
        # A supplied c_over_a is intentionally ignored for cubic structures.
        vectors = crystal.get_lattice_vectors(structure, a, ratio)
        volume = crystal.cell_volume(vectors)
    except ValueError as exc:
        return _invalid_parameter(str(exc))

    material = None
    if material_id is not None:
        material = next((item for item in load_materials() if item["id"] == material_id), None)
        if material is None:
            return _invalid_parameter(f"Unknown material ID '{material_id}'.")
        if material["structure"].upper() != structure:
            return _invalid_parameter(
                f"Material '{material_id}' is incompatible with structure {structure}."
            )

    atoms = crystal.generate_supercell(structure, a, size, ratio)
    atom_data = [
        {
            "id": atom["index"],
            "fractional": atom["fractional"].tolist(),
            "cartesian": atom["cartesian"].tolist(),
            "cell": list(atom["cell"]),
            "basis_index": atom["basis_index"],
        }
        for atom in atoms
    ]
    response_data = {
        "structure": structure,
        "units": {"length": "angstrom", "volume": "angstrom^3"},
        "parameters": {
            "a": a,
            "c": float(vectors[2, 2]) if structure == "HCP" else None,
            "c_over_a": ratio if structure == "HCP" else None,
            "supercell_size": size,
            "view": view,
            **({"display_size": display_size} if structure == "HCP" else {}),
        },
        "cell": {
            "representation": "primitive" if structure == "HCP" else "conventional",
            "lattice_vectors": vectors.tolist(),
            "basis_fractional": basis.tolist(),
            "volume": volume,
            "display_cell_volume": crystal.display_cell_volume(structure, a, ratio),
            "basis_atom_count": crystal.basis_atom_count(structure),
            "display_cell_atom_count": crystal.display_cell_atom_count(structure),
            "coordination_number": crystal.coordination_number(structure),
            "nearest_neighbor_distance": crystal.nearest_neighbor_distance(
                structure, a, ratio
            ),
            "touching_radius": crystal.touching_radius(structure, a, ratio),
            "packing_factor": crystal.packing_factor(structure, a, ratio),
        },
        "supercell": {"atom_count": len(atoms), "atoms": atom_data},
    }

    if material is not None:
        response_data["material"] = {
            key: material[key]
            for key in (
                "id", "name", "symbol", "atomic_number", "atomic_mass_g_mol",
                "space_group", "phase_note", "conditions", "sources",
            )
        }
        if "atomic_mass_note" in material:
            response_data["material"]["atomic_mass_note"] = material["atomic_mass_note"]
        response_data["material"]["theoretical_density_g_cm3"] = (
            crystal.theoretical_density(structure, a, material["atomic_mass_g_mol"], ratio)
        )

    display_sites = crystal.generate_display_sites(
        structure, a, size, ratio,
        display_size=display_size if structure == "HCP" else 1,
    )
    site_data = []
    for site in display_sites:
        item = {
            "id": int(site["index"]),
            "fractional": site["fractional"].tolist(),
            "cartesian": site["cartesian"].tolist(),
            "role": site["role"],
        }
        if structure == "HCP":
            item["layer"] = site["layer"]
        site_data.append(item)

    display_data = {"site_count": len(site_data), "sites": site_data}
    if view == "crystal":
        # Finite first-shell guides refer to the visible display sites, not
        # to the half-open periodic atoms in the scientific supercell.
        display_data["neighbour_network"] = visualization.generate_neighbour_network(
            structure, a, display_sites, ratio
        )
    # Python supplies both scientific/display sites and every guide endpoint;
    # Three.js only decides which precomputed lines are visible.
    guides = crystal.generate_display_guides(
        structure, a, size, ratio,
        display_size=display_size if structure == "HCP" else 1,
    )
    for guide_name, guide in guides.items():
        display_data[guide_name] = {
            **{key: value for key, value in guide.items() if key != "segments"},
            "segments": [
                {"start": segment["start"].tolist(),
                 "end": segment["end"].tolist()}
                for segment in guide["segments"]
            ],
        }
    if structure == "HCP":
        boundary = crystal.generate_hcp_prism_boundary(a, ratio, display_size)
        display_data.update({
            "kind": "hcp_prism_cluster",
            "display_size": display_size,
            "prism_count": display_size**2,
            "effective_atom_count": 6 * display_size**2,
            "primitive_cell_count": 3 * display_size**2,
            "boundary": {
                "vertices": boundary["vertices"].tolist(),
                "edges": [list(edge) for edge in boundary["edges"]],
            },
            "stacking": {
                "sequence": "ABAB",
                "layers": [
                    {"label": "A", "height_fraction": 0.0},
                    {"label": "B", "height_fraction": 0.5},
                    {"label": "A", "height_fraction": 1.0},
                ],
            },
        })
    response_data["display"] = display_data
    response_data["visualization"] = visualization.build_visualization(
        structure, a, view, ratio
    )

    return jsonify(response_data)


if __name__ == "__main__":
    app.run(debug=os.environ.get("CRYSTAL_DEBUG") == "1")

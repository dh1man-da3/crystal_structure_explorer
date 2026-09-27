"""Regression checks for the small, offline elemental-material catalog."""

from copy import deepcopy

import pytest

from app import MaterialCatalogError, load_materials, validate_materials


def _valid_document():
    return {
        "materials": [{
            "id": "copper",
            "name": "Copper",
            "symbol": "Cu",
            "structure": "FCC",
            "atomic_number": 29,
            "atomic_mass_g_mol": 63.546,
            "lattice": {"a_angstrom": 3.6148},
            "space_group": {"symbol": "Fm-3m", "number": 225},
            "phase_note": "Ambient-pressure FCC phase",
            "conditions": "18 °C",
            "sources": [
                {"property": "lattice", "name": "AIST", "url": "https://example.org/lattice"},
                {"property": "atomic_mass", "name": "NIST", "url": "https://example.org/mass"},
            ],
        }]
    }


def test_curated_catalog_has_exact_initial_elemental_presets():
    materials = load_materials()
    by_id = {material["id"]: material for material in materials}
    assert len(materials) == len(by_id) == 4
    assert set(by_id) == {"alpha-polonium", "alpha-iron", "copper", "magnesium"}

    expected = {
        "alpha-polonium": ("sc", "Po", 84, 208.9824308, 3.359, 221),
        "alpha-iron": ("bcc", "Fe", 26, 55.845, 2.8665, 229),
        "copper": ("fcc", "Cu", 29, 63.546, 3.6148, 225),
        "magnesium": ("hcp", "Mg", 12, 24.305, 3.2094, 194),
    }
    for material_id, (structure, symbol, atomic_number, mass, a, group) in expected.items():
        material = by_id[material_id]
        assert material["structure"] == structure
        assert material["symbol"] == symbol
        assert material["atomic_number"] == atomic_number
        assert material["atomic_mass_g_mol"] == pytest.approx(mass)
        assert material["lattice"]["a_angstrom"] == pytest.approx(a)
        assert material["space_group"]["number"] == group
        assert material["phase_note"] and material["conditions"]
        assert len(material["sources"]) >= 2
        assert all(source["property"] and source["name"] and source["url"]
                   for source in material["sources"])

    magnesium = by_id["magnesium"]
    assert magnesium["lattice"]["c_angstrom"] == pytest.approx(5.2105)
    assert magnesium["lattice"]["c_over_a"] == pytest.approx(5.2105 / 3.2094)
    assert "atomic_mass_note" in by_id["alpha-polonium"]


@pytest.mark.parametrize(
    ("change", "expected_error"),
    [
        (lambda row: row.pop("atomic_mass_g_mol"), "atomic_mass_g_mol"),
        (lambda row: row.update(structure="diamond"), "structure"),
        (lambda row: row["lattice"].update(a_angstrom=float("nan")), "a_angstrom"),
        (lambda row: row.update(atomic_number=True), "atomic_number"),
        (lambda row: row.update(sources=[]), "sources"),
        (lambda row: row["sources"][0].update(url="javascript:alert(1)"), "url"),
        (lambda row: row["space_group"].update(number=999), "space_group.number"),
    ],
)
def test_catalog_rejects_malformed_entries(change, expected_error):
    document = deepcopy(_valid_document())
    change(document["materials"][0])
    with pytest.raises(MaterialCatalogError, match=expected_error):
        validate_materials(document)


def test_catalog_rejects_duplicate_ids():
    document = _valid_document()
    document["materials"].append(deepcopy(document["materials"][0]))
    with pytest.raises(MaterialCatalogError, match="duplicate material id"):
        validate_materials(document)


def test_hcp_catalog_accepts_c_derived_from_ratio_and_requires_one():
    document = _valid_document()
    row = document["materials"][0]
    row["structure"] = "HCP"
    row["lattice"] = {"a_angstrom": 3.2094, "c_over_a": 5.2105 / 3.2094}
    assert validate_materials(document)[0]["structure"] == "hcp"
    del row["lattice"]["c_over_a"]
    with pytest.raises(MaterialCatalogError, match="requires c_angstrom or c_over_a"):
        validate_materials(document)

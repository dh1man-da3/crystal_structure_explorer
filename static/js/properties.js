"use strict";

const STRUCTURE_NAMES = {
  SC: "Simple Cubic (SC)",
  BCC: "Body-Centered Cubic (BCC)",
  FCC: "Face-Centered Cubic (FCC)",
  HCP: "Hexagonal Close-Packed (HCP)",
};

const SITE_ROLES = {
  corner: "Corner",
  body_center: "Body center",
  face_center: "Face center",
  basal_center: "Basal center",
  interior: "Interior",
  central: "Central site",
  neighbor: "Coordination neighbour",
  layer_site: "Layer site",
};

// These relations are presentation only. Python calculates every numeric result.
const EQUATIONS = {
  SC: [
    String.raw`V=a^3`,
    String.raw`d_{\mathrm{nn}}=a`,
    String.raw`r=\frac{a}{2}`,
    String.raw`\mathrm{APF}=\frac{\pi}{6}`,
  ],
  BCC: [
    String.raw`V=a^3`,
    String.raw`d_{\mathrm{nn}}=\frac{\sqrt{3}\,a}{2}`,
    String.raw`r=\frac{\sqrt{3}\,a}{4}`,
    String.raw`\mathrm{APF}=\frac{\sqrt{3}\pi}{8}`,
  ],
  FCC: [
    String.raw`V=a^3`,
    String.raw`d_{\mathrm{nn}}=\frac{a}{\sqrt{2}}`,
    String.raw`r=\frac{a}{2\sqrt{2}}`,
    String.raw`\mathrm{APF}=\frac{\pi}{3\sqrt{2}}`,
  ],
  HCP: [
    String.raw`c=\left(\frac{c}{a}\right)a`,
    String.raw`V_{\mathrm{primitive}}=\frac{\sqrt{3}}{2}a^2c`,
    String.raw`V_{\mathrm{prism}}=\frac{3\sqrt{3}}{2}a^2c`,
    String.raw`r=\frac{d_{\mathrm{nn}}}{2}`,
    String.raw`\left(\frac{c}{a}\right)_{\mathrm{ideal}}=\sqrt{\frac{8}{3}}\approx1.633`,
  ],
};

function decimal(value, places, minimumPlaces = 0) {
  const fixed = Number(value).toFixed(places);
  if (minimumPlaces === places) return fixed;
  const [whole, fraction] = fixed.split(".");
  if (!fraction) return whole;
  let kept = fraction;
  while (kept.length > minimumPlaces && kept.endsWith("0")) kept = kept.slice(0, -1);
  return kept ? `${whole}.${kept}` : whole;
}

function renderMath(element, latex) {
  if (!window.katex?.render) throw new Error("The local KaTeX renderer is unavailable.");
  window.katex.render(latex, element, { throwOnError: false });
}

function section(title) {
  const element = document.createElement("section");
  element.className = "property-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  element.append(heading);
  return element;
}

function listIn(element) {
  const list = document.createElement("dl");
  list.className = "property-list";
  element.append(list);
  return list;
}

function row(list, label, value, isMath = false) {
  const item = document.createElement("div");
  item.className = "property-row";
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  if (isMath) renderMath(description, value);
  else description.textContent = value;
  item.append(term, description);
  list.append(item);
}

function note(element, text) {
  const paragraph = document.createElement("p");
  paragraph.className = "property-note";
  paragraph.textContent = text;
  element.append(paragraph);
}

function lengthMath(symbol, value, places = 4, minimumPlaces = 3) {
  return `${symbol}=${decimal(value, places, minimumPlaces)}\\,\\text{\\AA}`;
}

function volumeMath(symbol, value) {
  return `${symbol}=${decimal(value, 3, 3)}\\,\\text{\\AA}^{3}`;
}

function latticeNumber(value) {
  if (Math.abs(value) < 1e-8) return "0";
  const integer = Math.round(value);
  if (Math.abs(value - integer) < 1e-8) return String(integer);
  for (const denominator of [2, 3]) {
    const numerator = Math.round(value * denominator);
    if (Math.abs(value - numerator / denominator) < 1e-8) {
      const sign = numerator < 0 ? "-" : "";
      return `${sign}\\frac{${Math.abs(numerator)}}{${denominator}}`;
    }
  }
  return decimal(value, 4);
}

function cartesianNumber(value) {
  return (Math.abs(value) < 0.00005 ? 0 : value).toFixed(4);
}

function addSources(fragment, sources) {
  const group = section("Sources");
  const list = document.createElement("ul");
  list.className = "source-list";
  for (const source of sources) {
    const address = new URL(source.url);
    if (!["https:", "http:"].includes(address.protocol)) continue;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = address.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = source.name;
    item.append(link);
    list.append(item);
  }
  group.append(list);
  fragment.append(group);
}

export function renderProperties(container, data, selectedSitePanel) {
  const fragment = document.createDocumentFragment();
  const { structure, parameters, cell, material, visualization } = data;
  const hcp = structure === "HCP";

  const identity = section("Structure");
  const identityRows = listIn(identity);
  row(identityRows, "Crystal structure", STRUCTURE_NAMES[structure]);
  row(identityRows, "Lattice system", hcp ? "Hexagonal" : "Cubic");
  row(identityRows, "Material", material ? `${material.name} · ${material.symbol}` : "Custom / Generic");
  if (material) {
    row(identityRows, "Space group", `${material.space_group.symbol} · No. ${material.space_group.number}`);
  }
  fragment.append(identity);

  if (visualization?.mode === "unit") {
    const accounting = section("Cell Accounting");
    const rows = listIn(accounting);
    const terms = visualization.accounting.terms.map((term) =>
      term.share_denominator === 1
        ? String(term.count)
        : `${term.count}\\times\\frac{${term.share_numerator}}{${term.share_denominator}}`
    );
    row(rows, "Shared-site contributions",
        `${terms.join("+")}=${visualization.accounting.effective_atom_count}`, true);
    note(accounting, "Effective-atom counts follow site sharing, not rendered sphere volume. Clip at Cell Walls changes appearance only.");
    fragment.append(accounting);
  } else if (visualization?.mode === "coordination") {
    const shell = section("Coordination Shell");
    const rows = listIn(shell);
    row(rows, "Central site", `Site ${visualization.center_id}`);
    row(rows, "Coordination number", String(visualization.coordination_number));
    const distanceGroups = visualization.distance_groups;
    if (distanceGroups.length === 1) {
      row(rows, "Neighbour distance",
          lengthMath("d", distanceGroups[0].distance), true);
    } else {
      row(rows, "Distance groups", distanceGroups.map((group) =>
        `${group.count} at ${decimal(group.distance, 4, 3)} Å`).join(" · "));
      if (hcp) note(shell, "Non-ideal c/a splits distances within the standard 12-site HCP shell.");
    }
    row(rows, "Coordination polyhedron", visualization.polyhedron.name);
    note(shell, "Neighbour Lines are geometric guides, not chemical bond predictions.");
    fragment.append(shell);
  } else if (visualization?.mode === "stacking") {
    const stacking = section("Layer Stacking");
    const rows = listIn(stacking);
    row(rows, "Direction", visualization.direction);
    row(rows, "Repeating sequence", visualization.sequence);
    row(rows, "Layers shown", visualization.layers.map((layer) => layer.label).join("–"));
    row(rows, "Natural layer spacing",
        lengthMath("d", visualization.natural_spacing), true);
    note(stacking, structure === "SC" || structure === "BCC"
      ? "These square layers are not close-packed. Separation changes only the view."
      : "The triangular layers are close-packed in the ideal geometry. Separation changes only the view.");
    fragment.append(stacking);
  }

  const lattice = section("Geometry");
  const latticeRows = listIn(lattice);
  row(latticeRows, "Lattice constant", lengthMath("a", parameters.a, 4, 2), true);
  if (hcp) {
    row(latticeRows, "Basal constants", String.raw`a=b`, true);
    row(latticeRows, "Prism height", lengthMath("c", parameters.c, 4, 3), true);
    row(latticeRows, "Axial ratio", `c/a=${decimal(parameters.c_over_a, 4, 4)}`, true);
    row(latticeRows, "Cell angles", String.raw`\alpha=\beta=90^\circ,\ \gamma=120^\circ`, true);
  } else {
    row(latticeRows, "Equal axes", String.raw`a=b=c`, true);
    row(latticeRows, "Cell angles", String.raw`\alpha=\beta=\gamma=90^\circ`, true);
  }
  row(latticeRows, "Nearest-neighbour distance",
      lengthMath(String.raw`d_{\mathrm{nn}}`, cell.nearest_neighbor_distance), true);
  row(latticeRows, "Touching radius", lengthMath("r", cell.touching_radius), true);
  row(latticeRows, hcp ? "Primitive-cell volume" : "Unit-cell volume",
      volumeMath(hcp ? String.raw`V_{\mathrm{primitive}}` : "V", cell.volume), true);
  if (hcp) {
    row(latticeRows, "Educational-prism volume",
        volumeMath(String.raw`V_{\mathrm{prism}}`, cell.display_cell_volume), true);
  }
  fragment.append(lattice);

  const packing = section("Packing");
  const packingRows = listIn(packing);
  row(packingRows, hcp ? "Effective atoms per educational prism" : "Effective atoms per unit cell",
      String(cell.display_cell_atom_count));
  row(packingRows, hcp ? "Primitive basis" : "Computational basis",
      `${cell.basis_atom_count} ${cell.basis_atom_count === 1 ? "atom" : "atoms"}`);
  row(packingRows, "Coordination number", String(cell.coordination_number));
  row(packingRows, "Atomic packing factor", `\\mathrm{APF}=${decimal(cell.packing_factor, 4, 4)}`, true);
  if (hcp) {
    note(packing, "CN = 12 is the standard HCP coordination; non-ideal c/a may split neighbour distances.");
  }
  fragment.append(packing);

  if (hcp && visualization?.mode === "crystal") {
    const cluster = section("HCP display cluster");
    const clusterRows = listIn(cluster);
    const display = data.display;
    row(clusterRows, "Basal arrangement", `${display.display_size} × ${display.display_size} prisms · one prism high`);
    row(clusterRows, "Educational prisms", String(display.prism_count));
    row(clusterRows, "Effective atoms by cell accounting", String(display.effective_atom_count));
    row(clusterRows, "Primitive cells represented", String(display.primitive_cell_count));
    row(clusterRows, "Visible lattice sites", String(display.site_count));
    const stacking = display.stacking;
    row(clusterRows, "Layers (bottom → top)", stacking.layers.map((layer) => layer.label).join("–"));
    row(clusterRows, "Repeating stacking", `${stacking.sequence}…`);
    note(cluster, "Visible boundary sites are shared; they are not additional effective atoms.");
    fragment.append(cluster);
  }

  if (material) {
    const materialGroup = section("Material");
    const materialRows = listIn(materialGroup);
    row(materialRows, "Element / phase", `${material.name} · ${material.symbol}`);
    row(materialRows, "Atomic number", String(material.atomic_number));
    row(materialRows, material.atomic_mass_note ? "Reference isotope molar mass" : "Atomic molar mass",
        `${decimal(material.atomic_mass_g_mol, 7)} g/mol`);
    row(materialRows, "Theoretical density",
        `\\rho=${decimal(material.theoretical_density_g_cm3, 3, 3)}\\,\\mathrm{g\\,cm^{-3}}`, true);
    note(materialGroup, material.phase_note);
    note(materialGroup, material.conditions);
    if (material.atomic_mass_note) note(materialGroup, material.atomic_mass_note);
    fragment.append(materialGroup);
  }

  fragment.append(selectedSitePanel);

  const relations = section("Relations");
  const equationList = document.createElement("ul");
  equationList.className = "equation-list";
  const equations = material
    ? [...EQUATIONS[structure], String.raw`\rho=\frac{nM}{N_{\mathrm A}V}`]
    : EQUATIONS[structure];
  for (const latex of equations) {
    const item = document.createElement("li");
    renderMath(item, latex);
    equationList.append(item);
  }
  relations.append(equationList);
  if (material) note(relations, "Density uses the computational cell volume in Å³ converted to cm³.");
  fragment.append(relations);

  if (material) addSources(fragment, material.sources);
  container.replaceChildren(fragment);
}

export function renderSelectedSite(container, site, data, viewMode = "crystal") {
  const fragment = document.createDocumentFragment();
  if (!site) {
    note(fragment, viewMode === "unit"
      ? "Site selection is disabled in Unit Cell view."
      : "Click a lattice site in the 3D model to inspect its coordinates.");
    container.replaceChildren(fragment);
    return;
  }

  const identity = document.createElement("p");
  identity.className = "selected-site-identity";
  identity.textContent = data.material
    ? `Site ${site.id} · ${data.material.name} (${data.material.symbol}) lattice site`
    : `Site ${site.id} · Generic ${data.structure} lattice site`;
  fragment.append(identity);

  const role = document.createElement("p");
  role.className = "selected-site-role";
  const layer = site.layer ? ` · ${site.layer} layer` :
    site.layer_label ? ` · ${site.layer_label} layer` : "";
  role.textContent = `${SITE_ROLES[site.role] || "Lattice site"}${layer}`;
  fragment.append(role);

  if (site.role === "neighbor" && Number.isFinite(site.distance_from_center)) {
    const neighbourDistance = listIn(fragment);
    row(neighbourDistance, "Distance from central site",
        lengthMath("d", site.distance_from_center), true);
  }

  const latticeHeading = document.createElement("h4");
  latticeHeading.textContent = "Lattice coordinates (u, v, w)";
  fragment.append(latticeHeading);
  const latticeEquation = document.createElement("div");
  latticeEquation.className = "selected-equation";
  renderMath(latticeEquation,
    `\\left(u,v,w\\right)=\\left(${site.fractional.map(latticeNumber).join(",\\,")}\\right)`);
  fragment.append(latticeEquation);

  const cartesianHeading = document.createElement("h4");
  cartesianHeading.textContent = "Cartesian coordinates (Å)";
  fragment.append(cartesianHeading);
  const coordinates = listIn(fragment);
  for (const [index, axis] of ["x", "y", "z"].entries()) {
    row(coordinates, axis,
      `${cartesianNumber(site.cartesian[index])}\\,\\text{\\AA}`, true);
  }

  const relation = document.createElement("div");
  relation.className = "selected-equation coordinate-relation";
  // Explanatory notation only: the displayed coordinates come from Python.
  renderMath(relation, String.raw`\mathbf{r}=u\mathbf{a}_1+v\mathbf{a}_2+w\mathbf{a}_3`);
  fragment.append(relation);
  note(fragment, data.visualization?.mode === "stacking"
    ? "Layers are visually separated; coordinates remain in the original crystallographic frame."
    : "Coordinates use the crystallographic frame, before visual centering or rotation.");
  container.replaceChildren(fragment);
}

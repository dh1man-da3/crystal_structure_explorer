"use strict";

import { renderProperties, renderSelectedSite } from "./properties.js";

const VIEW_HELP = {
  crystal: "Explore a finite crystal and its repeating unit cells.",
  unit: "Compare full hard spheres with their portions inside one conventional cell.",
  coordination: "Explore one atom's nearest neighbours and their optional polyhedron.",
  stacking: "Separate consecutive atomic planes to see how layers build the structure.",
};

const status = document.getElementById("status");
const hudStructure = document.getElementById("hud-structure");
const toolbarSummary = document.getElementById("toolbar-summary");
const modeLegend = document.getElementById("mode-legend");
const viewerContainer = document.getElementById("viewer");
const viewerStage = document.getElementById("viewer-stage");
const fullscreenButton = document.getElementById("toggle-fullscreen");
const fullscreenError = document.getElementById("fullscreen-error");
const propertyPanel = document.getElementById("properties");
const propertyContent = document.getElementById("property-content");
const selectedSitePanel = document.getElementById("selected-site");
const selectedSiteContent = document.getElementById("selected-site-content");
const clearSelectionButton = document.getElementById("clear-selection");
const viewButtons = {
  reset: document.getElementById("reset-view"),
  axes: document.getElementById("toggle-axes"),
  autoRotate: document.getElementById("toggle-auto-rotate"),
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const compactWorkspace = window.matchMedia("(max-width: 900px)");
const advancedControls = document.getElementById("advanced-controls");
// Keep the primary controls close to the model on compact screens. Native
// details retains keyboard/touch behavior; desktop keeps the existing fields open.
function syncCompactControls() {
  if (compactWorkspace.matches && advancedControls.contains(document.activeElement)) {
    advancedControls.querySelector("summary").focus();
  }
  advancedControls.open = !compactWorkspace.matches;
}
syncCompactControls();
compactWorkspace.addEventListener("change", syncCompactControls);
const viewState = {
  axes: false,
  autoRotate: false,
  atomSize: 100,
  colorScheme: "material",
  neighbourNetwork: false,
  unitClip: true,
  cubicCellLines: "outer",
  hcpCellLines: "outer",
  contactDiagonals: false,
  neighbourLines: true,
  polyhedron: false,
};
const controls = {
  panel: document.getElementById("controls"),
  viewModes: Object.fromEntries(["crystal", "unit", "coordination", "stacking"].map(
    (mode) => [mode, document.getElementById(`view-${mode}`)]
  )),
  viewModeHelp: document.getElementById("view-mode-help"),
  structure: document.getElementById("structure"),
  material: document.getElementById("material"),
  materialError: document.getElementById("material-error"),
  aSlider: document.getElementById("a-slider"),
  aNumber: document.getElementById("a-number"),
  aError: document.getElementById("a-error"),
  cubicSizeGroup: document.getElementById("cubic-size-group"),
  cubicSize: document.getElementById("cubic-size"),
  hcpClusterGroup: document.getElementById("hcp-cluster-group"),
  hcpDisplaySize: document.getElementById("hcp-display-size"),
  cellLinesGroup: document.getElementById("cell-lines-group"),
  contactDiagonalsGroup: document.getElementById("contact-diagonals-group"),
  coordinationGroup: document.getElementById("coordination-controls-group"),
  neighbourLines: document.getElementById("neighbour-lines"),
  polyhedron: document.getElementById("coordination-polyhedron"),
  layerSeparationGroup: document.getElementById("layer-separation-group"),
  layerSeparationSlider: document.getElementById("layer-separation-slider"),
  layerSeparationNumber: document.getElementById("layer-separation-number"),
  layerSeparationNote: document.getElementById("layer-separation-note"),
  ratioGroup: document.getElementById("hcp-ratio-group"),
  ratioSlider: document.getElementById("ratio-slider"),
  ratioNumber: document.getElementById("ratio-number"),
  ratioError: document.getElementById("ratio-error"),
  atomSizeGroup: document.getElementById("atom-size-group"),
  atomSizeSlider: document.getElementById("atom-size-slider"),
  atomSizeValue: document.getElementById("atom-size-value"),
  colorSchemeGroup: document.getElementById("color-scheme-group"),
  colorSchemes: {
    material: document.getElementById("color-material"),
    role: document.getElementById("color-role"),
  },
  neighbourNetworkGroup: document.getElementById("neighbour-network-group"),
  neighbourNetwork: document.getElementById("neighbour-network"),
  unitClipGroup: document.getElementById("unit-clip-group"),
  unitClip: document.getElementById("unit-clip"),
  cellLines: {
    outer: document.getElementById("cell-lines-outer"),
    all: document.getElementById("cell-lines-all"),
    off: document.getElementById("cell-lines-off"),
  },
  contactDiagonals: document.getElementById("contact-diagonals"),
  contactDiagonalsNote: document.getElementById("contact-diagonals-note"),
};

const idealHcpRatio = Number(controls.panel.dataset.idealHcpRatio);
const state = {
  viewMode: "crystal",
  structure: "SC",
  a: 3,
  cubicSize: 3,
  hcpDisplaySize: 2,
  hcpCOverA: idealHcpRatio,
  layerSeparation: 160,
  materialId: null,
};

let materials = [];
let viewer;
let currentData;
let selectedSite = null;
let lastValidStatus = "";
let pendingTimer;
let activeController;
let updateVersion = 0;
let initialCatalogReady;
let fullscreenReturnScroll = null;
let fullscreenPending = false;
const fullscreenSupported = typeof viewerStage.requestFullscreen === "function" &&
  typeof document.exitFullscreen === "function";

function finishStartup(success) {
  if (!document.body.classList.contains("app-booting") &&
      !document.body.classList.contains("app-startup-error")) return;
  document.body.classList.remove("app-booting", "app-startup-error");
  document.body.classList.add(success ? "app-ready" : "app-startup-error");
  controls.panel.inert = false;
  controls.panel.setAttribute("aria-busy", "false");
  fullscreenButton.disabled = !success || !fullscreenSupported;
  if (!success && !currentData) {
    const note = propertyContent.querySelector(".property-note");
    if (note) note.textContent = "Properties will appear when a structure loads.";
  }
}

function syncFullscreenState() {
  const wasFullscreen = viewerStage.classList.contains("is-fullscreen");
  const active = document.fullscreenElement === viewerStage;
  fullscreenPending = false;
  fullscreenButton.disabled = !viewer || !fullscreenSupported ||
    document.body.classList.contains("app-booting") ||
    document.body.classList.contains("app-startup-error");
  viewerStage.classList.toggle("is-fullscreen", active);
  viewerStage.classList.remove("fullscreen-transitioning");
  fullscreenButton.setAttribute("aria-label", active ? "Exit fullscreen" : "Enter fullscreen");
  fullscreenButton.title = active ? "Exit fullscreen" : "Enter fullscreen";
  fullscreenError.hidden = true;
  viewer?.resize();
  // The browser may finalize the native fullscreen dimensions one frame later.
  requestAnimationFrame(() => {
    viewer?.resize();
    if (wasFullscreen && !active && fullscreenReturnScroll) {
      window.scrollTo(fullscreenReturnScroll.x, fullscreenReturnScroll.y);
      fullscreenReturnScroll = null;
    }
  });
}

async function toggleFullscreen() {
  if (!fullscreenSupported || !viewer || fullscreenPending) return;
  fullscreenPending = true;
  fullscreenButton.disabled = true;
  fullscreenError.hidden = true;
  viewerStage.classList.add("fullscreen-transitioning");
  try {
    if (document.fullscreenElement === viewerStage) {
      await document.exitFullscreen();
    } else {
      fullscreenReturnScroll ||= { x: window.scrollX, y: window.scrollY };
      await viewerStage.requestFullscreen();
    }
  } catch (error) {
    fullscreenPending = false;
    fullscreenButton.disabled = false;
    fullscreenReturnScroll = null;
    viewerStage.classList.remove("fullscreen-transitioning");
    fullscreenError.textContent = "Fullscreen is unavailable in this browser window.";
    fullscreenError.hidden = false;
  }
}

function syncViewButtons() {
  viewButtons.axes.setAttribute("aria-pressed", String(viewState.axes));
  viewButtons.autoRotate.setAttribute("aria-pressed", String(viewState.autoRotate));
}

const roleLabels = {
  corner: "Corner",
  body_center: "Body centre",
  face_center: "Face centre",
  basal_center: "Basal centre",
  interior: "Interior",
};
const rolePalette = {
  corner: "var(--viz-corner)",
  body_center: "var(--viz-body-center)",
  face_center: "var(--viz-face-center)",
  basal_center: "var(--viz-basal-center)",
  interior: "var(--viz-interior)",
};

function renderModeLegend(data) {
  const mode = data.visualization.mode;
  let entries = [];
  if ((mode === "crystal" || mode === "unit") && viewState.colorScheme === "role") {
    if (mode === "unit") {
      entries = data.visualization.accounting.terms.map((term) => {
        const fraction = term.share_denominator === 1
          ? String(term.share_numerator)
          : `${term.share_numerator}/${term.share_denominator}`;
        return [`${roleLabels[term.role]} · ${fraction} per cell`, rolePalette[term.role]];
      });
    } else {
      const roles = new Set(data.display.sites.map((site) => site.role));
      entries = Object.keys(roleLabels).filter((role) => roles.has(role))
        .map((role) => [roleLabels[role], rolePalette[role]]);
    }
  } else if (mode === "coordination") {
    entries = [["Central atom", "var(--viz-central)"],
      ["Nearest neighbours", "var(--viz-neighbour)"]];
    if (viewState.polyhedron && data.visualization.polyhedron?.supported) {
      entries.push(["Coordination polyhedron", "var(--viz-polyhedron)"]);
    }
  } else if (mode === "stacking") {
    const labels = new Set(data.visualization.layers.map((layer) => layer.label));
    entries = [...labels].map((label) => [
      `${label} layer`, `var(--viz-layer-${label.toLowerCase()})`,
    ]);
  }
  modeLegend.hidden = entries.length === 0;
  const items = entries.map(([label, color]) => {
    const item = document.createElement("div");
    item.className = "mode-legend-item";
    const swatch = document.createElement("span");
    swatch.className = "mode-legend-swatch";
    swatch.style.setProperty("--swatch", color);
    swatch.setAttribute("aria-hidden", "true");
    const caption = document.createElement("span");
    caption.textContent = label;
    item.append(swatch, caption);
    return item;
  });
  modeLegend.replaceChildren(...items);
}

function readyStatus(data) {
  const { structure, parameters, display, visualization } = data;
  if (visualization.mode === "unit") {
    const description = structure === "HCP" ? "Educational Prism" : "Unit Cell";
    const siteLabel = structure === "SC" ? "visible corner sites" : "visible sites";
    const effective = visualization.accounting.effective_atom_count;
    return `${structure} · ${description} · ${visualization.site_count} ${siteLabel} · ` +
      `${effective} effective ${effective === 1 ? "atom" : "atoms"}`;
  }
  if (visualization.mode === "coordination") {
    const shape = viewState.polyhedron ? ` · ${visualization.polyhedron.name}` : "";
    return `${structure} · Coordination Shell · CN = ${visualization.coordination_number}${shape}`;
  }
  if (visualization.mode === "stacking") {
    return `${structure} · ${visualization.sequence} along ${visualization.direction} · ` +
      `${state.layerSeparation}% visual separation`;
  }
  const aText = formatValue(parameters.a, 2);
  return structure === "HCP"
    ? `${display.display_size}×${display.display_size} prism cluster · ` +
      `${display.site_count} visible lattice sites · a = ${aText} Å · ` +
      `c/a = ${parameters.c_over_a.toFixed(data.material ? 4 : 3)}`
    : `${parameters.supercell_size}×${parameters.supercell_size}×${parameters.supercell_size} ` +
      `unit cells · ${display.site_count} visible lattice points · a = ${aText} Å`;
}

function effectiveCellLinesMode(structure = state.structure) {
  return structure === "HCP" ? viewState.hcpCellLines : viewState.cubicCellLines;
}

function syncDisplayControls() {
  const supportsContact = ["crystal", "unit"].includes(state.viewMode) &&
    (state.structure === "BCC" || state.structure === "FCC");
  controls.cellLinesGroup.hidden = state.viewMode !== "crystal";
  controls.contactDiagonalsGroup.hidden = !supportsContact;
  controls.coordinationGroup.hidden = state.viewMode !== "coordination";
  controls.atomSizeGroup.hidden = state.viewMode === "unit";
  controls.atomSizeSlider.value = String(viewState.atomSize);
  controls.atomSizeValue.textContent = `${viewState.atomSize}%`;
  controls.colorSchemeGroup.hidden = !["crystal", "unit"].includes(state.viewMode);
  controls.colorSchemes[viewState.colorScheme].checked = true;
  controls.neighbourNetworkGroup.hidden = state.viewMode !== "crystal";
  controls.neighbourNetwork.checked = viewState.neighbourNetwork;
  controls.unitClipGroup.hidden = state.viewMode !== "unit";
  controls.unitClip.checked = viewState.unitClip;
  controls.cellLines[effectiveCellLinesMode()].checked = true;
  controls.contactDiagonals.disabled = !supportsContact;
  controls.contactDiagonals.checked = supportsContact && viewState.contactDiagonals;
  controls.neighbourLines.checked = viewState.neighbourLines;
  controls.polyhedron.checked = viewState.polyhedron;
  controls.contactDiagonalsNote.textContent = supportsContact
    ? "Geometric contact guides, not chemical bonds."
    : "Available for BCC and FCC only; these guides are not chemical bonds.";
}

function syncReducedMotion() {
  if (reducedMotion.matches) {
    viewState.autoRotate = false;
    viewer?.setAutoRotate(false);
    viewButtons.autoRotate.disabled = true;
    viewButtons.autoRotate.title = "Unavailable while Reduce Motion is enabled";
    viewButtons.autoRotate.setAttribute("aria-describedby", "reduced-motion-note");
  } else {
    viewButtons.autoRotate.disabled = false;
    viewButtons.autoRotate.title = "Slowly rotate the view";
    viewButtons.autoRotate.removeAttribute("aria-describedby");
  }
  syncViewButtons();
}

function formatValue(value, decimals) {
  // Show the ideal irrational ratio compactly, but preserve extra precision
  // supplied manually in the numeric fields.
  if (value === idealHcpRatio) return value.toFixed(decimals);
  const text = String(value);
  const places = text.includes(".") ? text.split(".")[1].length : 0;
  return places > decimals ? text : value.toFixed(decimals);
}

function siteSelected(site) {
  selectedSite = state.viewMode === "unit" ? null : site;
  renderSelectedSite(selectedSiteContent, selectedSite, currentData, state.viewMode);
  selectedSitePanel.classList.toggle("is-selected", selectedSite !== null);
  clearSelectionButton.hidden = state.viewMode === "unit" || selectedSite === null;
}

function setInputError(input, messageElement, invalid) {
  input.setAttribute("aria-invalid", String(invalid));
  messageElement.hidden = !invalid;
}

function syncMaterialOptions() {
  const options = [new Option("Custom / Generic", "")];
  for (const material of materials.filter((item) =>
    item.structure.toUpperCase() === state.structure)) {
    options.push(new Option(`${material.name} · ${material.symbol}`, material.id));
  }
  controls.material.replaceChildren(...options);
  controls.material.value = state.materialId || "";
}

function syncControls() {
  controls.viewModes[state.viewMode].checked = true;
  controls.viewModeHelp.textContent = VIEW_HELP[state.viewMode];
  controls.structure.value = state.structure.toLowerCase();
  syncMaterialOptions();
  controls.aSlider.value = String(state.a);
  controls.aNumber.value = formatValue(state.a, 2);
  controls.cubicSize.value = String(state.cubicSize);
  controls.hcpDisplaySize.value = String(state.hcpDisplaySize);
  controls.layerSeparationSlider.value = String(state.layerSeparation);
  controls.layerSeparationNumber.value = String(state.layerSeparation);
  controls.ratioSlider.value = String(state.hcpCOverA);
  controls.ratioNumber.value = state.materialId
    ? state.hcpCOverA.toFixed(6)
    : formatValue(state.hcpCOverA, 3);
  const hcp = state.structure === "HCP";
  controls.cubicSizeGroup.hidden = hcp || state.viewMode !== "crystal";
  controls.hcpClusterGroup.hidden = !hcp || state.viewMode !== "crystal";
  controls.layerSeparationGroup.hidden = state.viewMode !== "stacking";
  controls.ratioGroup.hidden = !hcp;
  syncDisplayControls();
  setInputError(controls.aNumber, controls.aError, false);
  setInputError(controls.ratioNumber, controls.ratioError, false);
}

function requestUrl() {
  const query = new URLSearchParams({
    structure: state.structure.toLowerCase(),
    a: String(state.a),
    size: String(state.structure === "HCP" ? 1 : state.cubicSize),
    view: state.viewMode,
  });
  if (state.structure === "HCP") {
    query.set("c_over_a", String(state.hcpCOverA));
    query.set("display_size", String(state.hcpDisplaySize));
  }
  if (state.materialId) query.set("material", state.materialId);
  return `/api/structure?${query}`;
}

async function loadMaterials() {
  try {
    const response = await fetch("/api/materials");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.materials) || !data.materials.every((item) =>
      typeof item.id === "string" && typeof item.structure === "string" &&
      Number.isFinite(item.lattice?.a_angstrom)
    )) throw new Error("Invalid material catalog response");
    materials = data.materials;
    syncMaterialOptions();
  } catch (error) {
    controls.materialError.hidden = false;
    console.error("Material presets could not be loaded:", error);
  }
}

function queueUpdate(delay = 0, preserveView = false) {
  // Invalidate immediately, even while a slider's debounce timer is running.
  updateVersion += 1;
  const version = updateVersion;
  viewer?.clearSelection();
  viewer?.setSelectionEnabled(false);
  clearTimeout(pendingTimer);
  activeController?.abort();
  activeController = undefined;
  propertyPanel.setAttribute("aria-busy", "true");
  status.classList.remove("error");
  status.dataset.state = "loading";
  status.textContent = lastValidStatus
    ? `Updating ${state.structure}…`
    : `Loading ${state.structure} structure…`;
  if (delay) {
    pendingTimer = setTimeout(() => loadStructure(version, preserveView), delay);
  } else {
    loadStructure(version, preserveView);
  }
}

async function loadStructure(version, preserveView) {
  const controller = new AbortController();
  activeController = controller;
  const expectedStructure = state.structure;
  const expectedMode = state.viewMode;
  const expectedSize = expectedStructure === "HCP" ? 1 : state.cubicSize;
  const expectedDisplaySize = expectedStructure === "HCP" ? state.hcpDisplaySize : null;
  const expectedMaterial = state.materialId;
  try {
    const response = await fetch(requestUrl(), { signal: controller.signal });
    if (version !== updateVersion) return;
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.error?.message || `Request failed (HTTP ${response.status}).`);
    }
    const data = await response.json();
    if (version !== updateVersion) return;
    if (document.body.classList.contains("app-booting") ||
        document.body.classList.contains("app-startup-error")) {
      await initialCatalogReady;
      if (version !== updateVersion) return;
    }
    if (
      data.structure !== expectedStructure ||
      data.parameters?.view !== expectedMode ||
      data.visualization?.mode !== expectedMode ||
      data.parameters?.supercell_size !== expectedSize ||
      (expectedDisplaySize !== null && (
        data.parameters?.display_size !== expectedDisplaySize ||
        data.display?.kind !== "hcp_prism_cluster" ||
        data.display?.display_size !== expectedDisplaySize ||
        !Number.isInteger(data.display?.prism_count) || data.display.prism_count < 1 ||
        !Number.isInteger(data.display?.effective_atom_count) ||
        !Number.isInteger(data.display?.primitive_cell_count) ||
        typeof data.display?.stacking?.sequence !== "string" ||
        !Array.isArray(data.display?.stacking?.layers) ||
        !data.display.stacking.layers.every((layer) => typeof layer.label === "string")
      )) ||
      (data.material?.id || null) !== expectedMaterial ||
      !Array.isArray(data.cell?.lattice_vectors) ||
      !Array.isArray(data.supercell?.atoms) ||
      data.supercell.atom_count !== data.supercell.atoms.length ||
      !Array.isArray(data.display?.sites) ||
      data.display.site_count !== data.display.sites.length ||
      (expectedMode !== "crystal" && (
        !Array.isArray(data.visualization?.sites) ||
        data.visualization.site_count !== data.visualization.sites.length
      ))
    ) {
      throw new Error("The structure API returned incomplete data.");
    }

    const { CrystalViewer } = await import("./viewer.js");
    if (version !== updateVersion) return;
    if (!window.katex?.render) throw new Error("The local math renderer did not load.");
    if (!viewer) {
      viewer = new CrystalViewer(viewerContainer, siteSelected);
      viewer.setAxesVisible(viewState.axes);
      viewer.setAutoRotate(viewState.autoRotate);
    }
    viewer.setAtomScale(viewState.atomSize);
    viewer.setColorScheme(viewState.colorScheme);
    viewer.setNeighbourNetworkVisible(viewState.neighbourNetwork);
    viewer.setUnitClippingVisible(viewState.unitClip);
    viewer.setNeighbourLinesVisible(viewState.neighbourLines);
    viewer.setPolyhedronVisible(viewState.polyhedron);
    if (viewer.layerSeparation !== state.layerSeparation) {
      viewer.setLayerSeparation(state.layerSeparation);
    }
    viewer.setCellLinesMode(effectiveCellLinesMode(data.structure));
    viewer.setContactDiagonalsVisible(
      viewState.contactDiagonals &&
      (expectedMode === "unit"
        ? data.visualization.contact_diagonals?.supported
        : expectedMode === "crystal" && data.display.contact_diagonals?.supported)
    );
    viewer.renderStructure(data, { preserveView });
    renderProperties(propertyContent, data, selectedSitePanel);
    renderModeLegend(data);
    siteSelected(null);
    propertyPanel.setAttribute("aria-busy", "false");

    // Reveal the Explorer only after the first real crystal frame and its
    // calculated properties are both in place. No minimum delay is imposed.
    if (document.body.classList.contains("app-booting") ||
        document.body.classList.contains("app-startup-error")) {
      await viewer.whenFirstFrame();
      if (version !== updateVersion) return;
    }
    currentData = data;
    viewer.setSelectionEnabled(expectedMode !== "unit");
    viewButtons.reset.disabled = false;
    lastValidStatus = readyStatus(data);
    hudStructure.textContent = data.structure;
    toolbarSummary.textContent = data.material
      ? `${data.structure} · ${data.material.name} · ${data.material.symbol}`
      : `${data.structure} · Custom / Generic`;
    status.dataset.state = "ready";
    status.textContent = lastValidStatus;
    finishStartup(true);
  } catch (error) {
    if (error.name === "AbortError" || version !== updateVersion) return;
    if ((document.body.classList.contains("app-booting") ||
         document.body.classList.contains("app-startup-error")) && viewer &&
        !viewer.firstFrameRendered) {
      // A failed first WebGL frame must not leave a stopped renderer in place.
      viewer.dispose();
      viewer = undefined;
    }
    viewer?.setSelectionEnabled(state.viewMode !== "unit");
    propertyPanel.setAttribute("aria-busy", "false");
    status.classList.add("error");
    status.dataset.state = "error";
    status.textContent = `Could not update ${expectedStructure}: ${error.message}`;
    console.error("Crystal viewer update failed:", error);
    finishStartup(false);
  } finally {
    if (activeController === controller) activeController = undefined;
  }
}

function useCustomIfChanged(key, value) {
  if (state.materialId && state[key] !== value) {
    state.materialId = null;
    controls.material.value = "";
  }
}

function validNumber(input, min, max) {
  const raw = input.value.trim();
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= min && value <= max ? value : null;
}

function sliderChanged(slider, numberInput, message, key, decimals) {
  const value = Number(Number(slider.value).toFixed(decimals));
  useCustomIfChanged(key, value);
  state[key] = value;
  slider.value = String(value);
  numberInput.value = value.toFixed(decimals);
  setInputError(numberInput, message, false);
  queueUpdate(130, true);
}

function numberChanged(numberInput, slider, message, key, min, max) {
  const value = validNumber(numberInput, min, max);
  setInputError(numberInput, message, value === null);
  if (value === null) return;
  useCustomIfChanged(key, value);
  state[key] = value;
  slider.value = String(value);
  queueUpdate(130, true);
}

function finishNumberInput(numberInput, slider, message, key, decimals) {
  numberInput.value = key === "hcpCOverA" && state.materialId
    ? state[key].toFixed(6)
    : formatValue(state[key], decimals);
  slider.value = String(state[key]);
  setInputError(numberInput, message, false);
}

controls.structure.addEventListener("change", () => {
  state.structure = controls.structure.value.toUpperCase();
  state.materialId = null;
  syncControls();
  queueUpdate();
});

for (const [mode, input] of Object.entries(controls.viewModes)) {
  input.addEventListener("change", () => {
    if (!input.checked || state.viewMode === mode) return;
    state.viewMode = mode;
    siteSelected(null);
    syncControls();
    queueUpdate();
  });
}

clearSelectionButton.addEventListener("click", () => viewer?.clearSelection());

// A pointer click may scroll the page to focus this bottom-corner button
// before its click event. Capture the original page position earlier.
fullscreenButton.addEventListener("pointerdown", () => {
  if (document.fullscreenElement !== viewerStage) {
    fullscreenReturnScroll = { x: window.scrollX, y: window.scrollY };
  }
});
fullscreenButton.addEventListener("click", toggleFullscreen);
document.addEventListener("fullscreenchange", syncFullscreenState);
if (!fullscreenSupported) {
  fullscreenButton.hidden = true;
} else {
  fullscreenButton.title = "Enter fullscreen";
}

viewButtons.reset.addEventListener("click", () => viewer?.resetView());
viewButtons.axes.addEventListener("click", () => {
  viewState.axes = !viewState.axes;
  viewer?.setAxesVisible(viewState.axes);
  syncViewButtons();
});
viewButtons.autoRotate.addEventListener("click", () => {
  if (reducedMotion.matches) return;
  viewState.autoRotate = !viewState.autoRotate;
  viewer?.setAutoRotate(viewState.autoRotate);
  syncViewButtons();
});
reducedMotion.addEventListener("change", syncReducedMotion);

for (const [mode, input] of Object.entries(controls.cellLines)) {
  input.addEventListener("change", () => {
    if (!input.checked || input.disabled) return;
    if (state.structure === "HCP") viewState.hcpCellLines = mode;
    else viewState.cubicCellLines = mode;
    viewer?.setCellLinesMode(mode);
  });
}

controls.contactDiagonals.addEventListener("change", () => {
  if (controls.contactDiagonals.disabled) return;
  viewState.contactDiagonals = controls.contactDiagonals.checked;
  viewer?.setContactDiagonalsVisible(viewState.contactDiagonals);
});

controls.neighbourLines.addEventListener("change", () => {
  viewState.neighbourLines = controls.neighbourLines.checked;
  viewer?.setNeighbourLinesVisible(viewState.neighbourLines);
});

controls.polyhedron.addEventListener("change", () => {
  viewState.polyhedron = controls.polyhedron.checked;
  viewer?.setPolyhedronVisible(viewState.polyhedron);
  if (currentData?.visualization?.mode === "coordination" &&
      state.viewMode === "coordination") {
    renderModeLegend(currentData);
    lastValidStatus = readyStatus(currentData);
    if (status.dataset.state === "ready") status.textContent = lastValidStatus;
  }
});

controls.atomSizeSlider.addEventListener("input", () => {
  viewState.atomSize = Number(controls.atomSizeSlider.value);
  controls.atomSizeValue.textContent = `${viewState.atomSize}%`;
  viewer?.setAtomScale(viewState.atomSize); // Display-only; no API request.
});

for (const [scheme, input] of Object.entries(controls.colorSchemes)) {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    viewState.colorScheme = scheme;
    viewer?.setColorScheme(scheme); // Display-only; preserve selection and camera.
    if (currentData?.visualization?.mode === state.viewMode) renderModeLegend(currentData);
  });
}

controls.neighbourNetwork.addEventListener("change", () => {
  viewState.neighbourNetwork = controls.neighbourNetwork.checked;
  viewer?.setNeighbourNetworkVisible(viewState.neighbourNetwork);
});

controls.unitClip.addEventListener("change", () => {
  viewState.unitClip = controls.unitClip.checked;
  viewer?.setUnitClippingVisible(viewState.unitClip);
});

controls.material.addEventListener("change", () => {
  const selected = materials.find((item) => item.id === controls.material.value);
  if (selected && selected.structure.toUpperCase() === state.structure) {
    state.materialId = selected.id;
    state.a = selected.lattice.a_angstrom;
    if (state.structure === "HCP") state.hcpCOverA = selected.lattice.c_over_a;
  } else {
    state.materialId = null;
  }
  syncControls();
  queueUpdate();
});

controls.cubicSize.addEventListener("change", () => {
  state.cubicSize = Number(controls.cubicSize.value);
  queueUpdate();
});

controls.hcpDisplaySize.addEventListener("change", () => {
  state.hcpDisplaySize = Number(controls.hcpDisplaySize.value);
  queueUpdate();
});

function setLayerSeparation(value) {
  state.layerSeparation = value;
  controls.layerSeparationSlider.value = String(value);
  controls.layerSeparationNumber.value = String(value);
  controls.layerSeparationNumber.setAttribute("aria-invalid", "false");
  controls.layerSeparationNote.textContent =
    "100% is natural layer spacing; larger values separate layers visually.";
  viewer?.setLayerSeparation(value); // Visual-only: no Flask request.
  if (currentData?.visualization?.mode === "stacking" && state.viewMode === "stacking") {
    lastValidStatus = readyStatus(currentData);
    if (status.dataset.state === "ready") status.textContent = lastValidStatus;
  }
}

controls.layerSeparationSlider.addEventListener("input", () => {
  setLayerSeparation(Number(controls.layerSeparationSlider.value));
});
controls.layerSeparationNumber.addEventListener("input", () => {
  const value = Number(controls.layerSeparationNumber.value);
  const valid = controls.layerSeparationNumber.value.trim() !== "" &&
    Number.isInteger(value) && value >= 100 && value <= 250;
  controls.layerSeparationNumber.setAttribute("aria-invalid", String(!valid));
  controls.layerSeparationNote.textContent = valid
    ? "100% is natural layer spacing; larger values separate layers visually."
    : "Enter a whole percentage from 100% to 250%.";
  if (valid) setLayerSeparation(value);
});
controls.layerSeparationNumber.addEventListener("blur", () => {
  setLayerSeparation(state.layerSeparation);
});

controls.aSlider.addEventListener("input", () => {
  sliderChanged(controls.aSlider, controls.aNumber, controls.aError, "a", 2);
});
controls.aNumber.addEventListener("input", () => {
  numberChanged(controls.aNumber, controls.aSlider, controls.aError, "a", 2, 6);
});
controls.aNumber.addEventListener("blur", () => {
  finishNumberInput(controls.aNumber, controls.aSlider, controls.aError, "a", 2);
});

controls.ratioSlider.addEventListener("input", () => {
  sliderChanged(controls.ratioSlider, controls.ratioNumber, controls.ratioError, "hcpCOverA", 3);
});
controls.ratioNumber.addEventListener("input", () => {
  numberChanged(controls.ratioNumber, controls.ratioSlider, controls.ratioError, "hcpCOverA", 1.2, 2);
});
controls.ratioNumber.addEventListener("blur", () => {
  finishNumberInput(controls.ratioNumber, controls.ratioSlider, controls.ratioError, "hcpCOverA", 3);
});

async function startExplorer() {
  syncControls();
  syncReducedMotion();
  // Start both local requests together, but wait for the catalog before the
  // first reveal. Catalog failure is reported inline without blocking the viewer.
  initialCatalogReady = loadMaterials();
  queueUpdate();
}

startExplorer().catch((error) => {
  status.classList.add("error");
  status.dataset.state = "error";
  status.textContent = `Could not start the Explorer: ${error.message}`;
  console.error("Explorer startup failed:", error);
  finishStartup(false);
});

"use strict";

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Stencil passes must finish before the ordinary sphere surface (renderOrder 0).
// A unique three-step sequence keeps one atom/plane's stencil from another's.
const UNIT_CAP_FIRST_ORDER = -10000;
const SELECTION_CLICK_THRESHOLD = 5; // CSS pixels, independent of device pixel ratio.
const SITE_ROLE_COLORS = {
  corner: "--viz-corner",
  body_center: "--viz-body-center",
  face_center: "--viz-face-center",
  basal_center: "--viz-basal-center",
  interior: "--viz-interior",
};

export class CrystalViewer {
  constructor(container, onSiteSelected = () => {}) {
    this.container = container;
    this.onSiteSelected = onSiteSelected;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0b121b);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 2000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, stencil: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.localClippingEnabled = false;
    this.renderer.autoClearStencil = true;
    this.hasStencil = Boolean(this.renderer.getContext().getContextAttributes()?.stencil);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.screenSpacePanning = true;
    this.controls.autoRotateSpeed = 0.7;
    this.controls.touches.ONE = THREE.TOUCH.ROTATE;
    this.controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.1);
    keyLight.position.set(8, 12, 10);
    this.scene.add(keyLight);

    this.structureGroup = new THREE.Group();
    this.scene.add(this.structureGroup);
    this.siteGroup = null;
    this.boundaryGroup = null;
    this.cellGridLines = null;
    this.contactDiagonalLines = null;
    this.neighbourNetworkLines = null;
    this.coordinationGuideLines = null;
    this.coordinationPolyhedronGroup = null;
    this.axesGroup = null;
    this.viewMode = "crystal";
    this.layerSeparation = 160;
    this.stackingAxis = null;
    this.stackingNaturalSpacing = 0;
    this.unitClippingPlanes = [];
    this.cellLinesMode = "outer";
    this.showContactDiagonals = false;
    this.showNeighbourLines = true;
    this.showPolyhedron = false;
    this.showNeighbourNetwork = false;
    this.showUnitClipping = true;
    this.atomScale = 100;
    this.colorScheme = "material";
    this.showAxes = false;
    this.viewCenter = new THREE.Vector3();
    this.defaultViewDirection = new THREE.Vector3(1, 0.8, 1).normalize();
    this.siteMeshes = [];
    this.unitCapMeshes = [];
    this.unitStencilMeshes = [];
    this.unitCapMaterials = [];
    this.siteMaterials = null;
    this.visualBaseRadius = 0;
    this.unitAtomRadius = 0;
    this.selectedSite = null;
    this.selectedMesh = null;
    this.selectionEnabled = false;
    this.pointerStart = null;
    this.activePointers = new Set();
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    // One reusable halo follows a selected mesh through centering and HCP rotation.
    this.selectionHalo = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 16),
      new THREE.MeshBasicMaterial({
        color: this.paletteColor("--viz-selection"), side: THREE.BackSide,
      })
    );
    const selectionColor = this.paletteColor("--viz-selection");
    this.selectedMaterial = new THREE.MeshStandardMaterial({
      color: selectionColor,
      emissive: selectionColor.clone().multiplyScalar(0.16),
      roughness: 0.42, metalness: 0.05,
    });
    this.selectedOriginalMaterial = null;
    this.selectionHalo.visible = false;
    this.resources = [];
    this.generatedBasisPositions = [];
    this.displaySiteCount = 0;
    this.boundsRadius = 0;
    this.fitDistance = 0;
    this.hasRenderableStructure = false;
    this.firstFrameRendered = false;
    this.firstFramePromise = new Promise((resolve, reject) => {
      this.resolveFirstFrame = resolve;
      this.rejectFirstFrame = reject;
    });
    // The application awaits this promise; the handler also avoids an
    // unhandled rejection if WebGL fails before that await is attached.
    this.firstFramePromise.catch(() => {});
    this.lastCanvasSize = { width: 0, height: 0, pixelRatio: 0 };

    this.handlePointerDown = this.handlePointerDown.bind(this);
    this.handlePointerMove = this.handlePointerMove.bind(this);
    this.handlePointerUp = this.handlePointerUp.bind(this);
    this.cancelPointer = this.cancelPointer.bind(this);
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", this.handlePointerDown);
    // OrbitControls captures the first pointer. Document listeners also see a
    // second finger released outside the canvas, and are attached only once.
    this.pointerDocument = canvas.ownerDocument;
    this.pointerDocument.addEventListener("pointermove", this.handlePointerMove);
    this.pointerDocument.addEventListener("pointerup", this.handlePointerUp);
    this.pointerDocument.addEventListener("pointercancel", this.cancelPointer);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.animate = this.animate.bind(this);
    this.animationFrame = requestAnimationFrame(this.animate);
  }

  clearStructure() {
    this.clearSelection();
    this.hasRenderableStructure = false;
    this.structureGroup.clear();
    for (const resource of this.resources) resource.dispose();
    this.resources = [];
    this.siteGroup = null;
    this.boundaryGroup = null;
    this.cellGridLines = null;
    this.contactDiagonalLines = null;
    this.neighbourNetworkLines = null;
    this.coordinationGuideLines = null;
    this.coordinationPolyhedronGroup = null;
    this.axesGroup = null;
    this.siteMeshes = [];
    this.unitCapMeshes = [];
    this.unitStencilMeshes = [];
    this.unitCapMaterials = [];
    this.siteMaterials = null;
    this.visualBaseRadius = 0;
    this.unitAtomRadius = 0;
    this.stackingAxis = null;
    this.stackingNaturalSpacing = 0;
    this.unitClippingPlanes = [];
    this.selectionHalo.material.clippingPlanes = [];
    this.selectionHalo.material.needsUpdate = true;
    this.selectedMaterial.clippingPlanes = [];
    this.selectedMaterial.needsUpdate = true;
    this.generatedBasisPositions = [];
    this.displaySiteCount = 0;
    this.boundsRadius = 0;
    this.fitDistance = 0;
    this.container.dataset.generatedBasisPositionCount = "0";
    this.container.dataset.displaySiteCount = "0";
    this.container.dataset.unitCapCount = "0";
    this.container.dataset.neighbourNetworkSegmentCount = "0";
  }

  paletteColor(name) {
    // CSS is the single color source shared with the viewer's HTML legend.
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (!value) throw new Error(`Missing visualization palette color: ${name}`);
    return new THREE.Color(value);
  }

  makeAtomMaterial(colorName, { central = false } = {}) {
    const color = this.paletteColor(colorName);
    const material = new THREE.MeshStandardMaterial({
      color, roughness: 0.48, metalness: 0.08,
      ...(central ? { emissive: color.clone().multiplyScalar(0.12) } : {}),
    });
    this.resources.push(material);
    return material;
  }

  makeRoleMaterials(sites) {
    const material = this.makeAtomMaterial("--viz-material");
    const roles = new Map();
    for (const site of sites) {
      if (!roles.has(site.role)) {
        roles.set(site.role, this.makeAtomMaterial(
          SITE_ROLE_COLORS[site.role] || "--viz-material"
        ));
      }
    }
    this.siteMaterials = { material, roles, all: [material, ...roles.values()] };
  }

  siteColorForRole(role) {
    return this.paletteColor(this.colorScheme === "role"
      ? SITE_ROLE_COLORS[role] || "--viz-material" : "--viz-material");
  }

  applySiteColors() {
    if (!["crystal", "unit"].includes(this.viewMode) || !this.siteMaterials) return;
    for (const mesh of this.siteMeshes) {
      const desired = this.colorScheme === "role"
        ? this.siteMaterials.roles.get(mesh.userData.displaySite.role) ||
          this.siteMaterials.material
        : this.siteMaterials.material;
      if (mesh === this.selectedMesh) this.selectedOriginalMaterial = desired;
      else mesh.material = desired;
    }
    for (const { material, role } of this.unitCapMaterials) {
      material.color.copy(this.siteColorForRole(role)).multiplyScalar(0.84);
    }
  }

  applyAtomScale() {
    if (this.viewMode === "unit") return; // Physical hard spheres never scale.
    const scale = this.atomScale / 100;
    for (const mesh of this.siteMeshes) {
      mesh.scale.setScalar(scale * (mesh.userData.baseVisualScale || 1));
    }
    this.selectionHalo.scale.setScalar(this.visualBaseRadius * 1.28 * scale *
      (this.selectedMesh?.userData.baseVisualScale || 1));
  }

  setAtomScale(percent) {
    if (!Number.isFinite(percent) || percent < 30 || percent > 120) {
      throw new Error("Atom Size must be between 30% and 120%.");
    }
    this.atomScale = percent;
    this.applyAtomScale();
  }

  setColorScheme(scheme) {
    if (!["material", "role"].includes(scheme)) {
      throw new Error("Unknown site color scheme.");
    }
    this.colorScheme = scheme;
    this.applySiteColors();
  }

  setNeighbourNetworkVisible(visible) {
    this.showNeighbourNetwork = Boolean(visible);
    this.updateGuideVisibility();
  }

  setUnitClippingVisible(visible) {
    this.showUnitClipping = Boolean(visible);
    this.updateUnitClippingVisibility();
  }

  updateUnitClippingVisibility() {
    const active = this.viewMode === "unit" && this.showUnitClipping;
    this.renderer.localClippingEnabled = active;
    for (const mesh of [...this.unitStencilMeshes, ...this.unitCapMeshes]) {
      mesh.visible = active;
    }
    this.container.dataset.unitClipping = String(active);
  }

  clearSelection() {
    if (this.selectedMesh && this.selectedOriginalMaterial) {
      this.selectedMesh.material = this.selectedOriginalMaterial;
    }
    this.selectionHalo.visible = false;
    this.selectedMesh = null;
    this.selectedOriginalMaterial = null;
    this.container.dataset.selectedSiteId = "";
    if (this.selectedSite !== null) {
      this.selectedSite = null;
      this.onSiteSelected(null);
    }
  }

  setSelectionEnabled(enabled) {
    this.selectionEnabled = enabled;
    if (!enabled) this.pointerStart = null;
  }

  setCellLinesMode(mode) {
    if (!["outer", "all", "off"].includes(mode)) {
      throw new Error("Unknown cell-lines mode.");
    }
    this.cellLinesMode = mode;
    this.updateGuideVisibility();
  }

  setContactDiagonalsVisible(visible) {
    this.showContactDiagonals = Boolean(visible);
    this.updateGuideVisibility();
  }

  setNeighbourLinesVisible(visible) {
    this.showNeighbourLines = Boolean(visible);
    this.updateGuideVisibility();
  }

  setPolyhedronVisible(visible) {
    this.showPolyhedron = Boolean(visible);
    this.updateGuideVisibility();
  }

  updateGuideVisibility() {
    if (this.boundaryGroup) {
      this.boundaryGroup.visible = this.viewMode === "unit" ||
        (this.viewMode === "crystal" && this.cellLinesMode === "outer");
    }
    if (this.cellGridLines) {
      this.cellGridLines.visible = this.viewMode === "crystal" && this.cellLinesMode === "all";
    }
    if (this.contactDiagonalLines) {
      this.contactDiagonalLines.visible =
        ["crystal", "unit"].includes(this.viewMode) && this.showContactDiagonals;
    }
    if (this.neighbourNetworkLines) {
      this.neighbourNetworkLines.visible =
        this.viewMode === "crystal" && this.showNeighbourNetwork;
    }
    if (this.coordinationGuideLines) {
      this.coordinationGuideLines.visible =
        this.viewMode === "coordination" && this.showNeighbourLines;
    }
    if (this.coordinationPolyhedronGroup) {
      this.coordinationPolyhedronGroup.visible =
        this.viewMode === "coordination" && this.showPolyhedron;
    }
  }

  setAxesVisible(visible) {
    this.showAxes = Boolean(visible);
    if (this.axesGroup) this.axesGroup.visible = this.showAxes;
  }

  setAutoRotate(enabled) {
    this.controls.autoRotate = Boolean(enabled);
  }

  resetView() {
    if (this.fitDistance <= 0) return;
    const wasRotating = this.controls.autoRotate;
    const hadDamping = this.controls.enableDamping;
    this.controls.autoRotate = false;
    // Flush any remaining orbit-drag momentum before restoring the fitted view.
    this.controls.enableDamping = false;
    this.controls.update();
    this.controls.target.copy(this.viewCenter);
    this.camera.up.set(0, 1, 0);
    this.camera.position.copy(this.viewCenter).addScaledVector(
      this.defaultViewDirection, this.fitDistance
    );
    this.controls.update();
    this.controls.enableDamping = hadDamping;
    this.controls.autoRotate = wasRotating;
  }

  handlePointerDown(event) {
    this.activePointers.add(event.pointerId);
    // Once a gesture has multiple fingers, none of its releases is a tap.
    if (this.activePointers.size > 1) {
      this.pointerStart = null;
      return;
    }
    // Unit Cell teaches clipped hard-sphere sharing, not individual sites.
    // Skip picking entirely (including caps) without affecting OrbitControls.
    if (!this.selectionEnabled || this.viewMode === "unit" ||
        event.button !== 0 || !event.isPrimary) {
      this.pointerStart = null;
      return;
    }
    this.pointerStart = {
      id: event.pointerId, x: event.clientX, y: event.clientY, maxMovement: 0,
    };
  }

  handlePointerMove(event) {
    const start = this.pointerStart;
    if (!start || start.id !== event.pointerId) return;
    start.maxMovement = Math.max(start.maxMovement,
      Math.hypot(event.clientX - start.x, event.clientY - start.y));
  }

  handlePointerUp(event) {
    this.activePointers.delete(event.pointerId);
    const start = this.pointerStart;
    if (start?.id === event.pointerId) this.pointerStart = null;
    if (!start || start.id !== event.pointerId || !this.selectionEnabled ||
        this.viewMode === "unit") return;
    // Moving away and back is still an orbit drag, not a selection click.
    const movement = Math.max(start.maxMovement,
      Math.hypot(event.clientX - start.x, event.clientY - start.y));
    if (movement > SELECTION_CLICK_THRESHOLD || this.activePointers.size > 0) return;

    const rect = this.renderer.domElement.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0 ||
        event.clientX < rect.left || event.clientX > rect.right ||
        event.clientY < rect.top || event.clientY > rect.bottom) return;
    this.pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    // Three.js raycasting sees the full mesh even when its shader is clipped.
    // Ignore hits on portions of a Unit Cell sphere that are not displayed.
    const candidates = this.viewMode === "unit"
      ? [...this.siteMeshes, ...this.unitCapMeshes] : this.siteMeshes;
    const hit = this.raycaster.intersectObjects(candidates, false).find((intersection) => {
      if (!this.unitClippingPlanes.every((plane) =>
        plane.distanceToPoint(intersection.point) >= -1e-7)) return false;
      if (!intersection.object.userData.siteSphere) return true;
      // Raycasting ignores both shader clipping and stencil. Reject the
      // square part of the cap plane outside its parent sphere's cross-section.
      const sphereCenter = intersection.object.userData.siteSphere
        .getWorldPosition(new THREE.Vector3());
      return intersection.point.distanceToSquared(sphereCenter) <=
        this.unitAtomRadius ** 2 + 1e-7;
    });
    if (!hit) {
      this.clearSelection();
      return;
    }
    const mesh = hit.object.userData.siteSphere || hit.object;
    const site = mesh.userData.displaySite;
    if (this.selectedMesh && this.selectedOriginalMaterial) {
      this.selectedMesh.material = this.selectedOriginalMaterial;
    }
    this.selectedOriginalMaterial = mesh.material;
    mesh.material = this.selectedMaterial;
    this.selectedSite = site;
    this.selectedMesh = mesh;
    this.selectionHalo.position.copy(mesh.position);
    this.applyAtomScale();
    this.selectionHalo.visible = true;
    this.container.dataset.selectedSiteId = String(site.id);
    this.onSiteSelected(site);
  }

  cancelPointer(event) {
    this.activePointers.delete(event.pointerId);
    this.pointerStart = null;
  }

  addGuideSegments(segments, color, opacity, { depthWrite = true } = {}) {
    // Crystallographic endpoints come from Python; flatten them into one draw object.
    const positions = new Float32Array(segments.length * 6);
    segments.forEach((segment, index) => {
      positions.set(segment.start, index * 6);
      positions.set(segment.end, index * 6 + 3);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({
      color, transparent: true, opacity, depthTest: true, depthWrite,
    });
    this.resources.push(geometry, material);
    const lines = new THREE.LineSegments(geometry, material);
    this.structureGroup.add(lines);
    return lines;
  }

  addCoordinationPolyhedron(neighbours, polyhedron) {
    // Python supplies the convex-hull topology. Only triangulation of each
    // ordered convex face is done here for Three.js rendering.
    const facePositions = [];
    for (const face of polyhedron.faces) {
      const first = neighbours[face[0]].cartesian;
      for (let index = 1; index < face.length - 1; index += 1) {
        facePositions.push(...first, ...neighbours[face[index]].cartesian,
          ...neighbours[face[index + 1]].cartesian);
      }
    }
    const faceGeometry = new THREE.BufferGeometry();
    faceGeometry.setAttribute("position", new THREE.Float32BufferAttribute(facePositions, 3));
    faceGeometry.computeVertexNormals();
    const faceMaterial = new THREE.MeshStandardMaterial({
      color: this.paletteColor("--viz-polyhedron"),
      roughness: 0.75,
      metalness: 0,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.15,
      depthTest: true,
      depthWrite: false,
    });
    this.resources.push(faceGeometry, faceMaterial);
    const faces = new THREE.Mesh(faceGeometry, faceMaterial);
    // Opaque atoms are rendered first; the transparent cage then draws its
    // faces and edges in a stable order without writing into the depth buffer.
    faces.renderOrder = 1;

    const edgePositions = [];
    for (const [start, end] of polyhedron.edges) {
      edgePositions.push(...neighbours[start].cartesian, ...neighbours[end].cartesian);
    }
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: this.paletteColor("--viz-polyhedron"),
      transparent: true,
      opacity: 0.72,
      depthTest: true,
      depthWrite: false,
    });
    this.resources.push(edgeGeometry, edgeMaterial);
    const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
    edges.renderOrder = 2;

    this.coordinationPolyhedronGroup = new THREE.Group();
    this.coordinationPolyhedronGroup.add(faces, edges);
    this.structureGroup.add(this.coordinationPolyhedronGroup);
  }

  addUnitCellCaps(sphereGeometry, localPlanes, radius) {
    // Follow Three.js's clipping-stencil example, but isolate every atom/plane
    // pair. A cap is clipped by *other* cell planes, making a cubic corner's
    // cut face a quarter disk rather than an entire circle.
    if (!this.hasStencil) return; // Keep uncapped clipping if stencil is unavailable.
    const capGeometry = new THREE.PlaneGeometry(radius * 2.02, radius * 2.02);
    this.resources.push(capGeometry);
    const localZ = new THREE.Vector3(0, 0, 1);
    let passIndex = 0;

    localPlanes.forEach((localPlane, planeIndex) => {
      const worldPlane = this.unitClippingPlanes[planeIndex];
      const stencilMaterial = (side, operation) => {
        const material = new THREE.MeshBasicMaterial({ side });
        material.depthWrite = false;
        material.depthTest = false;
        material.colorWrite = false;
        material.clippingPlanes = [worldPlane];
        material.stencilWrite = true;
        material.stencilFunc = THREE.AlwaysStencilFunc;
        material.stencilFail = operation;
        material.stencilZFail = operation;
        material.stencilZPass = operation;
        this.resources.push(material);
        return material;
      };
      const backMaterial = stencilMaterial(THREE.BackSide, THREE.IncrementWrapStencilOp);
      const frontMaterial = stencilMaterial(THREE.FrontSide, THREE.DecrementWrapStencilOp);
      const capMaterials = new Map();
      const capMaterialFor = (role) => {
        if (!capMaterials.has(role)) {
          const material = new THREE.MeshStandardMaterial({
            color: this.siteColorForRole(role).multiplyScalar(0.84),
            roughness: 0.62,
            metalness: 0.05,
            side: THREE.DoubleSide,
            clippingPlanes: this.unitClippingPlanes.filter((_, index) => index !== planeIndex),
            stencilWrite: true,
            stencilRef: 0,
            stencilFunc: THREE.NotEqualStencilFunc,
            stencilFail: THREE.ReplaceStencilOp,
            stencilZFail: THREE.ReplaceStencilOp,
            stencilZPass: THREE.ReplaceStencilOp,
          });
          this.resources.push(material);
          this.unitCapMaterials.push({ material, role });
          capMaterials.set(role, material);
        }
        return capMaterials.get(role);
      };

      for (const sphere of this.siteMeshes) {
        const center = sphere.position;
        if (Math.abs(localPlane.distanceToPoint(center)) >= radius * (1 - 1e-8)) {
          continue; // This atom is not cut by this plane.
        }
        const order = UNIT_CAP_FIRST_ORDER + passIndex * 3;
        passIndex += 1;

        const back = new THREE.Mesh(sphereGeometry, backMaterial);
        const front = new THREE.Mesh(sphereGeometry, frontMaterial);
        back.position.copy(center);
        front.position.copy(center);
        back.renderOrder = order;
        front.renderOrder = order + 1;
        back.frustumCulled = false;
        front.frustumCulled = false;

        const cap = new THREE.Mesh(
          capGeometry, capMaterialFor(sphere.userData.displaySite.role)
        );
        localPlane.projectPoint(center, cap.position);
        cap.quaternion.setFromUnitVectors(localZ, localPlane.normal.clone().negate());
        cap.renderOrder = order + 2;
        cap.frustumCulled = false;
        cap.userData.siteSphere = sphere;
        // The next atom/plane pair must start with an empty stencil buffer.
        cap.onAfterRender = (renderer) => renderer.clearStencil();

        this.siteGroup.add(back, front, cap);
        this.unitStencilMeshes.push(back, front);
        this.unitCapMeshes.push(cap);
      }
    });
    this.container.dataset.unitCapCount = String(this.unitCapMeshes.length);
  }

  renderStructure(data, options = {}) {
    const mode = data.visualization?.mode || "crystal";
    if (mode === "crystal") {
      this.renderCrystal(data, options);
    } else if (["unit", "coordination", "stacking"].includes(mode)) {
      this.renderEducationalView(data, options);
    } else {
      throw new Error("The API returned an unknown visualization mode.");
    }
    this.hasRenderableStructure = true;
  }

  whenFirstFrame() {
    return this.firstFramePromise;
  }

  renderCrystal(data, { preserveView = false } = {}) {
    const generatedBasisPositions = data.supercell?.atoms;
    const displaySites = data.display?.sites;
    const vectors = data.cell?.lattice_vectors;
    const size = data.parameters?.supercell_size;
    if (
      !Array.isArray(generatedBasisPositions) ||
      !Array.isArray(displaySites) ||
      data.display?.site_count !== displaySites.length ||
      !Array.isArray(vectors) ||
      vectors.length !== 3 ||
      !vectors.every((row) => Array.isArray(row) && row.length === 3 && row.every(Number.isFinite)) ||
      !Number.isInteger(size) || size < 1 ||
      !Number.isFinite(data.cell?.touching_radius)
    ) {
      throw new Error("The structure data is not suitable for the viewer.");
    }
    if (![generatedBasisPositions, displaySites].every((sites) => sites.every((site) =>
      Array.isArray(site.cartesian) &&
      site.cartesian.length === 3 &&
      site.cartesian.every(Number.isFinite)
    ))) {
      throw new Error("The API returned an invalid site coordinate.");
    }
    if (!displaySites.every((site) =>
      Number.isInteger(site.id) && site.id >= 0 &&
      Array.isArray(site.fractional) && site.fractional.length === 3 &&
      site.fractional.every(Number.isFinite) && typeof site.role === "string"
    ) || new Set(displaySites.map((site) => site.id)).size !== displaySites.length) {
      throw new Error("The API returned invalid display-site metadata.");
    }
    const boundary = data.display?.boundary;
    if (data.structure === "HCP" && !boundary) {
      throw new Error("The API did not provide the HCP cluster boundary.");
    }
    if (boundary && (
      !Array.isArray(boundary.vertices) ||
      !boundary.vertices.every((point) => Array.isArray(point) && point.length === 3 && point.every(Number.isFinite)) ||
      !Array.isArray(boundary.edges) ||
      !boundary.edges.every((edge) => Array.isArray(edge) && edge.length === 2 &&
        edge.every((index) => Number.isInteger(index) && index >= 0 && index < boundary.vertices.length))
    )) {
      throw new Error("The API returned an invalid display boundary.");
    }
    const cellGrid = data.display?.cell_grid;
    const contactDiagonals = data.display?.contact_diagonals;
    const neighbourNetwork = data.display?.neighbour_network;
    const validGuide = (guide) => guide && typeof guide.supported === "boolean" &&
      Number.isInteger(guide.segment_count) && guide.segment_count >= 0 &&
      Array.isArray(guide.segments) && guide.segment_count === guide.segments.length &&
      guide.segments.every((segment) => [segment.start, segment.end].every((point) =>
        Array.isArray(point) && point.length === 3 && point.every(Number.isFinite))) &&
      (guide.supported || guide.segment_count === 0);
    if (!validGuide(cellGrid) || !validGuide(contactDiagonals)) {
      throw new Error("The API returned invalid display guide geometry.");
    }
    const displayIds = new Set(displaySites.map((site) => site.id));
    if (!validGuide(neighbourNetwork) || !neighbourNetwork.supported ||
        !neighbourNetwork.segments.every((segment) =>
          Number.isInteger(segment.start_site_id) &&
          Number.isInteger(segment.end_site_id) &&
          displayIds.has(segment.start_site_id) &&
          displayIds.has(segment.end_site_id) &&
          segment.start_site_id !== segment.end_site_id &&
          Number.isFinite(segment.distance) && segment.distance > 0)) {
      throw new Error("The API returned invalid neighbour-network geometry.");
    }
    if (data.structure === "HCP" && (!cellGrid.supported || contactDiagonals.supported)) {
      throw new Error("The API returned incomplete HCP cell-line geometry.");
    }

    const previousOffset = this.camera.position.clone().sub(this.controls.target);
    const previousDistance = previousOffset.length();
    const previousFitDistance = this.fitDistance;
    this.clearStructure();
    this.viewMode = "crystal";
    this.defaultViewDirection.set(1, 0.8, 1).normalize();
    this.renderer.localClippingEnabled = false;
    this.generatedBasisPositions = generatedBasisPositions;
    this.structureGroup.position.set(0, 0, 0);
    this.structureGroup.rotation.set(0, 0, 0);

    const latticeVectors = vectors.map((row) => new THREE.Vector3(...row));

    // This radius is visual only; the API's physical touching radius is unchanged.
    const displayRadius = data.cell.touching_radius * 0.42;
    this.visualBaseRadius = displayRadius;
    const atomGeometry = new THREE.SphereGeometry(displayRadius, 24, 16);
    this.resources.push(atomGeometry);
    this.makeRoleMaterials(displaySites);

    for (const site of displaySites) {
      const mesh = new THREE.Mesh(atomGeometry, this.siteMaterials.material);
      mesh.position.set(...site.cartesian);
      mesh.userData.displaySite = site;
      mesh.userData.baseVisualScale = 1;
      this.structureGroup.add(mesh);
      this.siteMeshes.push(mesh);
      this.displaySiteCount += 1;
    }
    this.applySiteColors();
    this.applyAtomScale();

    const edgePoints = [];
    let extent;
    if (boundary) {
      // The whole HCP cluster exterior comes from Python; no tiling rule lives here.
      for (const [start, end] of boundary.edges) {
        edgePoints.push(
          new THREE.Vector3(...boundary.vertices[start]),
          new THREE.Vector3(...boundary.vertices[end])
        );
      }
    } else {
      // Preserve the existing cubic supercell outline from API lattice vectors.
      extent = latticeVectors.map((vector) => vector.clone().multiplyScalar(size));
      const corner = (i, j, k) => new THREE.Vector3()
        .addScaledVector(extent[0], i)
        .addScaledVector(extent[1], j)
        .addScaledVector(extent[2], k);
      for (let i = 0; i <= 1; i += 1) {
        for (let j = 0; j <= 1; j += 1) {
          for (let k = 0; k <= 1; k += 1) {
            if (i === 0) edgePoints.push(corner(i, j, k), corner(1, j, k));
            if (j === 0) edgePoints.push(corner(i, j, k), corner(i, 1, k));
            if (k === 0) edgePoints.push(corner(i, j, k), corner(i, j, 1));
          }
        }
      }
    }
    const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x61758a });
    this.resources.push(edgeGeometry, edgeMaterial);
    this.boundaryGroup = new THREE.Group();
    this.boundaryGroup.add(new THREE.LineSegments(edgeGeometry, edgeMaterial));
    this.structureGroup.add(this.boundaryGroup);

    if (cellGrid.supported) {
      this.cellGridLines = this.addGuideSegments(cellGrid.segments, 0x607487, 0.6);
    }
    if (contactDiagonals.supported) {
      this.contactDiagonalLines = this.addGuideSegments(
        contactDiagonals.segments, this.paletteColor("--viz-guide"), 0.4
      );
    }
    this.neighbourNetworkLines = this.addGuideSegments(
      neighbourNetwork.segments, this.paletteColor("--viz-guide"), 0.32,
      { depthWrite: false }
    );
    this.container.dataset.neighbourNetworkSegmentCount =
      String(neighbourNetwork.segment_count);
    this.updateGuideVisibility();

    // Center only the rendered group; the API coordinates remain untouched.
    if (boundary) {
      // Present the API's vertical z-axis upright on screen (Three.js uses y-up).
      this.structureGroup.rotation.x = -Math.PI / 2;
      this.structureGroup.updateMatrixWorld(true);
      const center = new THREE.Box3().setFromObject(this.structureGroup).getCenter(new THREE.Vector3());
      this.structureGroup.position.copy(center).multiplyScalar(-1);
    } else {
      this.structureGroup.position.copy(extent[0]).add(extent[1]).add(extent[2]).multiplyScalar(-0.5);
    }
    this.structureGroup.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(this.structureGroup);
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    this.boundsRadius = Math.max(sphere.radius, 1);
    this.viewCenter.copy(sphere.center);
    this.controls.target.copy(sphere.center);
    this.fitDistance = this.requiredDistance();
    const viewDirection = previousDistance > 0
      ? previousOffset.normalize()
      : new THREE.Vector3(1, 0.8, 1).normalize();
    // Parameter edits move the camera only partway with the changing model.
    // This keeps expansion/contraction visible, with bounds to avoid clipping
    // or a tiny model after a large change. Structure/size changes fully refit.
    const scaledDistance = previousFitDistance > 0
      ? previousDistance * Math.sqrt(this.fitDistance / previousFitDistance)
      : this.fitDistance;
    const cameraDistance = preserveView
      ? Math.min(Math.max(scaledDistance, this.fitDistance * 0.85), this.fitDistance * 1.5)
      : this.fitDistance;
    this.camera.position.copy(sphere.center).addScaledVector(
      viewDirection, cameraDistance
    );
    this.camera.far = Math.max(2000, this.boundsRadius * 100);
    this.camera.updateProjectionMatrix();
    this.controls.update();
    // Axes are visual guides, so their labels do not affect crystal centering or fit.
    this.addAxes(latticeVectors, size);
    this.container.dataset.generatedBasisPositionCount = String(generatedBasisPositions.length);
    this.container.dataset.displaySiteCount = String(this.displaySiteCount);
    this.container.dataset.visualizationMode = "crystal";
    this.structureGroup.add(this.selectionHalo);
  }

  renderEducationalView(data, { preserveView = false } = {}) {
    const view = data.visualization;
    const sites = view.sites;
    const vectors = data.cell?.lattice_vectors;
    const scientificSites = data.supercell?.atoms;
    const pointIsValid = (point) => Array.isArray(point) && point.length === 3 &&
      point.every(Number.isFinite);
    if (!Array.isArray(scientificSites) || !Array.isArray(sites) ||
        view.site_count !== sites.length || !Array.isArray(vectors) ||
        vectors.length !== 3 || !vectors.every(pointIsValid) ||
        !sites.every((site) => Number.isInteger(site.id) && site.id >= 0 &&
          pointIsValid(site.cartesian) && pointIsValid(site.fractional) &&
          typeof site.role === "string") ||
        new Set(sites.map((site) => site.id)).size !== sites.length ||
        !Number.isFinite(data.cell?.touching_radius)) {
      throw new Error("The API returned invalid visualization geometry.");
    }
    const boundary = view.boundary;
    if (view.mode === "unit" && (!boundary ||
        !Array.isArray(boundary.vertices) || !boundary.vertices.every(pointIsValid) ||
        !Array.isArray(boundary.edges) || !boundary.edges.every((edge) =>
          Array.isArray(edge) && edge.length === 2 && edge.every((index) =>
            Number.isInteger(index) && index >= 0 && index < boundary.vertices.length)) ||
        !Array.isArray(view.clipping_planes) ||
        view.clipping_planes.length !== (data.structure === "HCP" ? 8 : 6) ||
        !view.clipping_planes.every((plane) => pointIsValid(plane.normal) &&
          Number.isFinite(plane.constant)) ||
        !Number.isFinite(view.physical_radius) || view.physical_radius <= 0)) {
      throw new Error("The API returned invalid Unit Cell geometry.");
    }
    if (view.mode === "coordination") {
      const neighbours = sites.slice(1);
      const polyhedron = view.polyhedron;
      const validIndex = (index) => Number.isInteger(index) &&
        index >= 0 && index < neighbours.length;
      if (sites[0]?.role !== "central" || neighbours.length !== view.coordination_number ||
          !neighbours.every((site) => site.role === "neighbor") ||
          !Array.isArray(view.distance_groups) ||
          view.distance_groups.length === 0 ||
          !view.distance_groups.every((group) => Number.isFinite(group.distance) &&
            group.distance > 0 && Number.isInteger(group.count) && group.count > 0) ||
          view.distance_groups.reduce((total, group) => total + group.count, 0) !==
            view.coordination_number ||
          !Array.isArray(view.guide_segments) ||
          view.guide_segments.length !== view.coordination_number ||
          !view.guide_segments.every((segment) =>
            pointIsValid(segment.start) && pointIsValid(segment.end)) ||
          !polyhedron?.supported || typeof polyhedron.name !== "string" ||
          polyhedron.vertex_count !== neighbours.length ||
          !Array.isArray(polyhedron.faces) ||
          !Array.isArray(polyhedron.edges) ||
          polyhedron.face_count !== polyhedron.faces.length ||
          polyhedron.edge_count !== polyhedron.edges.length ||
          !polyhedron.faces.every((face) => Array.isArray(face) &&
            face.length >= 3 && face.every(validIndex)) ||
          !polyhedron.edges.every((edge) => Array.isArray(edge) &&
            edge.length === 2 && edge.every(validIndex))) {
        throw new Error("The API returned invalid Coordination geometry.");
      }
    }
    if (view.mode === "stacking" && (!pointIsValid(view.axis) ||
        !Number.isFinite(view.natural_spacing) || view.natural_spacing <= 0 ||
        !Number.isFinite(view.physical_radius) || view.physical_radius <= 0 ||
        !sites.every((site) => Number.isInteger(site.layer_index) &&
          site.layer_index >= 0 && site.layer_index <= 2 &&
          ["A", "B", "C"].includes(site.layer_label)))) {
      throw new Error("The API returned invalid Stacking geometry.");
    }

    const previousOffset = this.camera.position.clone().sub(this.controls.target);
    const previousDistance = previousOffset.length();
    const previousFitDistance = this.fitDistance;
    this.clearStructure();
    this.viewMode = view.mode;
    // Stacked planes read best from a shallower angle; an asymmetric view
    // avoids looking directly through a coordination neighbour.
    this.defaultViewDirection.set(...(
      view.mode === "stacking" ? [1, 0.38, 1] :
        view.mode === "coordination" ? [1, 0.57, 1.31] : [1, 0.8, 1]
    )).normalize();
    this.renderer.localClippingEnabled = view.mode === "unit" && this.showUnitClipping;
    this.generatedBasisPositions = scientificSites;
    this.structureGroup.position.set(0, 0, 0);
    this.structureGroup.rotation.set(0, 0, 0);
    this.structureGroup.quaternion.identity();
    this.siteGroup = new THREE.Group();
    this.structureGroup.add(this.siteGroup);

    // The Unit Cell uses Python's physical touching radius. The other two
    // educational views use a smaller base sphere for legibility; Atom Size
    // later scales only its Three.js mesh, never the scientific radius.
    const radius = view.mode === "unit" ? view.physical_radius :
      view.mode === "stacking" ? view.physical_radius * 0.78 :
        data.cell.touching_radius * 0.42;
    this.visualBaseRadius = radius;
    if (view.mode === "unit") this.unitAtomRadius = radius;
    const sphereGeometry = new THREE.SphereGeometry(radius, 32, 24);
    this.resources.push(sphereGeometry);
    if (view.mode === "unit") this.makeRoleMaterials(sites);
    const centralMaterial = view.mode === "coordination"
      ? this.makeAtomMaterial("--viz-central", { central: true }) : null;
    const neighbourMaterial = view.mode === "coordination"
      ? this.makeAtomMaterial("--viz-neighbour") : null;
    const layerMaterials = view.mode === "stacking" ? {
      A: this.makeAtomMaterial("--viz-layer-a"),
      B: this.makeAtomMaterial("--viz-layer-b"),
      C: this.makeAtomMaterial("--viz-layer-c"),
    } : null;
    for (const site of sites) {
      const siteMaterial = view.mode === "coordination" && site.role === "central"
        ? centralMaterial : view.mode === "stacking"
          ? layerMaterials[site.layer_label] : view.mode === "coordination"
            ? neighbourMaterial : this.siteMaterials.material;
      const mesh = new THREE.Mesh(sphereGeometry, siteMaterial);
      mesh.position.set(...site.cartesian);
      mesh.userData.baseVisualScale = view.mode === "coordination" &&
        site.role === "central" ? 1.1 : 1;
      mesh.userData.displaySite = site; // Original Python coordinates for inspection.
      mesh.userData.basePosition = mesh.position.clone();
      this.siteGroup.add(mesh);
      this.siteMeshes.push(mesh);
    }
    this.displaySiteCount = sites.length;
    if (view.mode === "unit") {
      this.applySiteColors();
      this.selectionHalo.scale.setScalar(radius * 1.28);
    } else {
      this.applyAtomScale();
    }

    if (view.mode === "unit") {
      const edgePoints = [];
      for (const [start, end] of boundary.edges) {
        edgePoints.push(
          new THREE.Vector3(...boundary.vertices[start]),
          new THREE.Vector3(...boundary.vertices[end])
        );
      }
      const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
      const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x61758a });
      this.resources.push(edgeGeometry, edgeMaterial);
      this.boundaryGroup = new THREE.Group();
      this.boundaryGroup.add(new THREE.LineSegments(edgeGeometry, edgeMaterial));
      this.structureGroup.add(this.boundaryGroup);

      const contact = view.contact_diagonals;
      if (contact?.supported) {
        this.contactDiagonalLines = this.addGuideSegments(
          contact.segments, this.paletteColor("--viz-guide"), 0.4
        );
      }
      if (data.structure === "HCP") {
        // Only a presentation rotation: the Python prism's z/c axis is y-up.
        this.structureGroup.rotation.x = -Math.PI / 2;
      }
    } else if (view.mode === "coordination") {
      this.coordinationGuideLines = this.addGuideSegments(
        view.guide_segments, this.paletteColor("--viz-guide"), 0.66
      );
      this.addCoordinationPolyhedron(sites.slice(1), view.polyhedron);
      if (data.structure === "HCP") this.structureGroup.rotation.x = -Math.PI / 2;
    } else {
      this.stackingAxis = new THREE.Vector3(...view.axis).normalize();
      this.stackingNaturalSpacing = view.natural_spacing;
      this.applyStackingOffsets();
      // Align the API's stacking normal with the screen's vertical direction.
      // The primitive crystallographic axes are children of this same group.
      this.structureGroup.quaternion.setFromUnitVectors(
        this.stackingAxis, new THREE.Vector3(0, 1, 0)
      );
    }
    this.updateGuideVisibility();
    // Full Unit Cell spheres may extend beyond the cell walls when clipping is
    // off. Fit their unchanged physical geometry once, not on each toggle.
    this.frameEducationalView(previousOffset, previousDistance, previousFitDistance,
      preserveView, this.siteGroup);

    if (view.mode === "unit") {
      // Three.js clipping planes are world-space. Transform the inward Python
      // planes by precisely the group's centering/HCP presentation matrix.
      const localPlanes = view.clipping_planes.map((plane) =>
        new THREE.Plane(new THREE.Vector3(...plane.normal), plane.constant));
      this.unitClippingPlanes = localPlanes.map((plane) =>
        plane.clone().applyMatrix4(this.structureGroup.matrixWorld));
      for (const material of this.siteMaterials.all) {
        material.clippingPlanes = this.unitClippingPlanes;
        material.needsUpdate = true;
      }
      this.selectionHalo.material.clippingPlanes = this.unitClippingPlanes;
      this.selectionHalo.material.needsUpdate = true;
      this.selectedMaterial.clippingPlanes = this.unitClippingPlanes;
      this.selectedMaterial.needsUpdate = true;
      this.addUnitCellCaps(sphereGeometry, localPlanes, radius);
    }
    this.updateUnitClippingVisibility();

    const latticeVectors = vectors.map((row) => new THREE.Vector3(...row));
    // Scientific HCP supercells remain primitive; do not use display tiling
    // vectors in the axes guide.
    this.addAxes(latticeVectors, view.mode === "stacking" ? 2.5 : 1);
    this.container.dataset.generatedBasisPositionCount = String(scientificSites.length);
    this.container.dataset.displaySiteCount = String(this.displaySiteCount);
    this.container.dataset.visualizationMode = view.mode;
    this.structureGroup.add(this.selectionHalo);
  }

  applyStackingOffsets() {
    if (this.viewMode !== "stacking" || !this.stackingAxis) return;
    const extraSpacing = (this.layerSeparation / 100 - 1) *
      this.stackingNaturalSpacing;
    for (const mesh of this.siteMeshes) {
      mesh.position.copy(mesh.userData.basePosition).addScaledVector(
        this.stackingAxis, mesh.userData.displaySite.layer_index * extraSpacing
      );
    }
    if (this.selectedMesh) this.selectionHalo.position.copy(this.selectedMesh.position);
  }

  setLayerSeparation(percent) {
    if (!Number.isFinite(percent) || percent < 100 || percent > 250) {
      throw new Error("Layer Separation must be between 100% and 250%.");
    }
    this.layerSeparation = percent;
    if (this.viewMode !== "stacking") return;
    const previousOffset = this.camera.position.clone().sub(this.controls.target);
    const previousDistance = previousOffset.length();
    const previousFitDistance = this.fitDistance;
    this.applyStackingOffsets();
    this.frameEducationalView(previousOffset, previousDistance, previousFitDistance,
      true, this.siteGroup);
  }

  frameEducationalView(previousOffset, previousDistance, previousFitDistance,
    preserveView, boundsObject = this.structureGroup) {
    // Re-centre presentation geometry; raw API site coordinates stay untouched.
    this.structureGroup.position.set(0, 0, 0);
    this.structureGroup.updateMatrixWorld(true);
    const center = new THREE.Box3().setFromObject(boundsObject)
      .getCenter(new THREE.Vector3());
    this.structureGroup.position.copy(center).multiplyScalar(-1);
    this.structureGroup.updateMatrixWorld(true);
    const sphere = new THREE.Box3().setFromObject(boundsObject)
      .getBoundingSphere(new THREE.Sphere());
    this.boundsRadius = Math.max(sphere.radius, 1);
    this.viewCenter.copy(sphere.center);
    this.controls.target.copy(sphere.center);
    this.fitDistance = this.requiredDistance();
    const viewDirection = preserveView && previousDistance > 0
      ? previousOffset.normalize() : this.defaultViewDirection;
    const scaledDistance = previousFitDistance > 0
      ? previousDistance * Math.sqrt(this.fitDistance / previousFitDistance)
      : this.fitDistance;
    const cameraDistance = preserveView
      ? Math.min(Math.max(scaledDistance, this.fitDistance * 0.85), this.fitDistance * 1.5)
      : this.fitDistance;
    this.camera.position.copy(sphere.center).addScaledVector(
      viewDirection, cameraDistance
    );
    this.camera.far = Math.max(2000, this.boundsRadius * 100);
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  addAxes(latticeVectors, size) {
    this.axesGroup = new THREE.Group();
    const colors = [0xe59b9b, 0x94c69e, 0x91b9ed];
    const labels = ["a₁", "a₂", "a₃"];
    const up = new THREE.Vector3(0, 1, 0);

    latticeVectors.forEach((vector, index) => {
      // Length is visual only. Directions always come from the API's primitive
      // a₁/a₂/a₃ vectors, never from HCP prism-tiling or stacking vectors.
      const length = vector.length() * 0.82 * Math.min(size, 2.5);
      const direction = vector.clone().normalize();
      const headLength = length * 0.17;
      const color = colors[index];
      const lineGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(), direction.clone().multiplyScalar(length - headLength),
      ]);
      const lineMaterial = new THREE.LineBasicMaterial({
        color, depthTest: false, depthWrite: false,
      });
      const line = new THREE.Line(lineGeometry, lineMaterial);
      line.renderOrder = 10;
      this.axesGroup.add(line);

      const coneGeometry = new THREE.ConeGeometry(length * 0.055, headLength, 12);
      const coneMaterial = new THREE.MeshBasicMaterial({
        color, depthTest: false, depthWrite: false,
      });
      const cone = new THREE.Mesh(coneGeometry, coneMaterial);
      cone.position.copy(direction).multiplyScalar(length - headLength / 2);
      cone.quaternion.setFromUnitVectors(up, direction);
      cone.renderOrder = 10;
      this.axesGroup.add(cone);

      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 64;
      const context = canvas.getContext("2d");
      context.font = "600 44px -apple-system, BlinkMacSystemFont, Arial, sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
      context.fillText(labels[index], 64, 32);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const labelMaterial = new THREE.SpriteMaterial({
        map: texture, transparent: true, depthTest: false, depthWrite: false,
      });
      const label = new THREE.Sprite(labelMaterial);
      label.position.copy(direction).multiplyScalar(length * 1.14);
      label.scale.set(length * 0.42, length * 0.21, 1);
      label.renderOrder = 11;
      this.axesGroup.add(label);
      this.resources.push(
        lineGeometry, lineMaterial, coneGeometry, coneMaterial, texture, labelMaterial
      );
    });

    this.axesGroup.visible = this.showAxes;
    this.structureGroup.add(this.axesGroup);
  }

  requiredDistance() {
    const vertical = THREE.MathUtils.degToRad(this.camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * this.camera.aspect);
    return this.boundsRadius / Math.sin(Math.min(vertical, horizontal) / 2) * 1.2;
  }

  resize() {
    const width = Math.max(1, Math.floor(this.container.clientWidth));
    const height = Math.max(1, Math.floor(this.container.clientHeight));
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    if (width === this.lastCanvasSize.width && height === this.lastCanvasSize.height &&
        pixelRatio === this.lastCanvasSize.pixelRatio) return;
    this.lastCanvasSize = { width, height, pixelRatio };
    this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    if (this.boundsRadius > 0) {
      const nextFitDistance = this.requiredDistance();
      // Keep the same orbit direction, pan target and zoom relative to the
      // fitted view. A narrower fullscreen aspect then gains just enough
      // camera distance to avoid cutting off the crystal; exit reverses it.
      const offset = this.camera.position.clone().sub(this.controls.target);
      offset.multiplyScalar(nextFitDistance / this.fitDistance);
      this.camera.position.copy(this.controls.target).add(offset);
      this.fitDistance = nextFitDistance;
      this.controls.update();
    }
  }

  animate() {
    this.animationFrame = requestAnimationFrame(this.animate);
    this.controls.update();
    try {
      this.renderer.render(this.scene, this.camera);
      if (!this.firstFrameRendered && this.hasRenderableStructure &&
          this.renderer.domElement.width > 1 && this.renderer.domElement.height > 1) {
        this.firstFrameRendered = true;
        this.resolveFirstFrame();
      }
    } catch (error) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = 0;
      if (!this.firstFrameRendered) this.rejectFirstFrame(error);
      else console.error("The 3D viewer stopped rendering:", error);
    }
  }

  dispose() {
    cancelAnimationFrame(this.animationFrame);
    this.resizeObserver.disconnect();
    this.controls.dispose();
    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointerdown", this.handlePointerDown);
    this.pointerDocument.removeEventListener("pointermove", this.handlePointerMove);
    this.pointerDocument.removeEventListener("pointerup", this.handlePointerUp);
    this.pointerDocument.removeEventListener("pointercancel", this.cancelPointer);
    this.activePointers.clear();
    this.pointerStart = null;
    this.clearStructure();
    this.selectionHalo.geometry.dispose();
    this.selectionHalo.material.dispose();
    this.selectedMaterial.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

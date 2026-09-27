"use strict";

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const viewers = [];
const validPoint = (point) => Array.isArray(point) && point.length === 3 &&
  point.every(Number.isFinite);

function validateModel(data) {
  const sites = data.display?.sites;
  const segments = data.display?.cell_grid?.segments;
  if (!Number.isFinite(data.parameters?.a) || data.parameters.a <= 0 ||
      !Array.isArray(sites) || sites.length === 0 ||
      !sites.every((site) => validPoint(site.cartesian)) ||
      !Array.isArray(segments) || segments.length === 0 ||
      !segments.every((segment) => validPoint(segment.start) && validPoint(segment.end))) {
    throw new Error("The API returned incomplete comparison geometry.");
  }
  return { sites, segments };
}

class ComparisonViewer {
  constructor(stage) {
    this.stage = stage;
    this.resources = [];
    this.abortController = new AbortController();
    this.hasModel = false;
    this.disposed = false;
    this.fitDistance = 0;
    this.render = this.render.bind(this);
  }

  async load() {
    const response = await fetch(this.stage.dataset.modelUrl, {
      signal: this.abortController.signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("The structure request failed.");
    const data = await response.json();
    if (this.disposed) return;
    const { sites, segments } = validateModel(data);

    const palette = getComputedStyle(this.stage);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(palette.getPropertyValue("--bg-stage").trim());
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 2000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    const canvas = this.renderer.domElement;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", this.stage.getAttribute("aria-label"));
    this.stage.appendChild(canvas);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enablePan = false;
    this.controls.enableDamping = false;
    this.controls.touches.ONE = THREE.TOUCH.ROTATE;
    // With pan disabled, the standard two-finger gesture performs zoom only.
    this.controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    this.controls.addEventListener("change", this.render);

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.85));
    const light = new THREE.DirectionalLight(0xffffff, 2.1);
    light.position.set(8, 12, 10);
    this.scene.add(light);

    const group = new THREE.Group();
    // A deliberately modest display radius, not a physical touching radius.
    const sphereGeometry = new THREE.SphereGeometry(data.parameters.a * 0.12, 24, 16);
    const sphereMaterial = new THREE.MeshStandardMaterial({
      color: new THREE.Color(palette.getPropertyValue("--viz-material").trim()),
      roughness: 0.48, metalness: 0.06,
    });
    this.resources.push(sphereGeometry, sphereMaterial);
    for (const site of sites) {
      const mesh = new THREE.Mesh(sphereGeometry, sphereMaterial);
      mesh.position.set(...site.cartesian);
      group.add(mesh);
    }

    // Both lattice sites and outline segments come directly from Python.
    const edgePoints = segments.flatMap((segment) => [
      new THREE.Vector3(...segment.start), new THREE.Vector3(...segment.end),
    ]);
    const edgeGeometry = new THREE.BufferGeometry().setFromPoints(edgePoints);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x61758a });
    this.resources.push(edgeGeometry, edgeMaterial);
    group.add(new THREE.LineSegments(edgeGeometry, edgeMaterial));
    if (data.structure === "HCP") {
      // Presentation only: orient the API's z/c direction upright on screen.
      group.rotation.x = -Math.PI / 2;
    }
    this.scene.add(group);

    const bounds = new THREE.Box3().setFromObject(group);
    group.position.sub(bounds.getCenter(new THREE.Vector3()));
    this.boundsRadius = bounds.getBoundingSphere(new THREE.Sphere()).radius;
    // Slightly asymmetric oblique view avoids aligning opposite cube corners
    // with body/face centres in the initial comparison image.
    this.camera.position.set(1.4, 0.9, 2.2).normalize();
    this.hasModel = true;
    this.resize();
    this.controls.update();
    this.render();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.stage);
    this.stage.dataset.siteCount = String(sites.length);
    this.stage.dataset.segmentCount = String(segments.length);
    this.stage.classList.add("is-ready");
    this.stage.querySelector(".compare-model-message").hidden = true;
  }

  requiredDistance() {
    const vertical = THREE.MathUtils.degToRad(this.camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * this.camera.aspect);
    return this.boundsRadius / Math.sin(Math.min(vertical, horizontal) / 2) * 1.12;
  }

  resize() {
    if (this.disposed || !this.hasModel) return;
    const width = Math.max(1, Math.floor(this.stage.clientWidth));
    const height = Math.max(1, Math.floor(this.stage.clientHeight));
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    const nextDistance = this.requiredDistance();
    const offset = this.camera.position.clone().sub(this.controls.target);
    if (this.fitDistance > 0) offset.multiplyScalar(nextDistance / this.fitDistance);
    else offset.setLength(nextDistance);
    this.camera.position.copy(this.controls.target).add(offset);
    this.fitDistance = nextDistance;
    this.camera.near = Math.max(this.boundsRadius / 100, 0.001);
    this.camera.far = this.boundsRadius * 100;
    this.camera.updateProjectionMatrix();
    this.controls.minDistance = nextDistance * 0.35;
    this.controls.maxDistance = nextDistance * 5;
    this.controls.update();
    this.render();
  }

  render() {
    if (this.hasModel && !this.disposed) this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.abortController.abort();
    this.resizeObserver?.disconnect();
    this.controls?.removeEventListener("change", this.render);
    this.controls?.dispose();
    for (const resource of this.resources) resource.dispose();
    this.renderer?.dispose();
    this.renderer?.domElement.remove();
  }
}

for (const stage of document.querySelectorAll(".compare-stage[data-structure]")) {
  const viewer = new ComparisonViewer(stage);
  viewers.push(viewer);
  viewer.load().catch((error) => {
    if (error.name === "AbortError" || viewer.disposed) return;
    viewer.dispose();
    stage.classList.add("is-error");
    const message = stage.querySelector(".compare-model-message");
    message.textContent = "Model unavailable";
    message.hidden = false;
  });
}

window.addEventListener("pagehide", (event) => {
  // A bfcache restoration keeps the existing scenes and controls intact.
  if (!event.persisted) viewers.forEach((viewer) => viewer.dispose());
});

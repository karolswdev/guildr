import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RGBELoader } from "three/examples/jsm/loaders/RGBELoader.js";
import { AtomNode } from "./atoms/AtomNode.js";
import { EdgeMesh } from "./atoms/EdgeMesh.js";
import type { AssetManager } from "./assets/AssetManager.js";
import { commandsForRunEvent } from "./flows/FlowDirector.js";
import type { FlowCommand } from "./flows/FlowTypes.js";
import { layoutWorkflowAtoms, type AtomLayout, type EdgeKind, type LoopGroupLayout } from "./layout.js";
import type { EngineSnapshot, RunEvent, WorkflowStep } from "./types.js";

type SceneManagerOptions = {
  canvas: HTMLCanvasElement;
  renderer: THREE.WebGLRenderer;
  workflow: WorkflowStep[];
  assets: AssetManager;
  onSelectAtom: (atomId: string) => void;
};

export type SpatialViewLevel = "global" | "cluster" | "surface";

export class SceneManager {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(42, 1, 0.1, 120);
  private readonly atomNodes = new Map<string, AtomNode>();
  private readonly atomMotion = new Map<string, { base: THREE.Vector3; phase: number; amp: number; drift: THREE.Vector3 }>();
  private readonly edgeMeshes: EdgeMesh[] = [];
  private readonly edgesById = new Map<string, EdgeMesh>();
  private readonly loopMeshes: THREE.Object3D[] = [];
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointer = new THREE.Vector2();
  private readonly textureLoader = new THREE.TextureLoader();
  private readonly gltfLoader = new GLTFLoader();
  private readonly layout: AtomLayout;
  private readonly pulseSprites: Array<{ sprite: THREE.Sprite; edge: EdgeMesh; offset: number; kind: EdgeKind }> = [];
  private readonly glowSprites: THREE.Sprite[] = [];
  private readonly spaceProps: Array<{ object: THREE.Object3D; base: THREE.Vector3; spin: THREE.Vector3; bobPhase: number }> = [];
  private readonly loadedTextures: THREE.Texture[] = [];
  private readonly canvas: HTMLCanvasElement;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly onSelectAtom: (atomId: string) => void;
  private viewportAspect = 1;
  private selectedAtomId = "";
  private orbitStart: { x: number; y: number; theta: number; phi: number } | null = null;
  private targetPanStart: { x: number; y: number; targetX: number; targetY: number; targetZ: number } | null = null;
  private tapStart: { x: number; y: number; time: number } | null = null;
  private lastEmptyTap: { x: number; y: number; time: number } | null = null;
  private pinchStart: { distance: number; radius: number } | null = null;
  private activePointers = new Map<number, PointerEvent>();
  private orbitTarget = new THREE.Vector3();
  private orbitTheta = -0.6;
  private orbitPhi = 0.98;
  private orbitRadius = 10;
  private polyPizzaPropsLoaded = false;
  private viewLevel: SpatialViewLevel = "global";

  constructor(options: SceneManagerOptions) {
    this.canvas = options.canvas;
    this.renderer = options.renderer;
    this.onSelectAtom = options.onSelectAtom;
    this.layout = layoutWorkflowAtoms(options.workflow);
    this.scene.background = new THREE.Color(0x0d0f14);

    this.scene.add(new THREE.AmbientLight(0xe8eaf0, 0.62));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
    keyLight.position.set(4, 8, 5);
    this.scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x7a5cff, 0.25);
    rimLight.position.set(-5, 4, -6);
    this.scene.add(rimLight);

    this.buildEnvironment(options.assets);
    this.buildLoopObjects(options.assets);
    this.buildWorkflow(options.workflow, options.assets);
    this.bindInput();
    this.fitAll();
  }

  resize(width: number, height: number): void {
    this.viewportAspect = Math.max(0.1, width / Math.max(1, height));
    this.camera.aspect = this.viewportAspect;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.fitAll();
  }

  applySnapshot(snapshot: EngineSnapshot): void {
    for (const [id, atom] of this.atomNodes.entries()) {
      const status = snapshot.atoms[id];
      if (status) {
        atom.setState(status);
      }
      atom.setTelemetry(snapshot.cost.byAtom[id] ?? null, snapshot.loops.byAtom[id] ?? null);
    }
  }

  applyRunEvent(event: RunEvent, snapshot: EngineSnapshot): void {
    this.applyFlowCommands(commandsForRunEvent(event, this.layout, snapshot));
  }

  applyDeferredAssets(assets: AssetManager): void {
    const lensflareUrl = assets.get("memPalace.lensflare")?.objectUrl;
    if (lensflareUrl) {
      const texture = this.loadTexture(lensflareUrl, true);
      for (const node of this.layout.nodes.filter((item) => item.lane === "context" || item.id.includes("memory"))) {
        const sprite = makeGlowSprite(texture, 0x41c7c7, 0.32, 2.8);
        sprite.position.set(node.x, 0.18, node.z);
        this.glowSprites.push(sprite);
        this.scene.add(sprite);
      }
    }

    const sparkUrl = assets.get("particles.spark")?.objectUrl;
    if (sparkUrl) {
      const texture = this.loadTexture(sparkUrl, true);
      for (const item of this.pulseSprites) {
        const spark = makePulseSprite(texture, 0xe8eaf0);
        spark.position.copy(item.sprite.position);
        spark.scale.set(0.24, 0.24, 0.24);
        this.glowSprites.push(spark);
        this.scene.add(spark);
      }
    }

    const hdriUrl = assets.get("environment.hdriSky")?.objectUrl;
    if (hdriUrl) {
      new RGBELoader().load(hdriUrl, (texture) => {
        texture.mapping = THREE.EquirectangularReflectionMapping;
        this.loadedTextures.push(texture);
        this.scene.environment = texture;
      });
    }
    this.buildPolyPizzaProps(assets);
  }

  render(timeMs: number): void {
    for (const atom of this.atomNodes.values()) {
      atom.animate(timeMs);
    }
    this.animateAtomDrift(timeMs);
    this.animateSpaceProps(timeMs);
    this.animatePulses(timeMs);
    this.animateGlows(timeMs);
    this.renderer.render(this.scene, this.camera);
  }

  fitAll(): void {
    const center = this.layout.bounds.center;
    this.orbitTarget.set(center.x, center.y, center.z);
    this.orbitRadius = Math.max(6, this.layout.bounds.radius * 1.75);
    this.orbitTheta = -0.74;
    this.orbitPhi = 0.95;
    this.updateCameraFromOrbit();
  }

  focusAtomInView(atomId: string, verticalBias = 0.28): void {
    const atom = this.atomNodes.get(atomId);
    if (!atom) {
      return;
    }
    this.orbitTarget.copy(atom.group.position);
    this.orbitTarget.y += (0.5 - verticalBias) * 1.2;
    this.orbitRadius = Math.max(4.8, this.layout.bounds.radius * 0.9);
    this.updateCameraFromOrbit();
  }

  restoreView(): void {
    this.setViewLevel(this.viewLevel, this.selectedAtomId);
  }

  setViewLevel(level: SpatialViewLevel, targetAtomId = ""): void {
    this.viewLevel = level;
    if (level === "global") {
      this.fitAll();
      return;
    }
    if (level === "surface") {
      this.focusAtomInView(targetAtomId || this.selectedAtomId || this.layout.nodes[0]?.id || "", 0.42);
      return;
    }
    this.focusLoopForAtom(targetAtomId || this.selectedAtomId || this.layout.nodes[0]?.id || "");
  }

  dispose(): void {
    this.canvas.removeEventListener("pointerdown", this.onPointerDown);
    this.canvas.removeEventListener("pointermove", this.onPointerMove);
    this.canvas.removeEventListener("pointerup", this.onPointerUp);
    this.canvas.removeEventListener("pointercancel", this.onPointerUp);
    this.canvas.removeEventListener("wheel", this.onWheel);
    for (const atom of this.atomNodes.values()) {
      atom.dispose();
    }
    for (const edge of this.edgeMeshes) {
      edge.dispose();
    }
    for (const mesh of this.loopMeshes) {
      disposeObject(mesh);
    }
    for (const pulse of this.pulseSprites) {
      pulse.sprite.material.dispose();
    }
    for (const glow of this.glowSprites) {
      glow.material.dispose();
    }
    for (const prop of this.spaceProps) {
      disposeObject(prop.object);
    }
    for (const texture of this.loadedTextures) {
      texture.dispose();
    }
  }

  private buildEnvironment(assets: AssetManager): void {
    void assets;
    const count = 180;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const radius = this.layout.bounds.radius * (0.9 + seeded(index, 1) * 1.2);
      const theta = seeded(index, 2) * Math.PI * 2;
      const phi = Math.acos(seeded(index, 3) * 2 - 1);
      positions[index * 3] = this.layout.bounds.center.x + radius * Math.sin(phi) * Math.cos(theta);
      positions[index * 3 + 1] = this.layout.bounds.center.y + radius * Math.cos(phi) * 0.72;
      positions[index * 3 + 2] = this.layout.bounds.center.z + radius * Math.sin(phi) * Math.sin(theta);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: 0x7d8499,
      size: 0.018,
      transparent: true,
      opacity: 0.45,
      depthWrite: false,
    });
    const stars = new THREE.Points(geometry, material);
    this.loopMeshes.push(stars);
    this.scene.add(stars);
  }

  private buildLoopObjects(assets: AssetManager): void {
    const haloUrl = assets.get("memPalace.radialAlpha")?.objectUrl;
    const haloTexture = haloUrl ? this.loadTexture(haloUrl, true) : null;
    for (const loop of this.layout.loops) {
      if (haloTexture) {
        const halo = makeGlowSprite(haloTexture, laneColor(loop.lane), 0.18, loop.radius * 3.3);
        halo.position.set(loop.center.x, loop.center.y, loop.center.z);
        this.loopMeshes.push(halo);
        this.scene.add(halo);
      }

      const label = makeLoopLabel(loop);
      this.loopMeshes.push(label);
      this.scene.add(label);
    }
  }

  private buildWorkflow(workflow: WorkflowStep[], assets: AssetManager): void {
    const normalUrl = assets.get("atom.flatNormal")?.objectUrl;
    const grainUrl = assets.get("atom.grain")?.objectUrl;
    const pulseUrl = assets.get("particles.disc")?.objectUrl;
    const glowUrl = assets.get("memPalace.radialAlpha")?.objectUrl;
    const textures = {
      normal: normalUrl ? this.loadTexture(normalUrl) : undefined,
      grain: grainUrl ? this.loadTexture(grainUrl, true) : undefined,
      pulse: pulseUrl ? this.loadTexture(pulseUrl, true) : undefined,
      glow: glowUrl ? this.loadTexture(glowUrl, true) : undefined,
    };

    for (const node of this.layout.nodes) {
      const step = workflow.find((item) => item.id === node.id);
      if (!step) {
        continue;
      }
      const atom = new AtomNode(step, textures);
      atom.group.position.set(node.x, node.y, node.z);
      this.atomMotion.set(step.id, {
        base: atom.group.position.clone(),
        phase: node.bobPhase,
        amp: node.bobAmp,
        drift: new THREE.Vector3(node.driftAxis.x, node.driftAxis.y, node.driftAxis.z),
      });
      this.atomNodes.set(step.id, atom);
      this.scene.add(atom.group);
    }

    for (const edge of this.layout.edges) {
      const from = this.atomNodes.get(edge.from)?.group.position;
      const to = this.atomNodes.get(edge.to)?.group.position;
      if (!from || !to) {
        continue;
      }
      const edgeMesh = new EdgeMesh(from, to, edge.kind, edge.id);
      this.edgeMeshes.push(edgeMesh);
      this.edgesById.set(edge.id, edgeMesh);
      this.scene.add(edgeMesh.mesh);
      if (textures.pulse) {
        this.addPulseSprite(edgeMesh, edge.kind, textures.pulse, this.edgeMeshes.length * 0.17);
      }
    }

    if (textures.glow) {
      this.buildMemoryGlows(textures.glow);
    }
  }

  private bindInput(): void {
    this.canvas.addEventListener("pointerdown", this.onPointerDown);
    this.canvas.addEventListener("pointermove", this.onPointerMove);
    this.canvas.addEventListener("pointerup", this.onPointerUp);
    this.canvas.addEventListener("pointercancel", this.onPointerUp);
    this.canvas.addEventListener("wheel", this.onWheel, { passive: false });
  }

  private applyFlowCommands(commands: FlowCommand[]): void {
    for (const command of commands) {
      if (command.type === "path_mode") {
        this.edgesById.get(command.pathId)?.setMode(command.mode, command.kind);
      } else if (command.type === "pulse") {
        this.edgesById.get(command.pathId)?.setMode(command.mode ?? "active", command.kind);
      } else if (command.type === "dust") {
        this.edgesById.get(command.pathId)?.setMode("selected", "cost");
      } else if (command.type === "repair_backflow") {
        this.edgesById.get(command.pathId)?.setMode("reversing", "repair");
      } else if (command.type === "replay") {
        for (const edge of this.edgeMeshes) {
          edge.setMode(command.mode === "resume" ? "queued" : "reversing", "replay");
        }
      }
    }
  }

  private loadTexture(url: string, srgb = false): THREE.Texture {
    const texture = this.textureLoader.load(url);
    if (srgb) {
      texture.colorSpace = THREE.SRGBColorSpace;
    }
    this.loadedTextures.push(texture);
    return texture;
  }

  private addPulseSprite(edge: EdgeMesh, kind: EdgeKind, texture: THREE.Texture, offset: number): void {
    const sprite = makePulseSprite(texture, kind === "gate" ? 0xe09b2a : kind === "loop" ? 0x41c7c7 : 0xe8eaf0);
    sprite.position.copy(edge.pointAt(0));
    this.pulseSprites.push({ sprite, edge, offset, kind });
    this.scene.add(sprite);
  }

  private buildMemoryGlows(texture: THREE.Texture): void {
    for (const node of this.layout.nodes) {
      if (node.lane !== "context" && node.id !== "persona_forum") {
        continue;
      }
      const sprite = makeGlowSprite(texture, 0x41c7c7, 0.22, node.id === "memory_refresh" ? 2.4 : 1.7);
      sprite.position.set(node.x, 0.1, node.z);
      this.glowSprites.push(sprite);
      this.scene.add(sprite);
    }
  }

  private buildPolyPizzaProps(assets: AssetManager): void {
    if (this.polyPizzaPropsLoaded) {
      return;
    }
    this.polyPizzaPropsLoaded = true;
    const center = new THREE.Vector3(this.layout.bounds.center.x, this.layout.bounds.center.y, this.layout.bounds.center.z);
    const props = [
      { id: "polyPizza.planetA", offset: new THREE.Vector3(-2.8, 2.6, -3.4), scale: 0.9, spin: new THREE.Vector3(0.00012, 0.00032, 0.00004) },
      { id: "polyPizza.planetB", offset: new THREE.Vector3(3.7, 2.3, -3.0), scale: 0.82, spin: new THREE.Vector3(0.00008, -0.00026, 0.00006) },
      { id: "polyPizza.pixelPlanet", offset: new THREE.Vector3(-4.7, 0.55, 1.7), scale: 0.72, spin: new THREE.Vector3(-0.00005, 0.0003, 0.0001) },
    ];
    props.forEach((prop, index) => {
      const asset = assets.get(prop.id);
      if (!asset?.objectUrl || asset.status !== "loaded") {
        return;
      }
      this.gltfLoader.load(asset.objectUrl, (gltf) => {
        const object = gltf.scene;
        object.name = `poly-pizza:${prop.id}`;
        normalizeModel(object, prop.scale);
        const wrapper = new THREE.Group();
        wrapper.name = `space-prop:${prop.id}`;
        wrapper.add(object);
        const base = center.clone().add(prop.offset);
        wrapper.position.copy(base);
        wrapper.rotation.set(index * 0.3, index * 0.6, index * 0.17);
        object.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.castShadow = false;
            child.receiveShadow = false;
          }
        });
        this.spaceProps.push({ object: wrapper, base, spin: prop.spin, bobPhase: index * 1.7 + 0.4 });
        this.scene.add(wrapper);
      });
    });
  }

  private animatePulses(timeMs: number): void {
    for (const pulse of this.pulseSprites) {
      const t = (timeMs * 0.00028 + pulse.offset) % 1;
      pulse.sprite.position.copy(pulse.edge.pointAt(t));
      const scale = (pulse.kind === "gate" ? 0.16 : 0.1) + Math.sin(t * Math.PI) * 0.07;
      pulse.sprite.scale.set(scale, scale, scale);
    }
  }

  private animateAtomDrift(timeMs: number): void {
    for (const [id, atom] of this.atomNodes.entries()) {
      const motion = this.atomMotion.get(id);
      if (!motion) {
        continue;
      }
      const bob = Math.sin(timeMs * 0.0008 + motion.phase) * motion.amp;
      const drift = Math.sin(timeMs * 0.00038 + motion.phase * 0.7) * 0.045;
      atom.group.position.copy(motion.base).addScaledVector(motion.drift, drift);
      atom.group.position.y += bob;
    }
  }

  private animateSpaceProps(timeMs: number): void {
    for (const prop of this.spaceProps) {
      prop.object.position.copy(prop.base);
      prop.object.position.y += Math.sin(timeMs * 0.00042 + prop.bobPhase) * 0.16;
      prop.object.rotation.x += prop.spin.x * 16;
      prop.object.rotation.y += prop.spin.y * 16;
      prop.object.rotation.z += prop.spin.z * 16;
    }
  }

  private animateGlows(timeMs: number): void {
    for (let index = 0; index < this.glowSprites.length; index += 1) {
      const sprite = this.glowSprites[index];
      const pulse = 1 + Math.sin(timeMs * 0.0012 + index) * 0.08;
      sprite.scale.setScalar((sprite.userData.baseScale as number || 1) * pulse);
    }
  }

  private onPointerDown = (event: PointerEvent): void => {
    this.canvas.setPointerCapture(event.pointerId);
    this.activePointers.set(event.pointerId, event);
    this.tapStart = { x: event.clientX, y: event.clientY, time: performance.now() };
    if (this.activePointers.size === 2) {
      const [first, second] = [...this.activePointers.values()];
      this.pinchStart = { distance: pointerDistance(first, second), radius: this.orbitRadius };
      this.orbitStart = null;
      return;
    }
    this.orbitStart = {
      x: event.clientX,
      y: event.clientY,
      theta: this.orbitTheta,
      phi: this.orbitPhi,
    };
  };

  private onPointerMove = (event: PointerEvent): void => {
    if (!this.activePointers.has(event.pointerId)) {
      return;
    }
    this.activePointers.set(event.pointerId, event);
    if (this.activePointers.size === 2 && this.pinchStart) {
      const [first, second] = [...this.activePointers.values()];
      const distance = pointerDistance(first, second);
      this.orbitRadius = clamp(this.pinchStart.radius * (this.pinchStart.distance / Math.max(1, distance)), 4, 22);
      this.updateCameraFromOrbit();
      return;
    }
    if (!this.orbitStart) {
      return;
    }
    this.orbitTheta = this.orbitStart.theta - (event.clientX - this.orbitStart.x) * 0.006;
    this.orbitPhi = clamp(this.orbitStart.phi + (event.clientY - this.orbitStart.y) * 0.004, 0.38, 1.28);
    this.updateCameraFromOrbit();
  };

  private onPointerUp = (event: PointerEvent): void => {
    this.activePointers.delete(event.pointerId);
    this.pinchStart = null;
    if (this.tapStart) {
      const distance = Math.hypot(event.clientX - this.tapStart.x, event.clientY - this.tapStart.y);
      const elapsed = performance.now() - this.tapStart.time;
      if (distance < 8 && elapsed < 240) {
        this.handleTap(event);
      }
    }
    this.tapStart = null;
    this.orbitStart = null;
    this.targetPanStart = null;
  };

  private onWheel = (event: WheelEvent): void => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 1.1 : 0.9;
    this.orbitRadius = clamp(this.orbitRadius * delta, 4, 22);
    this.updateCameraFromOrbit();
  };

  private handleTap(event: PointerEvent): void {
    const hit = this.pickAtom(event.clientX, event.clientY);
    if (hit) {
      this.selectAtom(hit);
      this.onSelectAtom(hit);
      return;
    }
    const now = performance.now();
    if (this.lastEmptyTap && now - this.lastEmptyTap.time < 300 && Math.hypot(event.clientX - this.lastEmptyTap.x, event.clientY - this.lastEmptyTap.y) < 8) {
      this.fitAll();
      this.lastEmptyTap = null;
      return;
    }
    this.lastEmptyTap = { x: event.clientX, y: event.clientY, time: now };
  }

  private selectAtom(atomId: string): void {
    if (this.selectedAtomId && this.selectedAtomId !== atomId) {
      this.atomNodes.get(this.selectedAtomId)?.setSelected(false);
    }
    this.selectedAtomId = atomId;
    this.atomNodes.get(atomId)?.setSelected(true);
  }

  private focusLoopForAtom(atomId: string): void {
    const node = this.layout.nodes.find((item) => item.id === atomId);
    const loop = this.layout.loops.find((item) => item.id === node?.loopId) ?? this.layout.loops[0];
    if (!loop) {
      this.fitAll();
      return;
    }
    this.orbitTarget.set(loop.center.x, loop.center.y, loop.center.z);
    this.orbitRadius = Math.max(4.6, loop.radius * 2.35);
    this.orbitTheta = -0.66;
    this.orbitPhi = 0.9;
    this.updateCameraFromOrbit();
  }

  private pickAtom(clientX: number, clientY: number): string {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects([...this.atomNodes.values()].map((atom) => atom.mesh), false);
    return typeof hits[0]?.object.userData.atomId === "string" ? hits[0].object.userData.atomId : "";
  }

  private updateCameraFromOrbit(): void {
    const sinPhi = Math.sin(this.orbitPhi);
    this.camera.position.set(
      this.orbitTarget.x + this.orbitRadius * sinPhi * Math.sin(this.orbitTheta),
      this.orbitTarget.y + this.orbitRadius * Math.cos(this.orbitPhi),
      this.orbitTarget.z + this.orbitRadius * sinPhi * Math.cos(this.orbitTheta),
    );
    this.camera.lookAt(this.orbitTarget);
    this.camera.updateProjectionMatrix();
  }
}

function pointerDistance(first: PointerEvent, second: PointerEvent): number {
  return Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function laneColor(lane: string): number {
  const colors: Record<string, number> = {
    context: 0x41c7c7,
    plan: 0x4d6fff,
    build: 0xe8eaf0,
    verify: 0x1a8c5a,
    ship: 0x28b8a8,
    gate: 0xe09b2a,
    empty: 0x1a1e2a,
  };
  return colors[lane] ?? colors.empty;
}

function makePulseSprite(texture: THREE.Texture, color: number): THREE.Sprite {
  const material = new THREE.SpriteMaterial({
    map: texture,
    color,
    transparent: true,
    opacity: 0.88,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(0.16, 0.16, 0.16);
  return sprite;
}

function makeGlowSprite(texture: THREE.Texture, color: number, opacity: number, scale: number): THREE.Sprite {
  const material = new THREE.SpriteMaterial({
    map: texture,
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const sprite = new THREE.Sprite(material);
  sprite.userData.baseScale = scale;
  sprite.scale.set(scale, scale, scale);
  sprite.rotation.x = -Math.PI / 2;
  return sprite;
}

function makeLoopLabel(loop: LoopGroupLayout): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "700 34px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(232,234,240,0.82)";
    ctx.fillText(loop.title, canvas.width / 2, canvas.height / 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.position.set(loop.center.x, loop.center.y + 1.1, loop.center.z);
  sprite.scale.set(2.2, 0.55, 1);
  return sprite;
}

function seeded(index: number, salt: number): number {
  let hash = 2166136261 ^ salt;
  hash ^= index + 0x9e3779b9;
  hash = Math.imul(hash, 16777619);
  hash ^= hash >>> 13;
  return ((hash >>> 0) % 10000) / 10000;
}

function normalizeModel(object: THREE.Object3D, targetSize: number): void {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const largest = Math.max(size.x, size.y, size.z, 0.001);
  object.scale.setScalar(targetSize / largest);
  const scaledBox = new THREE.Box3().setFromObject(object);
  const center = scaledBox.getCenter(new THREE.Vector3());
  object.position.sub(center);
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh || child instanceof THREE.Sprite || child instanceof THREE.Points) {
      const geometry = child instanceof THREE.Mesh || child instanceof THREE.Points ? child.geometry : null;
      geometry?.dispose();
      const material = child.material;
      if (Array.isArray(material)) {
        material.forEach((item) => item.dispose());
      } else {
        material.dispose();
      }
    }
  });
}

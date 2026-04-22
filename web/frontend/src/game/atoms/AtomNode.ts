import * as THREE from "three";
import type { AtomLoopStatus, AtomStatus, CostBucket, WorkflowStep } from "../types.js";

const STATE_COLORS: Record<string, { color: number; emissive: number; emissiveIntensity: number }> = {
  idle: { color: 0x1e2235, emissive: 0x000000, emissiveIntensity: 0 },
  active: { color: 0x2e4aff, emissive: 0x1a2a99, emissiveIntensity: 0.45 },
  done: { color: 0x1a8c5a, emissive: 0x0a3a28, emissiveIntensity: 0.25 },
  error: { color: 0xcc3333, emissive: 0x660000, emissiveIntensity: 0.35 },
  waiting: { color: 0xe09b2a, emissive: 0x7a4a00, emissiveIntensity: 0.45 },
  skipped: { color: 0x2a2d3a, emissive: 0x000000, emissiveIntensity: 0 },
};

export class AtomNode {
  readonly group = new THREE.Group();
  readonly mesh: THREE.Mesh;
  private readonly material: THREE.MeshStandardMaterial;
  private readonly selectionRing: THREE.Mesh;
  private readonly costRing: THREE.Mesh;
  private readonly loopRing: THREE.Mesh;
  private readonly selectionMaterial: THREE.MeshBasicMaterial;
  private readonly costMaterial: THREE.MeshBasicMaterial;
  private readonly loopMaterial: THREE.MeshBasicMaterial;
  private readonly baseScale = new THREE.Vector3(1, 1, 1);
  private state = "idle";
  private selected = false;

  constructor(readonly step: WorkflowStep, textures: { normal?: THREE.Texture; grain?: THREE.Texture } = {}) {
    this.group.name = `atom:${step.id}`;
    this.material = new THREE.MeshStandardMaterial({
      color: STATE_COLORS.idle.color,
      roughness: step.type === "gate" ? 0.28 : 0.58,
      metalness: step.type === "gate" ? 0.42 : 0.18,
      normalMap: textures.normal,
      map: textures.grain,
    });
    const geometry = step.type === "gate"
      ? new THREE.OctahedronGeometry(0.56, 1)
      : new THREE.IcosahedronGeometry(0.52, 1);
    this.mesh = new THREE.Mesh(geometry, this.material);
    this.mesh.position.y = step.type === "gate" ? 0.16 : 0;
    this.mesh.userData.atomId = step.id;
    this.group.add(this.mesh);
    this.selectionMaterial = new THREE.MeshBasicMaterial({ color: 0x4d6fff, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    this.costMaterial = new THREE.MeshBasicMaterial({ color: 0xd9b84d, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    this.loopMaterial = new THREE.MeshBasicMaterial({ color: 0x272b3d, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false });
    this.selectionRing = makeRing(0.9, 0.035, this.selectionMaterial, 0.03);
    this.costRing = makeRing(1.03, 0.028, this.costMaterial, 0.035);
    this.loopRing = makeRing(1.16, 0.026, this.loopMaterial, 0.04);
    this.group.add(this.selectionRing, this.costRing, this.loopRing);
    this.group.add(makeLabel(step.title || step.id, step.id));
    if (!step.enabled) {
      this.setState({ id: step.id, state: "skipped", attempt: 0, startedAt: null, completedAt: null, lastEvent: null });
    }
  }

  setState(status: AtomStatus): void {
    this.state = status.state;
    const style = STATE_COLORS[status.state] ?? STATE_COLORS.idle;
    this.material.color.setHex(style.color);
    this.material.emissive.setHex(style.emissive);
    this.material.emissiveIntensity = style.emissiveIntensity;
    this.syncSelectionRing();
  }

  setTelemetry(cost: CostBucket | null, loop: AtomLoopStatus | null): void {
    const hasCost = Boolean(cost && (cost.effectiveUsd > 0 || cost.unknownCostCount > 0));
    this.costMaterial.opacity = hasCost ? 0.78 : 0;
    this.costMaterial.color.setHex(cost && cost.unknownCostCount > 0 ? 0xcc3333 : 0xd9b84d);
    void loop;
    this.loopMaterial.opacity = 0;
  }

  setSelected(selected: boolean): void {
    this.selected = selected;
    this.syncSelectionRing();
  }

  setLensDimmed(dimmed: boolean): void {
    this.material.transparent = dimmed;
    this.material.opacity = dimmed ? 0.34 : 1;
    this.material.emissiveIntensity = dimmed ? 0.03 : (STATE_COLORS[this.state] ?? STATE_COLORS.idle).emissiveIntensity;
    this.material.needsUpdate = true;
    for (const child of this.group.children) {
      if (child instanceof THREE.Sprite) {
        child.material.opacity = dimmed ? 0.28 : 1;
      }
    }
  }

  animate(timeMs: number): void {
    if (this.state === "active" || this.state === "waiting") {
      const amount = this.state === "waiting" ? 0.04 : 0.025;
      const speed = this.state === "waiting" ? 0.006 : 0.003;
      const scale = 1 + Math.sin(timeMs * speed) * amount;
      this.group.scale.set(scale, scale, scale);
      return;
    }
    this.group.scale.copy(this.baseScale);
  }

  dispose(): void {
    this.mesh.geometry.dispose();
    this.material.dispose();
    for (const child of this.group.children) {
      if (child instanceof THREE.Mesh || child instanceof THREE.Sprite) {
        if (child instanceof THREE.Mesh) {
          child.geometry.dispose();
        }
        const material = child.material;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else {
          material.dispose();
        }
      }
    }
  }

  private syncSelectionRing(): void {
    this.selectionMaterial.opacity = statusRingOpacity(this.state, this.selected);
    this.selectionMaterial.color.setHex(this.selected ? 0x41c7c7 : statusRingColor(this.state));
  }
}

function statusRingColor(state: string): number {
  if (state === "error") {
    return 0xcc3333;
  }
  if (state === "waiting") {
    return 0xe09b2a;
  }
  return 0x4d6fff;
}

function statusRingOpacity(state: string, selected: boolean): number {
  if (selected) {
    return 0.95;
  }
  return state === "active" || state === "waiting" || state === "error" ? 0.78 : 0;
}

function makeRing(radius: number, tube: number, material: THREE.MeshBasicMaterial, y: number): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 8, 48), material);
  mesh.rotation.x = Math.PI / 2;
  mesh.position.y = y;
  return mesh;
}

function makeLabel(text: string, id: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "600 34px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#E8EAF0";
    ctx.fillText(truncateLabel(text), canvas.width / 2, canvas.height / 2 - 12);
    ctx.font = "500 18px JetBrains Mono, monospace";
    ctx.fillStyle = "rgba(199,202,214,0.68)";
    ctx.fillText(truncateLabel(id), canvas.width / 2, canvas.height / 2 + 28);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.position.set(0, -0.72, 0);
  sprite.scale.set(1.75, 0.44, 1);
  return sprite;
}

function truncateLabel(text: string): string {
  return text.length > 24 ? `${text.slice(0, 21)}...` : text;
}

import * as THREE from "three";
import {
  flowKindColor,
  flowModeOpacity,
  flowModeRadiusMultiplier,
  type FlowKind,
  type FlowMode,
} from "./FlowTypes.js";

export type FlowPathOptions = {
  id: string;
  from: THREE.Vector3;
  to: THREE.Vector3;
  kind: FlowKind;
  mode?: FlowMode;
};

export class FlowPath {
  readonly curve: THREE.CatmullRomCurve3;
  readonly mesh: THREE.Mesh;
  private readonly material: THREE.MeshBasicMaterial;
  private kind: FlowKind;
  private mode: FlowMode;
  private baseRadius: number;

  constructor(readonly options: FlowPathOptions) {
    this.kind = options.kind;
    this.mode = options.mode ?? "idle";
    this.baseRadius = radiusForKind(this.kind);
    this.curve = buildCurve(options.from, options.to, this.kind);
    this.material = new THREE.MeshBasicMaterial({
      color: flowKindColor(this.kind),
      transparent: true,
      opacity: flowModeOpacity(this.mode),
    });
    this.mesh = new THREE.Mesh(this.buildGeometry(), this.material);
    this.mesh.name = `flow:${options.id}`;
    this.mesh.userData.flowPathId = options.id;
    this.mesh.userData.flowKind = this.kind;
  }

  setMode(mode: FlowMode, kind = this.kind): void {
    if (mode === this.mode && kind === this.kind) {
      return;
    }
    const radiusChanged = radiusForKind(kind) * flowModeRadiusMultiplier(mode) !== this.baseRadius * flowModeRadiusMultiplier(this.mode);
    this.kind = kind;
    this.mode = mode;
    this.baseRadius = radiusForKind(kind);
    this.material.color.setHex(flowKindColor(kind));
    this.material.opacity = flowModeOpacity(mode);
    this.mesh.userData.flowKind = kind;
    if (radiusChanged) {
      this.mesh.geometry.dispose();
      this.mesh.geometry = this.buildGeometry();
    }
  }

  pointAt(t: number): THREE.Vector3 {
    return this.curve.getPointAt(clamp01(t));
  }

  tangentAt(t: number): THREE.Vector3 {
    return this.curve.getTangentAt(clamp01(t));
  }

  dispose(): void {
    this.mesh.geometry.dispose();
    this.material.dispose();
  }

  private buildGeometry(): THREE.TubeGeometry {
    return new THREE.TubeGeometry(
      this.curve,
      30,
      this.baseRadius * flowModeRadiusMultiplier(this.mode),
      7,
      false,
    );
  }
}

function buildCurve(from: THREE.Vector3, to: THREE.Vector3, kind: FlowKind): THREE.CatmullRomCurve3 {
  const midA = from.clone().lerp(to, 0.32);
  const midB = from.clone().lerp(to, 0.68);
  const distance = from.distanceTo(to);
  const lift = Math.min(1.35, Math.max(0.24, distance * liftRatio(kind)));
  const side = from.clone().sub(to).cross(new THREE.Vector3(0, 1, 0)).normalize();
  if (side.lengthSq() > 0) {
    const bow = Math.min(0.82, distance * bowRatio(kind));
    midA.addScaledVector(side, bow);
    midB.addScaledVector(side, -bow * 0.62);
  }
  midA.y += lift;
  midB.y += lift * (kind === "gate" || kind === "repair" ? 1.18 : 0.86);
  return new THREE.CatmullRomCurve3([from.clone(), midA, midB, to.clone()]);
}

function liftRatio(kind: FlowKind): number {
  if (kind === "gate" || kind === "repair" || kind === "intent") {
    return 0.16;
  }
  if (kind === "memory" || kind === "review") {
    return 0.14;
  }
  return 0.11;
}

function bowRatio(kind: FlowKind): number {
  if (kind === "gate" || kind === "repair") {
    return 0.08;
  }
  if (kind === "intent") {
    return 0.095;
  }
  return 0.055;
}

function radiusForKind(kind: FlowKind): number {
  if (kind === "gate" || kind === "repair" || kind === "intent") {
    return 0.026;
  }
  if (kind === "memory" || kind === "review" || kind === "replay") {
    return 0.022;
  }
  return 0.018;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

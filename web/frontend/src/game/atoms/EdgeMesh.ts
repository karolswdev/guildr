import * as THREE from "three";
import type { EdgeKind } from "../layout.js";
import { FlowPath } from "../flows/FlowPath.js";
import type { FlowKind, FlowMode } from "../flows/FlowTypes.js";

export class EdgeMesh {
  readonly flow: FlowPath;

  constructor(from: THREE.Vector3, to: THREE.Vector3, kind: EdgeKind, id?: string) {
    this.flow = new FlowPath({
      id: id || `${kind}:${from.x.toFixed(2)},${from.y.toFixed(2)},${from.z.toFixed(2)}->${to.x.toFixed(2)},${to.y.toFixed(2)},${to.z.toFixed(2)}`,
      from,
      to,
      kind: flowKindForEdge(kind),
      mode: kind === "sequence" ? "queued" : "active",
    });
  }

  get mesh(): THREE.Mesh {
    return this.flow.mesh;
  }

  get curve(): THREE.CatmullRomCurve3 {
    return this.flow.curve;
  }

  setMode(mode: FlowMode, kind?: FlowKind): void {
    this.flow.setMode(mode, kind);
  }

  pointAt(t: number): THREE.Vector3 {
    return this.flow.pointAt(t);
  }

  tangentAt(t: number): THREE.Vector3 {
    return this.flow.tangentAt(t);
  }

  dispose(): void {
    this.flow.dispose();
  }
}

function flowKindForEdge(kind: EdgeKind): FlowKind {
  if (kind === "gate") {
    return "gate";
  }
  if (kind === "loop") {
    return "review";
  }
  if (kind === "memory") {
    return "memory";
  }
  return "sequence";
}

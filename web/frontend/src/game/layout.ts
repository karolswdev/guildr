import type { WorkflowStep } from "./types.js";

export type AtomLane = "context" | "plan" | "build" | "verify" | "ship" | "gate";
export type EdgeKind = "sequence" | "gate" | "loop" | "memory";

export type Vec3 = {
  x: number;
  y: number;
  z: number;
};

export type AtomLayoutNode = {
  id: string;
  title: string;
  type: string;
  enabled: boolean;
  lane: AtomLane;
  loopId: string;
  orbitAngle: number;
  bobPhase: number;
  bobAmp: number;
  driftAxis: Vec3;
  x: number;
  y: number;
  z: number;
};

export type AtomLayoutEdge = {
  id: string;
  from: string;
  to: string;
  kind: EdgeKind;
};

export type LoopGroupLayout = {
  id: string;
  title: string;
  lane: AtomLane;
  nodeIds: string[];
  center: Vec3;
  radius: number;
};

export type AtomLayout = {
  nodes: AtomLayoutNode[];
  edges: AtomLayoutEdge[];
  loops: LoopGroupLayout[];
  bounds: {
    center: Vec3;
    radius: number;
  };
};

const LOOP_ORDER = ["memory_loop", "core_loop", "escalation_loop", "ship_loop"] as const;

const LOOP_DEFS: Record<string, { title: string; lane: AtomLane; center: Vec3; radius: number }> = {
  memory_loop: { title: "Memory Orbit", lane: "context", center: { x: -4.2, y: 1.25, z: -1.2 }, radius: 1.55 },
  core_loop: { title: "Build Loop", lane: "build", center: { x: 0, y: 0, z: 0 }, radius: 2.35 },
  escalation_loop: { title: "Review Orbit", lane: "verify", center: { x: 3.85, y: 1.35, z: -1.65 }, radius: 1.55 },
  ship_loop: { title: "Ship Orbit", lane: "ship", center: { x: 4.45, y: -0.7, z: 1.55 }, radius: 1.35 },
};

export function layoutWorkflowAtoms(workflow: WorkflowStep[]): AtomLayout {
  const steps = workflow.map((step) => ({
    step,
    loopId: loopForStep(step),
    lane: laneForStep(step),
  }));
  const grouped = new Map<string, typeof steps>();
  for (const item of steps) {
    const group = grouped.get(item.loopId) ?? [];
    group.push(item);
    grouped.set(item.loopId, group);
  }

  const loops: LoopGroupLayout[] = [];
  const nodes: AtomLayoutNode[] = [];
  for (const loopId of LOOP_ORDER) {
    const members = grouped.get(loopId) ?? [];
    if (members.length === 0) {
      continue;
    }
    const def = LOOP_DEFS[loopId];
    const radius = Math.max(def.radius, members.length > 2 ? 1.4 + members.length * 0.2 : def.radius);
    const nodeIds: string[] = [];
    members.forEach((item, index) => {
      const angle = angleForMember(loopId, index, members.length);
      const pos = orbitPosition(def.center, radius, angle, item.step.id, index, members.length, item.step.type === "gate");
      nodes.push({
        id: item.step.id,
        title: item.step.title || item.step.id,
        type: item.step.type,
        enabled: item.step.enabled,
        lane: item.lane,
        loopId,
        orbitAngle: angle,
        bobPhase: hashFloat(item.step.id, 0) * Math.PI * 2,
        bobAmp: 0.05 + hashFloat(item.step.id, 1) * 0.07,
        driftAxis: unitVectorFromHash(item.step.id),
        x: pos.x,
        y: pos.y,
        z: pos.z,
      });
      nodeIds.push(item.step.id);
    });
    loops.push({ id: loopId, title: def.title, lane: def.lane, nodeIds, center: def.center, radius });
  }

  const edges: AtomLayoutEdge[] = [];
  for (let index = 0; index < nodes.length - 1; index += 1) {
    addEdge(edges, nodes[index], nodes[index + 1], "sequence");
    if (nodes[index].lane === "gate") {
      for (let next = index + 2; next < Math.min(nodes.length, index + 4); next += 1) {
        if (nodes[next].lane !== "gate") {
          addEdge(edges, nodes[index], nodes[next], "gate");
        }
      }
    }
  }
  for (const loop of loops) {
    const members = loop.nodeIds.map((id) => nodes.find((node) => node.id === id)).filter((node): node is AtomLayoutNode => Boolean(node));
    if (members.length > 3) {
      addEdge(edges, members[members.length - 1], members[0], "loop");
    }
  }

  return {
    nodes,
    edges,
    loops,
    bounds: boundingSphere(nodes, loops),
  };
}

function loopForStep(step: WorkflowStep): string {
  if (step.id === "memory_refresh" || step.id === "persona_forum") {
    return "memory_loop";
  }
  if (step.id === "guru_escalation" || step.id === "review" || step.id === "approve_review") {
    return "escalation_loop";
  }
  if (step.id === "deployment") {
    return "ship_loop";
  }
  return "core_loop";
}

function laneForStep(step: WorkflowStep): AtomLane {
  if (step.type === "gate" || step.id.startsWith("approve_")) {
    return "gate";
  }
  if (step.id.includes("memory") || step.id.includes("persona")) {
    return "context";
  }
  if (step.id.includes("architect") || step.id.includes("plan")) {
    return "plan";
  }
  if (step.id.includes("test") || step.id.includes("review") || step.id.includes("guru")) {
    return "verify";
  }
  if (step.id.includes("deploy") || step.id.includes("ship")) {
    return "ship";
  }
  return "build";
}

function angleForMember(loopId: string, index: number, count: number): number {
  const offsets: Record<string, number> = {
    memory_loop: -0.6,
    core_loop: -2.25,
    escalation_loop: 0.2,
    ship_loop: 1.1,
  };
  return (Math.PI * 2 * index) / Math.max(1, count) + (offsets[loopId] ?? 0);
}

function orbitPosition(center: Vec3, radius: number, angle: number, id: string, index: number, count: number, isGate: boolean): Vec3 {
  const shell = radius * (0.82 + hashFloat(id, 2) * 0.28);
  const elevation = count <= 2 ? (index === 0 ? 0.28 : -0.22) : -0.44 + (index / Math.max(1, count - 1)) * 0.88;
  const yJitter = (hashFloat(id, 3) - 0.5) * 0.34 + (isGate ? 0.22 : 0);
  return {
    x: center.x + Math.cos(angle) * shell,
    y: center.y + elevation + yJitter,
    z: center.z + Math.sin(angle) * shell * (0.76 + hashFloat(id, 4) * 0.18),
  };
}

function addEdge(edges: AtomLayoutEdge[], from: AtomLayoutNode, to: AtomLayoutNode, kind: EdgeKind): void {
  const id = `${from.id}->${to.id}`;
  if (!edges.some((edge) => edge.id === id)) {
    edges.push({ id, from: from.id, to: to.id, kind: from.loopId === to.loopId ? kind : "loop" });
  }
}

function boundingSphere(nodes: AtomLayoutNode[], loops: LoopGroupLayout[]): AtomLayout["bounds"] {
  const points = [
    ...nodes.map((node) => ({ x: node.x, y: node.y, z: node.z })),
    ...loops.map((loop) => loop.center),
  ];
  const center = points.reduce(
    (acc, point) => ({ x: acc.x + point.x / points.length, y: acc.y + point.y / points.length, z: acc.z + point.z / points.length }),
    { x: 0, y: 0, z: 0 },
  );
  const radius = Math.max(
    4,
    ...points.map((point) => Math.hypot(point.x - center.x, point.y - center.y, point.z - center.z)),
  ) + 2.2;
  return { center, radius };
}

function unitVectorFromHash(id: string): Vec3 {
  const angle = hashFloat(id, 5) * Math.PI * 2;
  const y = hashFloat(id, 6) * 0.8 - 0.4;
  const x = Math.cos(angle);
  const z = Math.sin(angle);
  const length = Math.hypot(x, y, z) || 1;
  return { x: x / length, y: y / length, z: z / length };
}

function hashFloat(id: string, salt: number): number {
  let hash = 2166136261 ^ salt;
  for (let index = 0; index < id.length; index += 1) {
    hash ^= id.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 10000) / 10000;
}

import type { AtomLayout, AtomLayoutEdge } from "../layout.js";
import type { EngineSnapshot, RunEvent } from "../types.js";
import type { FlowCommand, FlowKind, FlowMode } from "./FlowTypes.js";

export function commandsForRunEvent(event: RunEvent, layout: AtomLayout, snapshot: EngineSnapshot): FlowCommand[] {
  const type = String(event.type ?? "");
  const atomId = eventAtomId(event);
  const edge = atomId ? edgeForAtom(layout, atomId, edgeDirectionFor(type)) : null;
  const eventId = typeof event.event_id === "string" ? event.event_id : null;
  const commands: FlowCommand[] = [];

  if (edge && (type === "phase_start" || type === "atom_started" || type === "phase_retry")) {
    commands.push(pathMode(edge.id, "active", kindForAtom(layout, atomId, "sequence")));
    commands.push({ type: "pulse", pathId: edge.id, kind: kindForAtom(layout, atomId, "sequence"), mode: "active", eventId });
  }
  if (edge && (type === "phase_done" || type === "atom_completed" || type === "checkpoint")) {
    commands.push(pathMode(edge.id, "queued", kindForAtom(layout, atomId, "sequence")));
    commands.push({ type: "pulse", pathId: edge.id, kind: kindForAtom(layout, atomId, "sequence"), mode: "queued", eventId });
  }
  if (edge && type === "usage_recorded") {
    commands.push({ type: "dust", pathId: edge.id, kind: "cost", count: 3, eventId });
    commands.push(pathMode(edge.id, "selected", "cost"));
  }
  if (edge && type === "provider_call_error") {
    commands.push({ type: "repair_backflow", pathId: edge.id, eventId });
    commands.push(pathMode(edge.id, "blocked", "repair"));
  }
  if (edge && (type === "gate_opened" || type === "budget_gate_opened")) {
    commands.push(pathMode(edge.id, "queued", "gate"));
  }
  if (edge && (type === "gate_decided" || type === "budget_gate_decided")) {
    commands.push(pathMode(edge.id, event.decision === "rejected" ? "blocked" : "active", "gate"));
  }
  if (edge && type === "operator_intent") {
    commands.push(pathMode(edge.id, "selected", "intent"));
    commands.push({ type: "pulse", pathId: edge.id, kind: "intent", mode: "selected", eventId });
  }
  if (edge && type === "loop_blocked") {
    commands.push(pathMode(edge.id, "blocked", "repair"));
  }
  if (edge && type === "loop_repaired") {
    commands.push(pathMode(edge.id, "reversing", "repair"));
  }
  if (!snapshot.live && edge) {
    commands.push({ type: "replay", mode: "freeze", replayIndex: snapshot.replayIndex });
  }

  return commands;
}

function pathMode(pathId: string, mode: FlowMode, kind: FlowKind): FlowCommand {
  return { type: "path_mode", pathId, mode, kind };
}

function eventAtomId(event: RunEvent): string {
  for (const key of ["atom_id", "step", "phase", "role"]) {
    const value = event[key];
    if (typeof value === "string" && value) {
      return value;
    }
  }
  return "";
}

function edgeDirectionFor(type: string): "incoming" | "outgoing" | "nearest" {
  if (type === "phase_done" || type === "atom_completed" || type === "checkpoint") {
    return "outgoing";
  }
  return "incoming";
}

function edgeForAtom(layout: AtomLayout, atomId: string, direction: "incoming" | "outgoing" | "nearest"): AtomLayoutEdge | null {
  if (direction !== "outgoing") {
    const incoming = layout.edges.find((edge) => edge.to === atomId);
    if (incoming) {
      return incoming;
    }
  }
  if (direction !== "incoming") {
    const outgoing = layout.edges.find((edge) => edge.from === atomId);
    if (outgoing) {
      return outgoing;
    }
  }
  return layout.edges.find((edge) => edge.from === atomId || edge.to === atomId) ?? null;
}

function kindForAtom(layout: AtomLayout, atomId: string, fallback: FlowKind): FlowKind {
  const node = layout.nodes.find((item) => item.id === atomId);
  if (!node) {
    return fallback;
  }
  if (node.lane === "gate") {
    return "gate";
  }
  if (node.lane === "context") {
    return "memory";
  }
  if (node.lane === "plan") {
    return "planning";
  }
  if (node.lane === "verify") {
    return "review";
  }
  if (node.lane === "build") {
    return "implementation";
  }
  return fallback;
}

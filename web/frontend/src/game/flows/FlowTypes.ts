export type FlowKind =
  | "sequence"
  | "planning"
  | "implementation"
  | "gate"
  | "review"
  | "repair"
  | "memory"
  | "cost"
  | "intent"
  | "replay";

export type FlowMode =
  | "idle"
  | "active"
  | "queued"
  | "blocked"
  | "reversing"
  | "selected";

export type Vec3Like = {
  x: number;
  y: number;
  z: number;
};

export type FlowPathCommand = {
  type: "path_mode";
  pathId: string;
  mode: FlowMode;
  kind?: FlowKind;
};

export type FlowPulseCommand = {
  type: "pulse";
  pathId: string;
  kind: FlowKind;
  mode?: FlowMode;
  color?: number;
  size?: number;
  speed?: number;
  eventId?: string | null;
};

export type FlowDustCommand = {
  type: "dust";
  pathId: string;
  kind: FlowKind;
  color?: number;
  count?: number;
  eventId?: string | null;
};

export type FlowRepairBackflowCommand = {
  type: "repair_backflow";
  pathId: string;
  eventId?: string | null;
};

export type FlowMemoryStreamCommand = {
  type: "memory_stream";
  fromId: string;
  toId: string;
  eventId?: string | null;
};

export type FlowReplayCommand = {
  type: "replay";
  mode: "freeze" | "reverse" | "resume";
  replayIndex: number;
};

export type FlowCommand =
  | FlowPathCommand
  | FlowPulseCommand
  | FlowDustCommand
  | FlowRepairBackflowCommand
  | FlowMemoryStreamCommand
  | FlowReplayCommand;

export function flowKindColor(kind: FlowKind): number {
  const colors: Record<FlowKind, number> = {
    sequence: 0x6f7894,
    planning: 0x4d6fff,
    implementation: 0xe8eaf0,
    gate: 0xe09b2a,
    review: 0x7a5cff,
    repair: 0xcc6633,
    memory: 0x41c7c7,
    cost: 0xd9b84d,
    intent: 0xffd166,
    replay: 0x9b7eff,
  };
  return colors[kind];
}

export function flowModeOpacity(mode: FlowMode): number {
  const opacities: Record<FlowMode, number> = {
    idle: 0.42,
    active: 0.92,
    queued: 0.72,
    blocked: 0.9,
    reversing: 0.76,
    selected: 1,
  };
  return opacities[mode];
}

export function flowModeRadiusMultiplier(mode: FlowMode): number {
  if (mode === "active" || mode === "selected") {
    return 1.35;
  }
  if (mode === "blocked") {
    return 1.22;
  }
  if (mode === "queued") {
    return 1.1;
  }
  return 1;
}

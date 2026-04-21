import type {
  AtomLoopStatus,
  AtomState,
  AtomStatus,
  CostBucket,
  CostSnapshot,
  CostSource,
  EngineSnapshot,
  LoopSnapshot,
  LoopStage,
  MemPalaceStatus,
  RunEvent,
  WorkflowStep,
} from "./types.js";

type SnapshotListener = (snapshot: EngineSnapshot) => void;
type EventListener = (event: RunEvent, snapshot: EngineSnapshot) => void;
type ConnectionListener = (state: "live" | "reconnecting" | "offline" | "history") => void;

export class EventEngine {
  private projectId = "";
  private eventSource: EventSource | null = null;
  private workflow: WorkflowStep[] = [];
  private history: RunEvent[] = [];
  private seenEventIds = new Set<string>();
  private atoms: Record<string, AtomStatus> = {};
  private cost: CostSnapshot = emptyCostSnapshot();
  private loops: LoopSnapshot = emptyLoopSnapshot();
  private memPalaceStatus: MemPalaceStatus | null = null;
  private replayIndex = -1;
  private snapshotListeners = new Set<SnapshotListener>();
  private eventListeners = new Set<EventListener>();
  private connectionListeners = new Set<ConnectionListener>();

  constructor(projectId = "", workflow: WorkflowStep[] = []) {
    this.projectId = projectId;
    this.setWorkflow(workflow);
  }

  async init(projectId: string, workflow: WorkflowStep[] = []): Promise<void> {
    this.projectId = projectId;
    this.setWorkflow(workflow);
    this.emitConnection("history");
    const response = await fetch(`/api/projects/${projectId}/events?limit=500`);
    if (!response.ok) {
      throw new Error(`Event history ${response.status}: ${response.statusText}`);
    }
    const payload = await response.json() as { events?: RunEvent[] };
    this.loadHistory(Array.isArray(payload.events) ? payload.events : []);
    this.connect();
  }

  connect(): void {
    if (!this.projectId || typeof EventSource === "undefined") {
      return;
    }
    this.eventSource?.close();
    this.eventSource = new EventSource(`/api/projects/${this.projectId}/stream`);
    this.eventSource.onopen = () => this.emitConnection("live");
    this.eventSource.onmessage = (message: MessageEvent) => {
      if (typeof message.data !== "string" || message.data.startsWith(":")) {
        return;
      }
      try {
        this.applyEvent(JSON.parse(message.data) as RunEvent);
      } catch {
        this.emitConnection("reconnecting");
      }
    };
    this.eventSource.onerror = () => {
      this.emitConnection("reconnecting");
    };
  }

  close(): void {
    this.eventSource?.close();
    this.eventSource = null;
  }

  setWorkflow(workflow: WorkflowStep[]): void {
    this.workflow = workflow.map((step) => ({ ...step }));
    this.rebuildFromHistory();
    this.emitSnapshot();
  }

  applyEvent(event: RunEvent): boolean {
    const eventId = typeof event.event_id === "string" ? event.event_id : "";
    if (eventId && this.seenEventIds.has(eventId)) {
      return false;
    }
    if (eventId) {
      this.seenEventIds.add(eventId);
    }
    this.history.push(event);
    if (this.replayIndex < 0) {
      this.applyFold(event);
      this.emitEvent(event);
      this.emitSnapshot();
    } else {
      this.emitSnapshot();
    }
    return true;
  }

  loadHistory(events: RunEvent[]): void {
    this.history = [];
    this.seenEventIds.clear();
    this.atoms = this.buildIdleAtoms();
    this.cost = emptyCostSnapshot();
    this.loops = emptyLoopSnapshot();
    this.memPalaceStatus = null;
    this.replayIndex = -1;
    for (const event of events) {
      const eventId = typeof event.event_id === "string" ? event.event_id : "";
      if (eventId && this.seenEventIds.has(eventId)) {
        continue;
      }
      if (eventId) {
        this.seenEventIds.add(eventId);
      }
      this.history.push(event);
      this.applyFold(event);
    }
    this.emitSnapshot();
  }

  scrubTo(index: number): void {
    if (this.history.length === 0) {
      this.replayIndex = -1;
      this.emitSnapshot();
      return;
    }
    const clamped = Math.max(0, Math.min(index, this.history.length - 1));
    this.atoms = this.buildIdleAtoms();
    this.cost = emptyCostSnapshot();
    this.loops = emptyLoopSnapshot();
    this.memPalaceStatus = null;
    for (let i = 0; i <= clamped; i += 1) {
      this.applyFold(this.history[i]);
    }
    this.replayIndex = clamped;
    this.emitSnapshot();
  }

  resumeLive(): void {
    this.replayIndex = -1;
    this.rebuildFromHistory();
    this.emitSnapshot();
  }

  snapshot(): EngineSnapshot {
    return {
      projectId: this.projectId,
      runId: this.currentRunId(),
      atoms: cloneAtoms(this.atoms),
      events: this.history.map((event) => ({ ...event })),
      scrubIndex: this.replayIndex,
      isLive: this.replayIndex < 0,
      memPalaceStatus: this.memPalaceStatus ? { ...this.memPalaceStatus } : null,
      historyLength: this.history.length,
      replayIndex: this.replayIndex,
      live: this.replayIndex < 0,
      cost: cloneCostSnapshot(this.cost),
      loops: cloneLoopSnapshot(this.loops),
    };
  }

  onSnapshot(listener: SnapshotListener): () => void {
    this.snapshotListeners.add(listener);
    return () => this.snapshotListeners.delete(listener);
  }

  onEvent(listener: EventListener): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  onConnection(listener: ConnectionListener): () => void {
    this.connectionListeners.add(listener);
    return () => this.connectionListeners.delete(listener);
  }

  private rebuildFromHistory(): void {
    this.atoms = this.buildIdleAtoms();
    this.cost = emptyCostSnapshot();
    this.loops = emptyLoopSnapshot();
    this.memPalaceStatus = null;
    for (const event of this.history) {
      this.applyFold(event);
    }
  }

  private emitSnapshot(): void {
    const snapshot = this.snapshot();
    for (const listener of this.snapshotListeners) {
      listener(snapshot);
    }
  }

  private emitEvent(event: RunEvent): void {
    const snapshot = this.snapshot();
    for (const listener of this.eventListeners) {
      listener(event, snapshot);
    }
  }

  private emitConnection(state: "live" | "reconnecting" | "offline" | "history"): void {
    for (const listener of this.connectionListeners) {
      listener(state);
    }
  }

  private applyFold(event: RunEvent | undefined): void {
    if (!event) {
      return;
    }
    const type = String(event.type ?? "");
    if (type === "run_started") {
      this.atoms = this.buildIdleAtoms();
      this.cost = emptyCostSnapshot();
      this.loops = emptyLoopSnapshot();
      this.memPalaceStatus = null;
      return;
    }
    if (type === "phase_start") {
      this.setAtomState(stepId(event), "active", event, true);
      return;
    }
    if (type === "phase_done") {
      this.setAtomState(stepId(event), "done", event, false, true);
      return;
    }
    if (type === "phase_retry") {
      this.setAtomState(stepId(event), "active", event, true);
      return;
    }
    if (type === "phase_error") {
      this.setAtomState(stepId(event), "error", event);
      return;
    }
    if (type === "gate_opened") {
      this.setAtomState(stepId(event), "waiting", event);
      return;
    }
    if (type === "gate_decided") {
      this.setAtomState(stepId(event), event.decision === "approved" ? "done" : "error", event, false, true);
      return;
    }
    if (type === "checkpoint") {
      this.setAtomState(stepId(event), "done", event, false, true);
      return;
    }
    if (type === "run_complete") {
      this.completeActiveAtoms(event);
      return;
    }
    if (type === "usage_recorded") {
      this.applyUsage(event);
      return;
    }
    if (
      type === "budget_warning" ||
      type === "budget_exceeded" ||
      type === "budget_gate_opened" ||
      type === "budget_gate_decided"
    ) {
      this.applyBudgetEvent(event, type);
      return;
    }
    if (
      type === "loop_entered" ||
      type === "loop_progressed" ||
      type === "loop_blocked" ||
      type === "loop_repaired" ||
      type === "loop_completed" ||
      type === "loop_reopened"
    ) {
      this.applyLoopEvent(event, type);
      return;
    }
    if (type === "memory_status" || type === "memory_refreshed") {
      this.applyMemoryEvent(event);
    }
  }

  private buildIdleAtoms(): Record<string, AtomStatus> {
    return Object.fromEntries(
      this.workflow.map((step) => [
        step.id,
        {
          id: step.id,
          state: step.enabled ? "idle" : "skipped",
          attempt: 0,
          startedAt: null,
          completedAt: null,
          lastEvent: null,
        } satisfies AtomStatus,
      ]),
    );
  }

  private setAtomState(
    id: string,
    state: AtomState,
    event: RunEvent,
    incrementAttempt = false,
    complete = false,
  ): void {
    if (!id) {
      return;
    }
    const current = this.atoms[id] ?? {
      id,
      state: "idle",
      attempt: 0,
      startedAt: null,
      completedAt: null,
      lastEvent: null,
    } satisfies AtomStatus;
    const ts = timeMs(event.ts);
    this.atoms[id] = {
      ...current,
      state,
      attempt: incrementAttempt ? current.attempt + 1 : current.attempt,
      startedAt: current.startedAt ?? (state === "active" ? ts : null),
      completedAt: complete ? ts : current.completedAt,
      lastEvent: event,
    };
  }

  private completeActiveAtoms(event: RunEvent): void {
    for (const atom of Object.values(this.atoms)) {
      if (atom.state === "active" || atom.state === "waiting") {
        this.setAtomState(atom.id, "done", event, false, true);
      }
    }
  }

  private applyUsage(event: RunEvent): void {
    const cost = costFields(event);
    const usage = usageFields(event);
    addCost(this.cost, cost, usage);
    addCost(bucket(this.cost.byProvider, key(event.provider_name, "unknown")), cost, usage);
    addCost(bucket(this.cost.byModel, key(event.model, "unknown")), cost, usage);
    addCost(bucket(this.cost.byRole, key(event.role, "unknown")), cost, usage);
    addCost(bucket(this.cost.byPhase, key(event.step, "run")), cost, usage);
    addCost(bucket(this.cost.byAtom, key(event.atom_id, key(event.step, "run"))), cost, usage);

    const source = cost.source;
    this.cost.sourceCounts[source] += 1;

    const budget = objectValue(event.budget);
    const remainingRun = numberOrNull(budget.remaining_run_budget_usd);
    const remainingPhase = numberOrNull(budget.remaining_phase_budget_usd);
    if (remainingRun !== null) {
      this.cost.remainingRunBudgetUsd = remainingRun;
    }
    if (remainingPhase !== null) {
      this.cost.remainingPhaseBudgetUsd = remainingPhase;
    }
  }

  private applyBudgetEvent(event: RunEvent, type: string): void {
    const gateId = key(event.gate_id, key(event.gate, "budget"));
    const level = key(event.level, "run");
    if (type === "budget_warning" && !this.cost.warnings.includes(level)) {
      this.cost.warnings.push(level);
      return;
    }
    if (type === "budget_exceeded" && !this.cost.exceeded.includes(level)) {
      this.cost.exceeded.push(level);
      return;
    }
    if (type === "budget_gate_opened" && !this.cost.openBudgetGateIds.includes(gateId)) {
      this.cost.openBudgetGateIds.push(gateId);
      return;
    }
    if (type !== "budget_gate_decided") {
      return;
    }

    const newRunBudget = numberOrNull(event.new_run_budget_usd);
    const newPhaseBudget = numberOrNull(event.new_phase_budget_usd);
    if (newRunBudget !== null) {
      this.cost.runBudgetUsd = newRunBudget;
    }
    if (newPhaseBudget !== null) {
      this.cost.phaseBudgetUsd = newPhaseBudget;
    }
    const atDecision = objectValue(event.budget_at_decision);
    this.cost.remainingRunBudgetUsd = numberOrNull(atDecision.remaining_run_budget_usd);
    this.cost.remainingPhaseBudgetUsd = numberOrNull(atDecision.remaining_phase_budget_usd);
    if (event.decision === "rejected") {
      this.cost.runHalted = true;
    }
    this.cost.openBudgetGateIds = this.cost.openBudgetGateIds.filter((id) => id !== gateId);
  }

  private applyLoopEvent(event: RunEvent, type: string): void {
    const atomId = key(event.atom_id, key(event.step, "run"));
    const stage = loopStage(event.loop_stage);
    const current = this.loops.byAtom[atomId] ?? emptyAtomLoopStatus(atomId);
    const artifactRefs = mergeRefs(current.artifactRefs, arrayOfStrings(event.artifact_refs));
    const evidenceRefs = mergeRefs(current.evidenceRefs, arrayOfStrings(event.evidence_refs));
    const memoryRefs = mergeRefs(current.memoryRefs, arrayOfStrings(event.memory_refs));
    const next: AtomLoopStatus = {
      ...current,
      currentStage: stage,
      previousStage: current.currentStage === stage ? current.previousStage : current.currentStage,
      nextExpectedStage: nextLoopStage(stage),
      repairCount: current.repairCount + (type === "loop_repaired" || stage === "repair" ? 1 : 0),
      reopenedCount: current.reopenedCount + (type === "loop_reopened" ? 1 : 0),
      artifactRefs,
      evidenceRefs,
      memoryRefs,
      lastEvent: event,
    };
    this.loops.byAtom[atomId] = next;
    this.loops.lastLoopEvent = event;
    this.recountLoopStages();
  }

  private applyMemoryEvent(event: RunEvent): void {
    this.memPalaceStatus = {
      initialized: Boolean(event.initialized),
      wing: typeof event.wing === "string" ? event.wing : null,
      cached_wakeup: typeof event.cached_wakeup === "string" ? event.cached_wakeup : null,
      last_search: typeof event.last_search === "string" ? event.last_search : null,
    };
  }

  private recountLoopStages(): void {
    this.loops.activeStageCounts = emptyStageCounts();
    for (const loop of Object.values(this.loops.byAtom)) {
      if (loop.currentStage) {
        this.loops.activeStageCounts[loop.currentStage] += 1;
      }
    }
  }

  private currentRunId(): string | null {
    for (let index = this.history.length - 1; index >= 0; index -= 1) {
      const runId = this.history[index].run_id;
      if (typeof runId === "string" && runId) {
        return runId;
      }
    }
    return null;
  }
}

export function emptyCostBucket(): CostBucket {
  return {
    effectiveUsd: 0,
    providerReportedUsd: 0,
    estimatedUsd: 0,
    unknownCostCount: 0,
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    reasoningTokens: 0,
  };
}

export function emptyCostSnapshot(): CostSnapshot {
  return {
    ...emptyCostBucket(),
    byProvider: {},
    byModel: {},
    byRole: {},
    byPhase: {},
    byAtom: {},
    sourceCounts: {
      provider_reported: 0,
      rate_card_estimate: 0,
      local_estimate: 0,
      unknown: 0,
    },
    runBudgetUsd: null,
    phaseBudgetUsd: null,
    remainingRunBudgetUsd: null,
    remainingPhaseBudgetUsd: null,
    runHalted: false,
    warnings: [],
    exceeded: [],
    openBudgetGateIds: [],
  };
}

export function emptyLoopSnapshot(): LoopSnapshot {
  return {
    byAtom: {},
    activeStageCounts: emptyStageCounts(),
    selectedStageFilter: null,
    lastLoopEvent: null,
  };
}

type FoldCost = {
  effectiveCost: number | null;
  providerReportedCost: number | null;
  estimatedCost: number | null;
  source: CostSource;
};

type FoldUsage = {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  reasoningTokens: number;
};

function addCost(target: CostBucket, cost: FoldCost, usage: FoldUsage): void {
  const effective = cost.effectiveCost ?? cost.providerReportedCost;
  if (effective === null) {
    target.unknownCostCount += 1;
  } else {
    target.effectiveUsd += effective;
  }
  if (cost.providerReportedCost !== null) {
    target.providerReportedUsd += cost.providerReportedCost;
  }
  if (cost.estimatedCost !== null) {
    target.estimatedUsd += cost.estimatedCost;
  }
  target.inputTokens += usage.inputTokens;
  target.outputTokens += usage.outputTokens;
  target.cacheReadTokens += usage.cacheReadTokens;
  target.cacheWriteTokens += usage.cacheWriteTokens;
  target.reasoningTokens += usage.reasoningTokens;
}

function costFields(event: RunEvent): FoldCost {
  const cost = objectValue(event.cost);
  const providerReportedCost = numberOrNull(cost.provider_reported_cost);
  const estimatedCost = numberOrNull(cost.estimated_cost);
  const effectiveCost = numberOrNull(cost.effective_cost) ?? numberOrNull(event.cost_usd);
  const source = costSource(cost.source ?? event.source);
  return { effectiveCost, providerReportedCost, estimatedCost, source };
}

function usageFields(event: RunEvent): FoldUsage {
  const usage = objectValue(event.usage);
  return {
    inputTokens: numberOrZero(usage.input_tokens),
    outputTokens: numberOrZero(usage.output_tokens),
    cacheReadTokens: numberOrZero(usage.cache_read_tokens),
    cacheWriteTokens: numberOrZero(usage.cache_write_tokens),
    reasoningTokens: numberOrZero(usage.reasoning_tokens),
  };
}

function bucket(collection: Record<string, CostBucket>, id: string): CostBucket {
  if (!collection[id]) {
    collection[id] = emptyCostBucket();
  }
  return collection[id];
}

function cloneAtoms(source: Record<string, AtomStatus>): Record<string, AtomStatus> {
  return Object.fromEntries(Object.entries(source).map(([id, value]) => [id, { ...value }]));
}

function cloneCostSnapshot(snapshot: CostSnapshot): CostSnapshot {
  return {
    ...snapshot,
    byProvider: cloneBuckets(snapshot.byProvider),
    byModel: cloneBuckets(snapshot.byModel),
    byRole: cloneBuckets(snapshot.byRole),
    byPhase: cloneBuckets(snapshot.byPhase),
    byAtom: cloneBuckets(snapshot.byAtom),
    sourceCounts: { ...snapshot.sourceCounts },
    warnings: [...snapshot.warnings],
    exceeded: [...snapshot.exceeded],
    openBudgetGateIds: [...snapshot.openBudgetGateIds],
  };
}

function cloneLoopSnapshot(snapshot: LoopSnapshot): LoopSnapshot {
  return {
    byAtom: Object.fromEntries(Object.entries(snapshot.byAtom).map(([id, value]) => [
      id,
      {
        ...value,
        artifactRefs: [...value.artifactRefs],
        evidenceRefs: [...value.evidenceRefs],
        memoryRefs: [...value.memoryRefs],
      },
    ])),
    activeStageCounts: { ...snapshot.activeStageCounts },
    selectedStageFilter: snapshot.selectedStageFilter,
    lastLoopEvent: snapshot.lastLoopEvent,
  };
}

function cloneBuckets(source: Record<string, CostBucket>): Record<string, CostBucket> {
  return Object.fromEntries(Object.entries(source).map(([id, value]) => [id, { ...value }]));
}

function emptyAtomLoopStatus(atomId: string): AtomLoopStatus {
  return {
    atomId,
    currentStage: null,
    previousStage: null,
    nextExpectedStage: null,
    repairCount: 0,
    reopenedCount: 0,
    artifactRefs: [],
    evidenceRefs: [],
    memoryRefs: [],
    lastEvent: null,
  };
}

function emptyStageCounts(): Record<LoopStage, number> {
  return {
    discover: 0,
    plan: 0,
    build: 0,
    verify: 0,
    repair: 0,
    review: 0,
    ship: 0,
    learn: 0,
  };
}

function stepId(event: RunEvent): string {
  return key(event.step, key(event.name, key(event.phase, key(event.gate, ""))));
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberOrZero(value: unknown): number {
  return numberOrNull(value) ?? 0;
}

function key(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function timeMs(value: unknown): number | null {
  if (typeof value !== "string") {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function costSource(value: unknown): CostSource {
  if (
    value === "provider_reported" ||
    value === "rate_card_estimate" ||
    value === "local_estimate" ||
    value === "unknown"
  ) {
    return value;
  }
  return "unknown";
}

function loopStage(value: unknown): LoopStage {
  if (
    value === "discover" ||
    value === "plan" ||
    value === "build" ||
    value === "verify" ||
    value === "repair" ||
    value === "review" ||
    value === "ship" ||
    value === "learn"
  ) {
    return value;
  }
  return "plan";
}

function nextLoopStage(stage: LoopStage): LoopStage | null {
  const order: LoopStage[] = ["discover", "plan", "build", "verify", "review", "ship", "learn"];
  if (stage === "repair") {
    return "verify";
  }
  const index = order.indexOf(stage);
  return index >= 0 ? order[index + 1] ?? null : null;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function mergeRefs(current: string[], next: string[]): string[] {
  return [...new Set([...current, ...next])];
}

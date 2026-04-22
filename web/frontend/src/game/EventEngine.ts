import type {
  AtomLoopStatus,
  AtomState,
  AtomStatus,
  CostBucket,
  CostSnapshot,
  CostSource,
  DiscussionEntry,
  DiscussionHighlight,
  EngineSnapshot,
  LoopSnapshot,
  LoopStage,
  MemPalaceStatus,
  NarrativeDigest,
  NarrativeHighlight,
  NextStepPacket,
  OperatorIntentState,
  RunEvent,
  WorkflowStep,
} from "./types.js";
import { isRunEventType } from "./eventTypes.js";

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
  private nextStepPacket: NextStepPacket | null = null;
  private digests: NarrativeDigest[] = [];
  private discussion: DiscussionEntry[] = [];
  private discussionHighlights: DiscussionHighlight[] = [];
  private pendingIntents: Record<string, OperatorIntentState> = {};
  private appliedIntents: Record<string, OperatorIntentState> = {};
  private ignoredIntents: Record<string, OperatorIntentState> = {};
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
    this.nextStepPacket = null;
    this.digests = [];
    this.discussion = [];
    this.discussionHighlights = [];
    this.pendingIntents = {};
    this.appliedIntents = {};
    this.ignoredIntents = {};
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
    this.nextStepPacket = null;
    this.digests = [];
    this.discussion = [];
    this.discussionHighlights = [];
    this.pendingIntents = {};
    this.appliedIntents = {};
    this.ignoredIntents = {};
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
      nextStepPacket: this.nextStepPacket
        ? attachPendingIntents(cloneNextStepPacket(this.nextStepPacket), this.pendingIntents)
        : null,
      digests: this.digests.map(cloneNarrativeDigest),
      latestDigest: this.digests.length > 0 ? cloneNarrativeDigest(this.digests[this.digests.length - 1]) : null,
      discussion: this.discussion.map(cloneDiscussionEntry),
      discussionHighlights: this.discussionHighlights.map(cloneDiscussionHighlight),
      pendingIntents: cloneIntentMap(this.pendingIntents),
      appliedIntents: cloneIntentMap(this.appliedIntents),
      ignoredIntents: cloneIntentMap(this.ignoredIntents),
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
    this.nextStepPacket = null;
    this.digests = [];
    this.discussion = [];
    this.discussionHighlights = [];
    this.pendingIntents = {};
    this.appliedIntents = {};
    this.ignoredIntents = {};
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
    if (!isRunEventType(event.type)) {
      return;
    }
    const type = event.type;
    if (type === "run_started") {
      this.atoms = this.buildIdleAtoms();
      this.cost = emptyCostSnapshot();
      this.loops = emptyLoopSnapshot();
      this.memPalaceStatus = null;
      this.nextStepPacket = null;
      this.digests = [];
      this.discussion = [];
      this.discussionHighlights = [];
      this.pendingIntents = {};
      this.appliedIntents = {};
      this.ignoredIntents = {};
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
    if (type === "memory_status" || type === "memory_refreshed" || type === "memory_search_completed") {
      this.applyMemoryEvent(event);
    }
    if (type === "next_step_packet_created") {
      this.applyNextStepPacket(event);
    }
    if (type === "narrative_digest_created") {
      this.applyNarrativeDigest(event);
    }
    if (type === "discussion_entry_created") {
      this.applyDiscussionEntry(event);
    }
    if (type === "discussion_highlight_created") {
      this.applyDiscussionHighlight(event);
    }
    if (type === "operator_intent") {
      this.applyOperatorIntent(event);
    }
    if (type === "operator_intent_applied") {
      this.applyOperatorIntentTerminal(event, "applied");
    }
    if (type === "operator_intent_ignored") {
      this.applyOperatorIntentTerminal(event, "ignored");
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
      wakeUpHash: typeof event.wake_up_hash === "string" ? event.wake_up_hash : null,
      wakeUpBytes: numberOrNull(event.wake_up_bytes) ?? 0,
      memoryRefs: arrayOfStrings(event.memory_refs),
      artifactRefs: arrayOfStrings(event.artifact_refs),
    };
  }

  private applyNextStepPacket(event: RunEvent): void {
    const packet = objectValue(event.packet);
    const packetId = key(packet.packet_id ?? event.packet_id, "");
    const step = key(packet.step ?? event.step, "");
    if (!packetId || !step) {
      return;
    }
    this.nextStepPacket = {
      packetId,
      step,
      title: key(packet.title ?? event.title, step),
      role: key(packet.role ?? event.role, step),
      objective: key(packet.objective, ""),
      whyNow: key(packet.why_now, ""),
      inputs: Array.isArray(packet.inputs)
        ? packet.inputs.filter((item): item is Record<string, unknown> => (
          Boolean(item) && typeof item === "object" && !Array.isArray(item)
        ))
        : [],
      queuedIntents: Array.isArray(packet.queued_intents)
        ? packet.queued_intents.filter((item): item is Record<string, unknown> => (
          Boolean(item) && typeof item === "object" && !Array.isArray(item)
        ))
        : [],
      contextPreview: arrayOfStrings(packet.context_preview),
      interventionOptions: arrayOfStrings(packet.intervention_options),
      sourceRefs: arrayOfStrings(packet.source_refs ?? event.source_refs),
      memoryRefs: arrayOfStrings(event.memory_refs),
      raw: { ...packet },
    };
  }

  private applyNarrativeDigest(event: RunEvent): void {
    const digest = objectValue(event.digest);
    const digestId = key(digest.digest_id ?? event.digest_id, "");
    if (!digestId) {
      return;
    }
    const next: NarrativeDigest = {
      digestId,
      title: key(digest.title ?? event.title, "Narrative digest"),
      summary: key(digest.summary ?? event.summary, ""),
      highlights: narrativeHighlights(digest.highlights ?? event.highlights),
      risks: arrayOfStrings(digest.risks ?? event.risks),
      openQuestions: arrayOfStrings(digest.open_questions ?? event.open_questions),
      nextStepHint: stringOrNull(digest.next_step_hint ?? event.next_step_hint),
      sourceEventIds: arrayOfStrings(digest.source_event_ids ?? event.source_event_ids),
      artifactRefs: arrayOfStrings(digest.artifact_refs ?? event.artifact_refs),
      window: objectValue(digest.window ?? event.window),
      lastEvent: event,
      raw: { ...digest },
    };
    const index = this.digests.findIndex((item) => item.digestId === digestId);
    if (index >= 0) {
      this.digests[index] = next;
    } else {
      this.digests.push(next);
    }
  }

  private applyDiscussionEntry(event: RunEvent): void {
    const entry = objectValue(event.entry);
    const discussionEntryId = key(entry.discussion_entry_id ?? event.discussion_entry_id, "");
    if (!discussionEntryId) {
      return;
    }
    const next: DiscussionEntry = {
      discussionEntryId,
      speaker: key(entry.speaker ?? event.speaker, "unknown"),
      entryType: key(entry.entry_type ?? event.entry_type, "note"),
      atomId: stringOrNull(entry.atom_id ?? event.atom_id),
      text: key(entry.text ?? event.text, ""),
      sourceRefs: arrayOfStrings(entry.source_refs ?? event.source_refs),
      artifactRefs: arrayOfStrings(entry.artifact_refs ?? event.artifact_refs),
      metadata: objectValue(entry.metadata),
      lastEvent: event,
      raw: { ...entry },
    };
    const index = this.discussion.findIndex((item) => item.discussionEntryId === discussionEntryId);
    if (index >= 0) {
      this.discussion[index] = next;
    } else {
      this.discussion.push(next);
    }
  }

  private applyDiscussionHighlight(event: RunEvent): void {
    const highlight = objectValue(event.highlight);
    const discussionHighlightId = key(highlight.discussion_highlight_id ?? event.discussion_highlight_id, "");
    if (!discussionHighlightId) {
      return;
    }
    const next: DiscussionHighlight = {
      discussionHighlightId,
      highlightType: key(highlight.highlight_type ?? event.highlight_type, "notable"),
      atomId: stringOrNull(highlight.atom_id ?? event.atom_id),
      text: key(highlight.text ?? event.text, ""),
      sourceRefs: arrayOfStrings(highlight.source_refs ?? event.source_refs),
      artifactRefs: arrayOfStrings(highlight.artifact_refs ?? event.artifact_refs),
      lastEvent: event,
      raw: { ...highlight },
    };
    const index = this.discussionHighlights.findIndex((item) => item.discussionHighlightId === discussionHighlightId);
    if (index >= 0) {
      this.discussionHighlights[index] = next;
    } else {
      this.discussionHighlights.push(next);
    }
  }

  private applyOperatorIntent(event: RunEvent): void {
    const clientIntentId = intentClientId(event);
    if (!clientIntentId) {
      return;
    }
    this.pendingIntents[clientIntentId] = {
      clientIntentId,
      intentEventId: stringOrNull(event.intent_event_id) ?? stringOrNull(event.event_id),
      kind: key(event.kind, "intent"),
      atomId: stringOrNull(event.atom_id),
      payload: objectValue(event.payload),
      status: "queued",
      appliedTo: null,
      reason: null,
      step: stringOrNull(event.step),
      artifactRefs: arrayOfStrings(event.artifact_refs),
      sourceRefs: arrayOfStrings(event.source_refs),
      lastEvent: event,
    };
    delete this.appliedIntents[clientIntentId];
    delete this.ignoredIntents[clientIntentId];
  }

  private applyOperatorIntentTerminal(event: RunEvent, status: "applied" | "ignored"): void {
    const clientIntentId = intentClientId(event);
    if (!clientIntentId) {
      return;
    }
    const current =
      this.pendingIntents[clientIntentId] ??
      this.appliedIntents[clientIntentId] ??
      this.ignoredIntents[clientIntentId];
    const next: OperatorIntentState = {
      clientIntentId,
      intentEventId: stringOrNull(event.intent_event_id) ?? current?.intentEventId ?? stringOrNull(event.event_id),
      kind: key(event.kind, current?.kind ?? "intent"),
      atomId: stringOrNull(event.atom_id) ?? current?.atomId ?? null,
      payload: current?.payload ? { ...current.payload } : objectValue(event.payload),
      status,
      appliedTo: status === "applied" ? stringOrNull(event.applied_to) : current?.appliedTo ?? null,
      reason: status === "ignored" ? stringOrNull(event.reason) : current?.reason ?? null,
      step: stringOrNull(event.step) ?? current?.step ?? null,
      artifactRefs: mergeRefs(current?.artifactRefs ?? [], arrayOfStrings(event.artifact_refs)),
      sourceRefs: mergeRefs(current?.sourceRefs ?? [], arrayOfStrings(event.source_refs)),
      lastEvent: event,
    };
    delete this.pendingIntents[clientIntentId];
    if (status === "applied") {
      this.appliedIntents[clientIntentId] = next;
      delete this.ignoredIntents[clientIntentId];
    } else {
      this.ignoredIntents[clientIntentId] = next;
      delete this.appliedIntents[clientIntentId];
    }
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

function cloneNextStepPacket(packet: NextStepPacket): NextStepPacket {
  return {
    ...packet,
    inputs: packet.inputs.map((input) => ({ ...input })),
    queuedIntents: packet.queuedIntents.map((intent) => ({ ...intent })),
    contextPreview: [...packet.contextPreview],
    interventionOptions: [...packet.interventionOptions],
    sourceRefs: [...packet.sourceRefs],
    memoryRefs: [...packet.memoryRefs],
    raw: { ...packet.raw },
  };
}

function cloneNarrativeDigest(digest: NarrativeDigest): NarrativeDigest {
  return {
    ...digest,
    highlights: digest.highlights.map((highlight) => ({
      text: highlight.text,
      sourceRefs: [...highlight.sourceRefs],
    })),
    risks: [...digest.risks],
    openQuestions: [...digest.openQuestions],
    sourceEventIds: [...digest.sourceEventIds],
    artifactRefs: [...digest.artifactRefs],
    window: { ...digest.window },
    lastEvent: digest.lastEvent ? { ...digest.lastEvent } : null,
    raw: { ...digest.raw },
  };
}

function cloneDiscussionEntry(entry: DiscussionEntry): DiscussionEntry {
  return {
    ...entry,
    sourceRefs: [...entry.sourceRefs],
    artifactRefs: [...entry.artifactRefs],
    metadata: { ...entry.metadata },
    lastEvent: entry.lastEvent ? { ...entry.lastEvent } : null,
    raw: { ...entry.raw },
  };
}

function cloneDiscussionHighlight(highlight: DiscussionHighlight): DiscussionHighlight {
  return {
    ...highlight,
    sourceRefs: [...highlight.sourceRefs],
    artifactRefs: [...highlight.artifactRefs],
    lastEvent: highlight.lastEvent ? { ...highlight.lastEvent } : null,
    raw: { ...highlight.raw },
  };
}

function cloneIntentMap(source: Record<string, OperatorIntentState>): Record<string, OperatorIntentState> {
  return Object.fromEntries(Object.entries(source).map(([id, intent]) => [id, cloneIntent(intent)]));
}

function cloneIntent(intent: OperatorIntentState): OperatorIntentState {
  return {
    ...intent,
    payload: { ...intent.payload },
    artifactRefs: [...intent.artifactRefs],
    sourceRefs: [...intent.sourceRefs],
    lastEvent: intent.lastEvent ? { ...intent.lastEvent } : null,
  };
}

function attachPendingIntents(
  packet: NextStepPacket,
  pendingIntents: Record<string, OperatorIntentState>,
): NextStepPacket {
  const seen = new Set(
    packet.queuedIntents
      .map((intent) => key(intent.client_intent_id, ""))
      .filter((clientIntentId) => clientIntentId.length > 0),
  );
  for (const intent of Object.values(pendingIntents)) {
    if (intent.atomId !== null && intent.atomId !== packet.step) {
      continue;
    }
    if (seen.has(intent.clientIntentId)) {
      continue;
    }
    packet.queuedIntents.push({
      client_intent_id: intent.clientIntentId,
      intent_event_id: intent.intentEventId,
      kind: intent.kind,
      atom_id: intent.atomId,
      payload: { ...intent.payload },
      status: intent.status,
      source_refs: [...intent.sourceRefs],
    });
    seen.add(intent.clientIntentId);
  }
  return packet;
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

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function intentClientId(event: RunEvent): string {
  return (
    stringOrNull(event.client_intent_id) ??
    stringOrNull(event.intent_event_id) ??
    stringOrNull(event.event_id) ??
    ""
  );
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

function narrativeHighlights(value: unknown): NarrativeHighlight[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    const highlight = objectValue(item);
    const text = key(highlight.text, "");
    if (!text) {
      return [];
    }
    return [{
      text,
      sourceRefs: arrayOfStrings(highlight.source_refs ?? highlight.sourceRefs),
    }];
  });
}

function mergeRefs(current: string[], next: string[]): string[] {
  return [...new Set([...current, ...next])];
}

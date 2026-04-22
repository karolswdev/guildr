import type { RunEventType } from "./eventTypes.js";

export type RunEvent = Record<string, unknown> & {
  event_id?: string;
  schema_version?: number;
  type?: RunEventType;
  step?: string;
  role?: string;
  model?: string;
  provider_name?: string;
  atom_id?: string;
};

export type AtomState = "idle" | "active" | "done" | "error" | "waiting" | "skipped";
export type LoopStage = "discover" | "plan" | "build" | "verify" | "repair" | "review" | "ship" | "learn";

export type WorkflowStep = {
  id: string;
  title?: string;
  type: string;
  handler: string;
  enabled: boolean;
};

export type AtomStatus = {
  id: string;
  state: AtomState;
  attempt: number;
  startedAt: number | null;
  completedAt: number | null;
  lastEvent: RunEvent | null;
};

export type CostSource = "provider_reported" | "rate_card_estimate" | "local_estimate" | "unknown";
export type CostConfidence = "high" | "medium" | "low" | "none";

export type CostBucket = {
  effectiveUsd: number;
  providerReportedUsd: number;
  estimatedUsd: number;
  unknownCostCount: number;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  reasoningTokens: number;
};

export type CostSnapshot = CostBucket & {
  byProvider: Record<string, CostBucket>;
  byModel: Record<string, CostBucket>;
  byRole: Record<string, CostBucket>;
  byPhase: Record<string, CostBucket>;
  byAtom: Record<string, CostBucket>;
  sourceCounts: Record<CostSource, number>;
  runBudgetUsd: number | null;
  phaseBudgetUsd: number | null;
  remainingRunBudgetUsd: number | null;
  remainingPhaseBudgetUsd: number | null;
  runHalted: boolean;
  warnings: string[];
  exceeded: string[];
  openBudgetGateIds: string[];
};

export type MemPalaceStatus = {
  initialized: boolean;
  wing: string | null;
  cached_wakeup: string | null;
  last_search: string | null;
  wakeUpHash: string | null;
  wakeUpBytes: number;
  memoryRefs: string[];
  artifactRefs: string[];
};

export type NextStepPacket = {
  packetId: string;
  step: string;
  title: string;
  role: string;
  objective: string;
  whyNow: string;
  inputs: Record<string, unknown>[];
  queuedIntents: Record<string, unknown>[];
  contextPreview: string[];
  interventionOptions: string[];
  sourceRefs: string[];
  memoryRefs: string[];
  raw: Record<string, unknown>;
};

export type OperatorIntentStatus = "queued" | "applied" | "ignored";

export type OperatorIntentState = {
  clientIntentId: string;
  intentEventId: string | null;
  kind: string;
  atomId: string | null;
  payload: Record<string, unknown>;
  status: OperatorIntentStatus;
  appliedTo: string | null;
  reason: string | null;
  step: string | null;
  artifactRefs: string[];
  sourceRefs: string[];
  lastEvent: RunEvent | null;
};

export type NarrativeHighlight = {
  text: string;
  sourceRefs: string[];
};

export type NarrativeDigest = {
  digestId: string;
  title: string;
  summary: string;
  highlights: NarrativeHighlight[];
  risks: string[];
  openQuestions: string[];
  nextStepHint: string | null;
  sourceEventIds: string[];
  artifactRefs: string[];
  window: Record<string, unknown>;
  wakeUpHash: string | null;
  memoryRefs: string[];
  lastEvent: RunEvent | null;
  raw: Record<string, unknown>;
};

export type DiscussionEntry = {
  discussionEntryId: string;
  speaker: string;
  entryType: string;
  atomId: string | null;
  text: string;
  sourceRefs: string[];
  artifactRefs: string[];
  metadata: Record<string, unknown>;
  wakeUpHash: string | null;
  memoryRefs: string[];
  lastEvent: RunEvent | null;
  raw: Record<string, unknown>;
};

export type DiscussionHighlight = {
  discussionHighlightId: string;
  highlightType: string;
  atomId: string | null;
  text: string;
  sourceRefs: string[];
  artifactRefs: string[];
  wakeUpHash: string | null;
  memoryRefs: string[];
  lastEvent: RunEvent | null;
  raw: Record<string, unknown>;
};

export type AtomLoopStatus = {
  atomId: string;
  currentStage: LoopStage | null;
  previousStage: LoopStage | null;
  nextExpectedStage: LoopStage | null;
  repairCount: number;
  reopenedCount: number;
  artifactRefs: string[];
  evidenceRefs: string[];
  memoryRefs: string[];
  lastEvent: RunEvent | null;
};

export type LoopSnapshot = {
  byAtom: Record<string, AtomLoopStatus>;
  activeStageCounts: Record<LoopStage, number>;
  selectedStageFilter: LoopStage | null;
  lastLoopEvent: RunEvent | null;
};

export type DemoViewport = {
  name: string | null;
  width: number | null;
  height: number | null;
};

export type DemoArtifact = {
  ref: string;
  kind: string;
  sha256: string;
  bytes: number;
  testStatus: string | null;
  viewport: DemoViewport | null;
  eventId: string | null;
};

export type DemoStatus =
  | "planned"
  | "skipped"
  | "capturing"
  | "captured"
  | "failed"
  | "presented";

export type DemoPlan = {
  demoId: string;
  status: DemoStatus;
  adapter: string;
  confidence: string;
  reason: string;
  taskId: string | null;
  atomId: string | null;
  startCommand: string;
  testCommand: string;
  specPath: string;
  route: string;
  viewports: string[];
  capturePolicy: string[];
  viewport: DemoViewport | null;
  artifacts: DemoArtifact[];
  testStatus: string | null;
  captureError: string | null;
  summaryRef: string | null;
  sourceRefs: string[];
  artifactRefs: string[];
  wakeUpHash: string | null;
  memoryRefs: string[];
  lastEvent: RunEvent | null;
  raw: Record<string, unknown>;
};

export type EngineSnapshot = {
  projectId: string;
  runId: string | null;
  atoms: Record<string, AtomStatus>;
  events: RunEvent[];
  scrubIndex: number;
  isLive: boolean;
  memPalaceStatus: MemPalaceStatus | null;
  nextStepPacket: NextStepPacket | null;
  digests: NarrativeDigest[];
  latestDigest: NarrativeDigest | null;
  discussion: DiscussionEntry[];
  discussionHighlights: DiscussionHighlight[];
  demos: DemoPlan[];
  latestDemo: DemoPlan | null;
  pendingIntents: Record<string, OperatorIntentState>;
  appliedIntents: Record<string, OperatorIntentState>;
  ignoredIntents: Record<string, OperatorIntentState>;
  historyLength: number;
  replayIndex: number;
  live: boolean;
  cost: CostSnapshot;
  loops: LoopSnapshot;
};

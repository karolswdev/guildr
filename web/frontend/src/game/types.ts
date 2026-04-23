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
  rateCardVersions: string[];
  rateCardRefs: string[];
  missingRateCardVersions: string[];
};

export type MemPalaceStatus = {
  available: boolean;
  initialized: boolean;
  wing: string | null;
  roleWings: Record<string, string>;
  costAccounting: Record<string, unknown>;
  cached_wakeup: string | null;
  last_search: string | null;
  wakeUpHash: string | null;
  previousWakeUpHash: string | null;
  hashChanged: boolean | null;
  wakeUpBytes: number;
  memoryRefs: string[];
  artifactRefs: string[];
  error: string | null;
  lastEvent: RunEvent | null;
};

export type MemoryEventRecord = {
  type: string;
  eventId: string | null;
  available: boolean;
  initialized: boolean;
  wing: string | null;
  roleWings: Record<string, string>;
  costAccounting: Record<string, unknown>;
  cachedWakeup: string | null;
  lastSearch: string | null;
  wakeUpHash: string | null;
  previousWakeUpHash: string | null;
  hashChanged: boolean | null;
  wakeUpBytes: number;
  memoryRefs: string[];
  artifactRefs: string[];
  error: string | null;
  query: string | null;
  room: string | null;
  results: number | null;
  ts: number | null;
  lastEvent: RunEvent | null;
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
  acceptanceCriteria: string[];
  evidenceRequired: string[];
  demoRequested: boolean;
  demoCompatibility: string | null;
  demoAdapter: string | null;
  demoConfidence: string | null;
  demoReason: string | null;
  sourceRefs: string[];
  memoryRefs: string[];
  raw: Record<string, unknown>;
};

export type FunctionalMiniSprint = {
  miniSprintId: string;
  title: string;
  objective: string;
  scopeRefs: string[];
  acceptanceCriteria: string[];
  evidenceRequired: string[];
  demoRequested: boolean;
  demoCompatibility: string | null;
  sourceRefs: string[];
  steps: FunctionalMiniSprintStep[];
  acceptance: FunctionalAcceptance | null;
  lastEvent: RunEvent | null;
};

export type FunctionalMiniSprintStep = {
  stepId: string;
  stepKind: string;
  status: string;
  artifactRefs: string[];
  evidenceRefs: string[];
  sourceEventIds: string[];
  sourceRefs: string[];
  lastEvent: RunEvent | null;
};

export type FunctionalAcceptance = {
  passed: boolean;
  criteriaResults: Record<string, unknown>[];
  blockingFindings: string[];
  reviewArtifactRef: string | null;
  evidenceRefs: string[];
  recommendedActions: string[];
  sourceRefs: string[];
  lastEvent: RunEvent | null;
};

export type FunctionalSnapshot = {
  currentMiniSprint: FunctionalMiniSprint | null;
  byId: Record<string, FunctionalMiniSprint>;
  acceptance: FunctionalAcceptance | null;
  evidenceRefs: string[];
};

export type HeroPresence = {
  heroId: string;
  name: string;
  status: string;
  termMode: string | null;
  targetStep: string | null;
  targetDeliverable: string | null;
  consultationTrigger: string | null;
  retiredReason: string | null;
  sourceRefs: string[];
  lastEvent: RunEvent | null;
};

export type HeroSnapshot = {
  byId: Record<string, HeroPresence>;
  active: HeroPresence[];
  retired: HeroPresence[];
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
  demoCompatibility: string | null;
  demoRequested: boolean;
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

export type ArtifactPreviewExcerptKind =
  | "text_head"
  | "text_tail"
  | "binary_placeholder";

export type ArtifactPreview = {
  eventId: string | null;
  artifactRef: string;
  producingAtomId: string | null;
  projectId: string;
  hash: string;
  bytes: number;
  mime: string;
  excerpt: string;
  excerptKind: ArtifactPreviewExcerptKind;
  truncated: boolean;
  triggerEventId: string | null;
  sourceRefs: string[];
  wakeUpHash: string | null;
  memoryRefs: string[];
  ts: number | null;
};

export type EngineSnapshot = {
  projectId: string;
  runId: string | null;
  atoms: Record<string, AtomStatus>;
  events: RunEvent[];
  scrubIndex: number;
  isLive: boolean;
  memPalaceStatus: MemPalaceStatus | null;
  memoryEvents: MemoryEventRecord[];
  nextStepPacket: NextStepPacket | null;
  functional: FunctionalSnapshot;
  heroes: HeroSnapshot;
  digests: NarrativeDigest[];
  latestDigest: NarrativeDigest | null;
  discussion: DiscussionEntry[];
  discussionHighlights: DiscussionHighlight[];
  demos: DemoPlan[];
  latestDemo: DemoPlan | null;
  previews: ArtifactPreview[];
  latestPreview: ArtifactPreview | null;
  pendingIntents: Record<string, OperatorIntentState>;
  appliedIntents: Record<string, OperatorIntentState>;
  ignoredIntents: Record<string, OperatorIntentState>;
  historyLength: number;
  replayIndex: number;
  live: boolean;
  cost: CostSnapshot;
  loops: LoopSnapshot;
};

export const RUN_EVENT_TYPES = [
  "run_started",
  "run_complete",
  "run_error",
  "phase_start",
  "phase_done",
  "phase_retry",
  "phase_error",
  "checkpoint",
  "gate_opened",
  "gate_decided",
  "usage_recorded",
  "provider_call_error",
  "budget_warning",
  "budget_exceeded",
  "budget_gate_opened",
  "budget_gate_decided",
  "loop_entered",
  "loop_progressed",
  "loop_blocked",
  "loop_repaired",
  "loop_completed",
  "loop_reopened",
  "memory_status",
  "memory_refreshed",
  "memory_search_completed",
  "memory_error",
  "next_step_packet_created",
  "narrative_digest_created",
  "discussion_entry_created",
  "discussion_highlight_created",
  "operator_intent",
  "operator_intent_applied",
  "operator_intent_ignored",
  "narrator_sidecar_requested",
  "narrator_sidecar_skipped",
  "narrator_sidecar_fallback",
  "narrator_sidecar_completed",
  "atom_started",
  "atom_completed",
  "demo_planned",
  "demo_skipped",
] as const;

export type RunEventType = typeof RUN_EVENT_TYPES[number];

const RUN_EVENT_TYPE_SET = new Set<string>(RUN_EVENT_TYPES);

export function isRunEventType(value: unknown): value is RunEventType {
  return typeof value === "string" && RUN_EVENT_TYPE_SET.has(value);
}

# Error Handling & Retry Strategy

## Error categories

| Category                 | Example                                       | Retry strategy                                                                                       |
|--------------------------|-----------------------------------------------|-------------------------------------------------------------------------------------------------------|
| **Content failure**      | sprint-plan missing Evidence sections         | Retry with targeted corrective feedback (see `phases/phase-3-architect.md`)                           |
| **Thinking truncation**  | `finish_reason=length`, `content` empty       | Bump `max_tokens` (2× up to 32K), OR trim prompt, then retry                                          |
| **Malformed JSON**       | Self-eval returned invalid JSON               | Re-prompt with "your output was not valid JSON, return only the object". Fallback: regex-extract outermost `{...}`. |
| **Server 503/504**       | Queue full, server restarting                 | Exponential backoff 1→2→4→8s, max 4 retries                                                           |
| **Connection refused**   | llama-server down                             | Do not retry. Pause run, surface to PWA.                                                              |
| **Architect exhaustion** | 3 self-eval passes all failed                 | Escalate to human with all drafts + failure reasons                                                   |
| **Validator failure**    | Phase output doesn't pass gate                | Retry phase with failure context, max `config.max_retries`                                           |
| **Permission denied**    | Can't write file                              | Hard fail. Human intervention required.                                                               |
| **Unclean working tree** | `git diff-index --quiet HEAD --` non-zero at task start | Hard fail. Do NOT auto-stash/discard — unexpected state means human investigation. Surface to PWA. |

## Failure-context injection (content-failure retries)

When a phase validator fails, the retry prompt gets:

```
Previous attempt failed because: <specific failure from validator>

Please revise <output file> addressing ONLY these failures. Keep all
passing sections unchanged.
```

Specificity matters — "please try again" produces the same garbage.
"`Task 2` acceptance criterion uses vague language ('fast API'); specify
a latency threshold" produces a fix.

## Max retry budgets

| Scope                     | Default | Config                     |
|---------------------------|---------|----------------------------|
| Per-phase retries         | 3       | `max_retries`              |
| Architect self-eval passes| 3       | `architect_max_passes`     |
| JSON re-parse attempts    | 2       | hardcoded                  |
| Total orchestrator iterations | 20  | `max_total_iterations`     |

When `max_total_iterations` is hit, orchestrator halts and reports —
something is structurally wrong, not transient.

## Session preservation on failure

Failed sessions export to
`.orchestrator/sessions/<phase>-<attempt>.json`. Kept for human
inspection. Cleanup on success is optional (keep for audit trail).

# M12 — Release Hardening And Quality Review

## Purpose

Close out the Council Engine target: run the full cross-phase quality-gate sweep, verify acceptance criteria (SRS §15), harden perf/security/portability (SRS §13), and ship a Mac-first, LAN-only, vendored release that a non-developer can operate on mobile.

## Why this phase exists

Earlier mini-phases can each be honest in isolation and still compose into an unshippable product. M12 is the final assembly: no dashboard relapse, no unsourced claims, no secret leakage, no mobile breakage, no cost mystery, no hidden filesystem assumptions.

## Required context files

- `docs/srs-council-engine.md` §13, §15, §17
- `docs/implementation-roadmap.md`
- `docs/design-review-protocol.md`
- `QUALITY_GATES.md` (all)
- `EXECUTION_CHECKLIST.md`

## Implementation surface

- Release checklist artifacts only — no new runtime primitives land here.
- `project-management/evidence/M12/` for captures and bundle references.
- Perf / security / accessibility test additions where gaps exist.
- README + install.sh + record_live_demo.sh validation.

## Tasks

- [ ] Walk every SRS §15 acceptance criterion against the running system. Mark pass / fail / deferred with links.
- [ ] Cross-phase gate sweep: run every gate in `QUALITY_GATES.md` G1–G10 against current main.
- [ ] Perf: PWA interaction < 100 ms local, event update < 1 s, event history ≥ 5,000 events per project loadable without jank.
- [ ] Reliability: refresh survival, server-restart survival, memory packet reuse — each evidenced with a test or a logged manual walk.
- [ ] Security review: LAN-only default, no secret logging, advisor keys only via env, project path traversal, no uncontrolled public exposure. Run `/security-review` skill against the pending changes.
- [ ] Portability: Mac-first, `uv`-managed env, vendored assets, no hotlinked upstream CDNs. `install.sh` smoke.
- [ ] Observability: phase logs, events, memory status artifacts, advisor outputs, usage events — sample a real run and confirm presence of each.
- [ ] Design review protocol run for any architectural change since M01.
- [ ] DIRECTION_GUARDRAILS six-capture review on iPhone portrait, desktop wide, selected atom, active flow, blocked/repair state, deferred-model loaded, no-overlap state.
- [ ] Release notes in `docs/release-notes.md` with the acceptance-criteria matrix embedded.
- [ ] Update `../STATUS.md` Phase Board to reflect mini-phases (or keep as separate track with links).

## Quality gates

- [ ] Every G1–G10 gate in `QUALITY_GATES.md` is checked for the release candidate.
- [ ] All 13 SRS §15 acceptance criteria evidenced.
- [ ] No open P0 in pending PRs / issues.
- [ ] `git diff --check` clean; `uv run pytest -q` full suite passing; `./web/frontend/build.sh` clean.

## Evidence commands / checks

```bash
uv run pytest -q
./web/frontend/build.sh
# security review (skill)
# manual captures into project-management/evidence/M12/
git diff --check
```

## Done means

- [ ] All SRS §15 acceptance criteria green with linked evidence.
- [ ] All cross-phase quality gates green.
- [ ] Six direction-guardrail captures present for the release build.
- [ ] A non-developer can open the PWA on mobile and answer the DIRECTION_GUARDRAILS quality questions without reading a table.
- [ ] Release notes + evidence matrix committed (on operator approval).

## Known traps

- Declaring a phase done based on unit tests without running the PWA end-to-end — the dashboard-relapse regression is invisible to pytest.
- Shipping with a live-endpoint-only test marked `@pytest.mark.live` that silently skips in CI. Confirm coverage before release.
- Leaving scratch artifacts (temp projects, logs) under `project-management/evidence/` that leak machine paths. Clean before commit.

## Handoff notes

- This phase does not add code. If you're tempted to add a new abstraction here, that abstraction belongs in an earlier mini-phase.
- On release, update `../AGENT_ONBOARDING.md` glossary for any primitive introduced across the pack.
- Tag release only after the user approves the evidence matrix.

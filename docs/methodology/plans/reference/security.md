# Security

## Posture

Single-user, LAN-only, trust-the-box. This is a power-user tool, not a
multi-tenant service. Threat model: "random device on home Wi-Fi pokes
at the port" and "typo in a URL exposes it to the internet" — not
nation-state attackers.

## LAN-only middleware (mandatory)

The PWA backend (FastAPI) MUST bind to `0.0.0.0` (so LAN devices can
reach it) but reject any request whose source IP isn't in RFC1918
private ranges:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- Plus `127.0.0.0/8` for loopback.

Override only via explicit env var: `ORCHESTRATOR_EXPOSE_PUBLIC=1`. Log
a WARNING at startup when overridden. **No CLI flag** — env var is
deliberately a speed bump.

Implementation: FastAPI middleware that checks `request.client.host`
against the allowlist and returns 403 otherwise. Place it before any
route.

## Why this matters more than usual

The llama-server upstream has **no authentication**. It's bound to
`0.0.0.0:8080` on the inference host. Anything with LAN access can send
arbitrary prompts. The orchestrator PWA sits in front of the same LAN
with full filesystem write access on whichever box it runs on. If the
PWA is accidentally exposed to the internet, a stranger can drive your
box into writing arbitrary code to arbitrary paths.

The LAN-only middleware is the one line of defense. Don't weaken it.

## Secrets

- No API keys in prompts. `LLAMA_API_KEY` is a non-empty placeholder
  (the server ignores it).
- Real secrets (deployment credentials, etc.) live in `.env` and are
  **NEVER** sent to the model. The Deployer reads env at runtime and
  templates deploy scripts; it does not paste secrets into prompts.

## Permission scope

Role sessions use `--dangerously-skip-permissions` so they can write
files autonomously. Acceptable because:

- The orchestrator runs on the user's own box.
- Each session is scoped to the project directory.
- Outputs are gated (Architect → human approval → Coder).

**Do not** propagate `--dangerously-skip-permissions` to any session
that runs outside the project directory.

## Human gates as security controls

`approve_sprint_plan` and `approve_review` gates are not just UX — they
are where a human validates the autonomous pipeline hasn't gone off the
rails. Gates must:

- Show the exact artifact being approved (full `sprint-plan.md` or
  `REVIEW.md`).
- **Default to reject on timeout** — no approval = no proceed.
- Log the decision with timestamp.

## Audit trail

Every role session exports its transcript to
`.orchestrator/sessions/<phase>-<attempt>.json`. Keep them. It's the
only way to reconstruct what the model saw and decided.

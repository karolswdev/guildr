/**
 * Progress view — live run console, controls, and durable agent logs.
 */

type PhaseSummary = {
  phase: string;
  exists: boolean;
  count: number;
  entries: Array<Record<string, unknown>>;
  last_event: Record<string, unknown> | null;
};

type LogResponse = {
  project_id: string;
  phases: PhaseSummary[];
};

type ResumeStep = "architect" | "approve_sprint_plan" | "implementation" | "testing" | "review" | "approve_review" | "deployment";

const RUN_STEPS: ResumeStep[] = [
  "architect",
  "approve_sprint_plan",
  "implementation",
  "testing",
  "review",
  "approve_review",
  "deployment",
];

export function renderProgress(container: Element, navigate: (route: string) => void, projectId: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <button
        onclick="navigate('#project/${projectId}')"
        style="background: none; border: none; color: #4fc3f7;
               font-size: 14px; cursor: pointer; padding: 8px 0;"
      >
        ← Back
      </button>
      <h1 style="font-size: 18px; margin-top: 8px;">Run Console</h1>
    </header>
    <main style="padding: 16px; display: grid; gap: 16px;">
      <section style="padding: 12px; background: #141414; border: 1px solid #2d2d2d; border-radius: 8px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">
          <div id="phase-dot" style="width: 16px; height: 16px; border-radius: 50%; background: #555;"></div>
          <span id="phase-name" style="font-size: 16px; font-weight: 600;">Loading...</span>
        </div>
        <div style="display: flex; gap: 4px;">
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; font-size: 13px;">
          <span style="color: #888;">Tokens/sec <span id="tok-s" style="color: #4fc3f7;">—</span></span>
          <span style="color: #888;">VRAM <span id="vram" style="color: #4fc3f7;">—</span></span>
        </div>
      </section>

      <section style="padding: 12px; background: #141414; border: 1px solid #2d2d2d; border-radius: 8px;">
        <div style="font-size: 14px; font-weight: 600; margin-bottom: 12px;">Run Control</div>
        <label style="display: block; font-size: 12px; color: #888; margin-bottom: 6px;">Resume From</label>
        <select id="resume-step" style="width: 100%; padding: 10px; margin-bottom: 10px; background: #0b0b0b; color: #f1f1f1; border: 1px solid #333; border-radius: 6px;">
          ${RUN_STEPS.map((step) => `<option value="${step}">${step}</option>`).join("")}
        </select>
        <label style="display: block; font-size: 12px; color: #888; margin-bottom: 6px;">Instruction</label>
        <textarea
          id="operator-instruction"
          rows="5"
          placeholder="Inject a directive for the next relevant model call."
          style="width: 100%; padding: 10px; margin-bottom: 10px; background: #0b0b0b; color: #f1f1f1; border: 1px solid #333; border-radius: 6px; resize: vertical; box-sizing: border-box;"
        ></textarea>
        <label style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 13px; color: #cfcfcf;">
          <input id="compact-before-resume" type="checkbox" />
          Compact context before resume
        </label>
        <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px;">
          <button id="btn-inject" style="padding: 12px; background: #0f3460; color: white; border: none; border-radius: 6px; cursor: pointer;">Inject</button>
          <button id="btn-compact" style="padding: 12px; background: #184b35; color: white; border: none; border-radius: 6px; cursor: pointer;">Compact</button>
          <button id="btn-resume" style="padding: 12px; background: #4fc3f7; color: #0a0a0a; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Resume</button>
        </div>
        <div id="control-status" style="margin-top: 10px; min-height: 20px; font-size: 13px; color: #888;"></div>
      </section>

      <section style="padding: 12px; background: #141414; border: 1px solid #2d2d2d; border-radius: 8px;">
        <div style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Live Event Log</div>
        <div
          id="event-log"
          style="max-height: 280px; overflow-y: auto; background: #0a0a0a;
                 border-radius: 6px; padding: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                 font-size: 13px; line-height: 1.6;"
        >
          <div style="color: #888;">Connecting to event stream...</div>
        </div>
      </section>

      <section style="padding: 12px; background: #141414; border: 1px solid #2d2d2d; border-radius: 8px;">
        <div style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Agent Logs</div>
        <div id="phase-logs" style="display: grid; gap: 10px;">
          <div style="color: #888;">Loading durable logs...</div>
        </div>
      </section>
    </main>
  `;

  const eventLog = container.querySelector("#event-log") as HTMLDivElement;
  const phaseLogs = container.querySelector("#phase-logs") as HTMLDivElement;
  const phaseDot = container.querySelector("#phase-dot") as HTMLDivElement;
  const phaseName = container.querySelector("#phase-name") as HTMLSpanElement;
  const tokS = container.querySelector("#tok-s") as HTMLSpanElement;
  const vram = container.querySelector("#vram") as HTMLSpanElement;
  const phaseSteps = container.querySelectorAll(".phase-step");
  const resumeStep = container.querySelector("#resume-step") as HTMLSelectElement;
  const instructionInput = container.querySelector("#operator-instruction") as HTMLTextAreaElement;
  const compactCheckbox = container.querySelector("#compact-before-resume") as HTMLInputElement;
  const controlStatus = container.querySelector("#control-status") as HTMLDivElement;
  const btnInject = container.querySelector("#btn-inject") as HTMLButtonElement;
  const btnCompact = container.querySelector("#btn-compact") as HTMLButtonElement;
  const btnResume = container.querySelector("#btn-resume") as HTMLButtonElement;

  const phases = ["architect", "implementation", "testing", "review", "deployment"];
  let evtSource: EventSource | null = null;
  let refreshTimer: number | null = null;

  function setStatus(message: string, isError = false): void {
    controlStatus.textContent = message;
    controlStatus.style.color = isError ? "#e74c3c" : "#888";
  }

  function setBusy(button: HTMLButtonElement, busy: boolean, label: string): void {
    button.disabled = busy;
    button.textContent = label;
    button.style.opacity = busy ? "0.7" : "1";
  }

  function appendEvent(type: string, message: string): void {
    const div = document.createElement("div");
    const timestamp = new Date().toLocaleTimeString();

    let color = "#888";
    if (type.includes("error") || type.includes("fail")) color = "#e74c3c";
    else if (type.includes("done") || type.includes("complete") || type.includes("approved")) color = "#2ecc71";
    else if (type.includes("gate")) color = "#f39c12";
    else if (type.includes("phase")) color = "#4fc3f7";

    div.style.color = color;
    div.textContent = `[${timestamp}] ${message}`;
    eventLog.appendChild(div);
    eventLog.scrollTop = eventLog.scrollHeight;

    while (eventLog.children.length > 200) {
      eventLog.removeChild(eventLog.firstChild!);
    }
  }

  function describeEvent(data: Record<string, unknown>): string {
    const t = String(data.type ?? "event");
    const name = data.name ?? data.phase ?? "";
    const attempt = data.attempt;
    const error = data.error;
    if (t === "run_started") {
      const startAt = data.start_at ? ` from ${data.start_at}` : "";
      return `▶ run started (${data.dry_run ? "dry-run" : "live"}${startAt})`;
    }
    if (t === "run_complete") return "✔ run complete";
    if (t === "run_error") return `✖ ${error ?? "run failed"}`;
    if (t === "phase_start") return `→ ${name}${attempt ? ` (retry ${attempt})` : ""}`;
    if (t === "phase_done") return `✔ ${name}`;
    if (t === "phase_retry") return `↻ ${name} retry ${attempt ?? "?"}`;
    if (t === "phase_error") return `✖ ${name}: ${error ?? "error"}`;
    if (t === "gate_opened") return `⏸ gate: ${data.gate ?? ""}`;
    if (t === "gate_decided") return `${data.decision === "approved" ? "✔" : "✖"} gate: ${data.gate ?? ""}`;
    return data.message ? String(data.message) : t;
  }

  function updatePhase(phase: string): void {
    phaseName.textContent = phase.charAt(0).toUpperCase() + phase.slice(1);
    const idx = phases.indexOf(phase);
    phaseDot.style.background = idx >= 0 ? "#4fc3f7" : "#555";
    for (let i = 0; i < phaseSteps.length; i++) {
      const step = phaseSteps[i] as HTMLDivElement;
      step.style.background = i <= idx ? "#4fc3f7" : "#333";
    }
  }

  async function apiGet<T>(url: string): Promise<T> {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
    return resp.json() as Promise<T>;
  }

  async function apiPost<T>(url: string, body: unknown): Promise<T> {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      throw new Error(`API ${resp.status}: ${resp.statusText}`);
    }
    return resp.json() as Promise<T>;
  }

  async function refreshLogs(): Promise<void> {
    try {
      const data = await apiGet<LogResponse>(`/api/projects/${projectId}/logs?limit=6`);
      phaseLogs.innerHTML = "";
      for (const phase of data.phases) {
        const block = document.createElement("section");
        block.style.cssText = "padding: 10px; background: #0b0b0b; border: 1px solid #242424; border-radius: 6px;";
        const entries = phase.entries.length === 0
          ? `<div style="color: #666; font-size: 12px;">No entries yet</div>`
          : phase.entries.map((entry) => {
            const level = typeof entry.level === "string" ? entry.level : "INFO";
            const message = typeof entry.message === "string" ? entry.message : (typeof entry.event === "string" ? entry.event : "event");
            const ts = typeof entry.ts === "string" ? new Date(entry.ts).toLocaleTimeString() : "now";
            const color = level === "ERROR" ? "#e74c3c" : level === "WARNING" ? "#f39c12" : "#cfcfcf";
            return `<div style="font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; color: ${color}; line-height: 1.5;">[${escapeHtml(ts)}] ${escapeHtml(message)}</div>`;
          }).join("");

        block.innerHTML = `
          <div style="display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px;">
            <strong style="font-size: 13px;">${escapeHtml(phase.phase)}</strong>
            <span style="font-size: 12px; color: #888;">${phase.count} events</span>
          </div>
          ${entries}
        `;
        phaseLogs.appendChild(block);
      }
    } catch (err: unknown) {
      phaseLogs.innerHTML = `<div style="color: #e74c3c; font-size: 13px;">${escapeHtml(err instanceof Error ? err.message : "Failed to load logs")}</div>`;
    }
  }

  function connectStream(): void {
    evtSource?.close();
    evtSource = new EventSource(`/api/projects/${projectId}/stream`);

    evtSource.onmessage = (event: MessageEvent): void => {
      if (event.data.startsWith(":")) return;

      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        appendEvent("parse-error", "Failed to parse event stream payload");
        return;
      }

      const eventType = (data.type as string) || "unknown";
      const phase = (data.name as string) || (data.phase as string) || "";
      appendEvent(eventType, describeEvent(data));

      if (phase && phases.includes(phase)) {
        updatePhase(phase);
      }
      if (data.tok_s !== undefined) {
        tokS.textContent = typeof data.tok_s === "number" ? `${data.tok_s.toFixed(1)}` : String(data.tok_s);
      }
      if (data.vram !== undefined) {
        vram.textContent = typeof data.vram === "number" ? `${data.vram.toFixed(0)} MB` : String(data.vram);
      }
    };

    evtSource.onerror = (): void => {
      appendEvent("error", "Connection lost. Reconnecting...");
      evtSource?.close();
      window.setTimeout(connectStream, 3000);
    };
  }

  btnInject.addEventListener("click", async () => {
    const instruction = instructionInput.value.trim();
    if (!instruction) {
      setStatus("Enter an instruction first.", true);
      return;
    }
    setBusy(btnInject, true, "Injecting...");
    try {
      await apiPost(`/api/projects/${projectId}/control/instructions`, {
        phase: null,
        instruction,
      });
      instructionInput.value = "";
      setStatus("Instruction queued for upcoming model calls.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Inject failed", true);
    } finally {
      setBusy(btnInject, false, "Inject");
    }
  });

  btnCompact.addEventListener("click", async () => {
    setBusy(btnCompact, true, "Compacting...");
    try {
      await apiPost(`/api/projects/${projectId}/control/compact`, { max_chars: 18000 });
      setStatus("Compact context refreshed.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Compact failed", true);
    } finally {
      setBusy(btnCompact, false, "Compact");
    }
  });

  btnResume.addEventListener("click", async () => {
    setBusy(btnResume, true, "Resuming...");
    try {
      const payload = {
        start_at: resumeStep.value as ResumeStep,
        instruction: instructionInput.value.trim() || null,
        compact_context: compactCheckbox.checked,
        max_chars: 18000,
      };
      const result = await apiPost<{ started: boolean; start_at: string }>(
        `/api/projects/${projectId}/control/resume`,
        payload,
      );
      instructionInput.value = "";
      setStatus(result.started ? `Run resumed from ${result.start_at}.` : "A run is already active.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Resume failed", true);
    } finally {
      setBusy(btnResume, false, "Resume");
    }
  });

  connectStream();
  refreshLogs();
  refreshTimer = window.setInterval(() => {
    void refreshLogs();
  }, 4000);

  window.addEventListener("hashchange", () => {
    evtSource?.close();
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
    }
  }, { once: true });
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

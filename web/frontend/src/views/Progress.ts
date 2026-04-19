/**
 * Progress view — live event log, phase indicator, and metrics gauge.
 */

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
      <h1 style="font-size: 18px; margin-top: 8px;">Progress</h1>
    </header>
    <main style="padding: 16px;">
      <!-- Phase indicator -->
      <div id="phase-indicator" style="margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
          <div id="phase-dot" style="width: 16px; height: 16px; border-radius: 50%; background: #555;"></div>
          <span id="phase-name" style="font-size: 16px; font-weight: 600;">Loading...</span>
        </div>
        <div style="display: flex; gap: 4px; margin-top: 8px;">
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
          <div class="phase-step" style="flex: 1; height: 6px; background: #333; border-radius: 3px;"></div>
        </div>
      </div>

      <!-- Metrics gauge -->
      <div id="metrics-gauge" style="margin-bottom: 24px; padding: 12px; background: #16213e; border-radius: 8px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
          <span style="font-size: 13px; color: #888;">Tokens/sec</span>
          <span id="tok-s" style="font-size: 14px; color: #4fc3f7;">—</span>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="font-size: 13px; color: #888;">VRAM</span>
          <span id="vram" style="font-size: 14px; color: #4fc3f7;">—</span>
        </div>
      </div>

      <!-- Event log -->
      <div style="margin-bottom: 12px; font-size: 14px; font-weight: 600;">Event Log</div>
      <div
        id="event-log"
        style="max-height: 400px; overflow-y: auto; background: #0a0a0a;
               border-radius: 8px; padding: 12px; font-family: monospace;
               font-size: 13px; line-height: 1.6;"
      >
        <div style="color: #888;">Connecting to event stream...</div>
      </div>
    </main>
  `;

  const eventLog = container.querySelector("#event-log") as HTMLDivElement;
  const phaseDot = container.querySelector("#phase-dot") as HTMLDivElement;
  const phaseName = container.querySelector("#phase-name") as HTMLSpanElement;
  const tokS = container.querySelector("#tok-s") as HTMLSpanElement;
  const vram = container.querySelector("#vram") as HTMLSpanElement;
  const phaseSteps = container.querySelectorAll(".phase-step");

  const phases = ["architect", "implementation", "testing", "review", "deployment"];
  let eventCount = 0;

  // -- SSE connection --------------------------------------------------------

  let abortCtrl: AbortController | null = null;

  function connectStream(): void {
    abortCtrl?.abort();
    abortCtrl = new AbortController();

    const url = `/api/projects/${projectId}/stream`;
    const evtSource = new EventSource(url);

    evtSource.onmessage = (event: MessageEvent): void => {
      if (event.data.startsWith(":")) return; // skip comments/keepalive

      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        appendEvent("parse-error", "Failed to parse event: " + event.data.slice(0, 80));
        return;
      }

      const eventType = (data.type as string) || "unknown";
      const phase = (data.phase as string) || "";
      const message = (data.message as string) || (data.event as string) || "";

      appendEvent(eventType, message);

      // Update phase indicator
      if (phase) {
        updatePhase(phase);
      }

      // Update metrics if present
      if (data.tok_s !== undefined) {
        tokS.textContent = typeof data.tok_s === "number" ? `${data.tok_s.toFixed(1)}` : String(data.tok_s);
      }
      if (data.vram !== undefined) {
        vram.textContent = typeof data.vram === "number" ? `${data.vram.toFixed(0)} MB` : String(data.vram);
      }
    };

    evtSource.onerror = (): void => {
      appendEvent("error", "Connection lost. Reconnecting...");
      evtSource.close();
      // Reconnect after delay
      setTimeout(connectStream, 3000);
    };
  }

  // -- helpers ----------------------------------------------------------------

  function appendEvent(type: string, message: string): void {
    eventCount++;
    const div = document.createElement("div");
    const timestamp = new Date().toLocaleTimeString();

    let color = "#888";
    if (type.includes("error") || type.includes("fail")) color = "#e74c3c";
    else if (type.includes("success") || type.includes("pass") || type.includes("approve")) color = "#2ecc71";
    else if (type.includes("gate")) color = "#f39c12";
    else if (type.includes("phase")) color = "#4fc3f7";

    div.style.color = color;
    div.textContent = `[${timestamp}] ${message}`;
    eventLog.appendChild(div);
    eventLog.scrollTop = eventLog.scrollHeight;

    // Limit log size
    while (eventLog.children.length > 200) {
      eventLog.removeChild(eventLog.firstChild!);
    }
  }

  function updatePhase(phase: string): void {
    if (!phaseName) return;
    phaseName.textContent = phase.charAt(0).toUpperCase() + phase.slice(1);

    const idx = phases.indexOf(phase);
    if (idx >= 0) {
      phaseDot.style.background = "#4fc3f7";
      for (let i = 0; i < phaseSteps.length; i++) {
        const step = phaseSteps[i] as HTMLDivElement;
        if (i <= idx) {
          step.style.background = "#4fc3f7";
        } else {
          step.style.background = "#333";
        }
      }
    }
  }

  // -- start ------------------------------------------------------------------

  connectStream();

  // Cleanup on navigation away
  window.addEventListener("hashchange", () => {
    abortCtrl?.abort();
    evtSource?.close();
  }, { once: true });
}

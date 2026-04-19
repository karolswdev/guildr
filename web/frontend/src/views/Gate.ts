/**
 * Gate view — display artifact for human approval, approve/reject with reason.
 */

export function renderGate(container: Element, navigate: (route: string) => void, projectId: string, gateName: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <button
        onclick="navigate('#project/${projectId}')"
        style="background: none; border: none; color: #4fc3f7;
               font-size: 14px; cursor: pointer; padding: 8px 0;"
      >
        ← Back
      </button>
      <h1 style="font-size: 18px; margin-top: 8px;">Gate: ${escapeHtml(gateName)}</h1>
    </header>
    <main style="padding: 16px;">
      <!-- Status banner -->
      <div id="gate-status" style="margin-bottom: 16px; padding: 12px; border-radius: 8px; text-align: center; font-weight: 600; display: none;"></div>

      <!-- Artifact display -->
      <div style="margin-bottom: 24px;">
        <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px;">Artifact</div>
        <div
          id="gate-artifact"
          style="background: #16213e; padding: 16px; border-radius: 8px;
                 overflow-x: auto; font-size: 14px; line-height: 1.6;
                 white-space: pre-wrap; max-height: 400px; overflow-y: auto;"
        >
          <span style="color: #888;">Loading artifact...</span>
        </div>
      </div>

      <!-- Decision form (hidden when already decided) -->
      <div id="gate-decision" style="display: none;">
        <div style="font-size: 14px; font-weight: 600; margin-bottom: 12px;">Your Decision</div>

        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
          <button
            id="approve-btn"
            class="tap-target"
            style="flex: 1; padding: 16px; background: #2ecc71; color: white;
                   border: none; border-radius: 8px; font-size: 18px;
                   font-weight: 600; cursor: pointer;"
          >
            Approve
          </button>
          <button
            id="reject-btn"
            class="tap-target"
            style="flex: 1; padding: 16px; background: #e74c3c; color: white;
                   border: none; border-radius: 8px; font-size: 18px;
                   font-weight: 600; cursor: pointer;"
          >
            Reject
          </button>
        </div>

        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 8px; font-size: 14px; font-weight: 600;">
            Reason (optional)
          </label>
          <textarea
            id="gate-reason"
            rows="4"
            placeholder="Why are you approving or rejecting this?"
            style="width: 100%; padding: 12px; background: #16213e;
                   border: 1px solid #333; border-radius: 8px;
                   color: white; font-size: 16px; resize: vertical;"
          ></textarea>
        </div>

        <div id="gate-error" style="color: #e74c3c; display: none; font-size: 14px;"></div>
      </div>
    </main>
  `;

  const statusEl = container.querySelector("#gate-status") as HTMLDivElement;
  const artifactEl = container.querySelector("#gate-artifact") as HTMLDivElement;
  const decisionEl = container.querySelector("#gate-decision") as HTMLDivElement;
  const approveBtn = container.querySelector("#approve-btn") as HTMLButtonElement;
  const rejectBtn = container.querySelector("#reject-btn") as HTMLButtonElement;
  const reasonInput = container.querySelector("#gate-reason") as HTMLTextAreaElement;
  const errorEl = container.querySelector("#gate-error") as HTMLDivElement;

  // -- load gate state -------------------------------------------------------

  async function loadGate(): Promise<void> {
    try {
      const resp = await fetch(`/api/projects/${projectId}/gates/${gateName}`);
      if (!resp.ok) throw new Error(`Gate not found: ${resp.status}`);
      const data = await resp.json() as { status: string; artifact: string; reason: string };

      artifactEl.textContent = data.artifact || "(no artifact)";

      if (data.status === "approved") {
        showStatus("approved", "Approved", "#2ecc71");
        decisionEl.style.display = "none";
      } else if (data.status === "rejected") {
        showStatus("rejected", `Rejected${data.reason ? ": " + data.reason : ""}`, "#e74c3c");
        decisionEl.style.display = "none";
      } else {
        decisionEl.style.display = "block";
      }
    } catch (err: unknown) {
      artifactEl.innerHTML = `<span style="color: #e74c3c;">Failed to load: ${err instanceof Error ? err.message : "Unknown error"}</span>`;
    }
  }

  function showStatus(type: string, text: string, color: string): void {
    statusEl.style.display = "block";
    statusEl.style.background = color + "22";
    statusEl.style.border = `1px solid ${color}`;
    statusEl.style.color = color;
    statusEl.textContent = text;
  }

  // -- decision handlers -----------------------------------------------------

  async function submitDecision(decision: "approved" | "rejected"): Promise<void> {
    const reason = reasonInput.value.trim();
    errorEl.style.display = "none";

    try {
      const resp = await fetch(`/api/projects/${projectId}/gates/${gateName}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason }),
      });

      if (!resp.ok) throw new Error(`Failed to decide: ${resp.status}`);

      showStatus(decision, decision === "approved" ? "Approved" : `Rejected${reason ? ": " + reason : ""}`,
                 decision === "approved" ? "#2ecc71" : "#e74c3c");
      decisionEl.style.display = "none";

      // Navigate to progress after decision
      setTimeout(() => navigate(`#project/${projectId}/progress`), 1500);
    } catch (err: unknown) {
      errorEl.textContent = err instanceof Error ? err.message : "Unknown error";
      errorEl.style.display = "block";
    }
  }

  approveBtn.addEventListener("click", () => submitDecision("approved"));
  rejectBtn.addEventListener("click", () => submitDecision("rejected"));

  loadGate();
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

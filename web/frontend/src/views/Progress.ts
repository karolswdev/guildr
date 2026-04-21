/**
 * Progress view - mission control for live runs, workflow editing, and logs.
 */

type JsonRecord = Record<string, unknown>;

type PhaseSummary = {
  phase: string;
  exists: boolean;
  count: number;
  entries: JsonRecord[];
  last_event: JsonRecord | null;
};

type LogResponse = {
  project_id: string;
  phases: PhaseSummary[];
};

type PhaseLogResponse = {
  project_id: string;
  phase: string;
  entries: JsonRecord[];
};

type EventListResponse = {
  project_id: string;
  events: JsonRecord[];
};

type WorkflowStep = {
  id: string;
  title: string;
  type: string;
  handler: string;
  enabled: boolean;
  description?: string;
  config?: JsonRecord;
};

type WorkflowResponse = {
  project_id: string;
  steps: WorkflowStep[];
};

type Persona = {
  name: string;
  perspective: string;
  mandate: string;
  turn_order: number;
  veto_scope: string;
};

type PersonaSynthesisResponse = {
  project_id: string;
  personas: Persona[];
  steps: WorkflowStep[];
};

type MemoryResponse = {
  project_id: string;
  available: boolean;
  command: string | null;
  initialized: boolean;
  wing: string;
  cached_wakeup: string;
  cached_status: string;
  last_search: string;
  metadata: JsonRecord;
  wake_up?: string;
  output?: string;
};

type StepRunState = "idle" | "active" | "done" | "waiting" | "error" | "disabled";

const PHASE_ORDER = [
  "memory_refresh",
  "persona_forum",
  "architect",
  "micro_task_breakdown",
  "implementation",
  "testing",
  "guru_escalation",
  "review",
  "deployment",
];

export function renderProgress(container: Element, navigate: (route: string) => void, projectId: string): void {
  container.innerHTML = `
    <style>
      .mc-topbar, .mc-status-strip, .mc-command, .mc-panel { padding-left: max(16px, env(safe-area-inset-left)); padding-right: max(16px, env(safe-area-inset-right)); }
      .mc-tabs { padding-left: max(16px, env(safe-area-inset-left)); padding-right: max(16px, env(safe-area-inset-right)); }
      .mc-panel-split { display: grid; gap: 16px; grid-template-columns: minmax(220px, 0.38fr) minmax(0, 0.62fr); }
      .mc-workflow-grid { display: grid; gap: 16px; grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr); }
      .mc-memory-grid { display: grid; gap: 16px; grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr); }
      @media (max-width: 760px) {
        .mc-topbar { position: sticky; top: 0; z-index: 30; align-items: flex-start !important; }
        .mc-status-strip { padding-top: 10px !important; }
        .mc-command { position: sticky; top: 54px; z-index: 25; box-shadow: 0 10px 24px rgba(0,0,0,0.28); }
        .mc-tabs { position: fixed; left: 0; right: 0; bottom: 0; z-index: 40; padding: 6px max(10px, env(safe-area-inset-right)) max(8px, env(safe-area-inset-bottom)) max(10px, env(safe-area-inset-left)) !important; justify-content: space-around; border-top: 1px solid #202020; border-bottom: none !important; }
        .mc-tab { min-width: 64px; min-height: 44px; padding: 8px 10px !important; border-bottom: none !important; border-radius: 8px; }
        .mc-panel { padding: 12px max(12px, env(safe-area-inset-right)) calc(84px + env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)) !important; }
        .mc-panel-split, .mc-workflow-grid, .mc-memory-grid { grid-template-columns: 1fr !important; }
        .mc-command > div { display: grid !important; grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .mc-command button, .mc-command select, .mc-command input, .mc-command label { min-height: 44px; }
        #run-strip { display: flex !important; overflow-x: auto; padding-bottom: 4px; scroll-snap-type: x mandatory; }
        #run-strip > button { min-width: 148px; scroll-snap-align: start; }
      }
    </style>
    <header class="mc-topbar" style="padding: 12px 16px; border-bottom: 1px solid #1a1a1a; background: #050505; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;">
      <div style="display: flex; align-items: center; gap: 16px;">
        <button
          onclick="navigate('#project/${projectId}')"
          style="background: none; border: none; color: #8fd3ff; font-size: 13px; cursor: pointer; padding: 4px 0;"
        >&larr; Back</button>
        <h1 style="font-size: 18px; margin: 0; font-weight: 600;">Mission Control</h1>
        <div id="dirty-indicator" style="font-size: 11px; color: #8c8c8c;">Workflow synced</div>
      </div>
      <div id="control-status" style="font-size: 13px; color: #8c8c8c; min-height: 18px;"></div>
    </header>

    <section class="mc-status-strip" style="padding: 12px 16px; background: linear-gradient(180deg,#121826 0%,#0c0f16 100%); border-bottom: 1px solid #273148;">
      <div style="display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-bottom: 10px;">
        <div style="padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid #24324b; border-radius: 8px;">
          <div style="font-size: 10px; color: #7f8aa3; text-transform: uppercase; letter-spacing: 0; margin-bottom: 4px;">Current Focus</div>
          <div id="focus-step" style="font-size: 15px; font-weight: 600; color: #f3f7ff;">Loading...</div>
          <div id="focus-detail" style="font-size: 12px; color: #b7c1d8; margin-top: 4px;">Waiting for run state.</div>
        </div>
        <div style="padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid #24324b; border-radius: 8px;">
          <div style="font-size: 10px; color: #7f8aa3; text-transform: uppercase; letter-spacing: 0; margin-bottom: 4px;">Next Step</div>
          <div id="focus-next" style="font-size: 15px; font-weight: 600; color: #f3f7ff;">-</div>
          <div id="focus-next-detail" style="font-size: 12px; color: #b7c1d8; margin-top: 4px;">Workflow ready.</div>
        </div>
        <div style="padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid #24324b; border-radius: 8px;">
          <div style="font-size: 10px; color: #7f8aa3; text-transform: uppercase; letter-spacing: 0; margin-bottom: 4px;">Telemetry</div>
          <div style="display: flex; justify-content: space-between; gap: 8px;">
            <div>
              <div style="font-size: 10px; color: #7f8aa3;">tok/s</div>
              <div id="tok-s" style="font-size: 15px; font-weight: 600; color: #7de5b1;">-</div>
            </div>
            <div>
              <div style="font-size: 10px; color: #7f8aa3;">VRAM</div>
              <div id="vram" style="font-size: 15px; font-weight: 600; color: #7de5b1;">-</div>
            </div>
          </div>
        </div>
        <div style="padding: 10px 12px; background: rgba(255,255,255,0.03); border: 1px solid #24324b; border-radius: 8px;">
          <div style="font-size: 10px; color: #7f8aa3; text-transform: uppercase; letter-spacing: 0; margin-bottom: 4px;">Latest Signal</div>
          <div id="latest-signal" style="font-size: 13px; font-weight: 600; color: #f3f7ff;">Connecting...</div>
          <div id="latest-signal-detail" style="font-size: 12px; color: #b7c1d8; margin-top: 4px;">Event stream starting.</div>
        </div>
      </div>
      <div id="run-strip" style="display: grid; gap: 6px; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));"></div>
    </section>

    <section class="mc-command" style="padding: 10px 16px; background: #0a0a0a; border-bottom: 1px solid #1a1a1a;">
      <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end;">
        <div>
          <div style="font-size: 10px; color: #666; text-transform: uppercase; margin-bottom: 4px;">Resume from</div>
          <select id="resume-step" style="${selectStyle()}"></select>
        </div>
        <div>
          <div style="font-size: 10px; color: #666; text-transform: uppercase; margin-bottom: 4px;">Scope</div>
          <select id="instruction-scope" style="${selectStyle()}">
            <option value="">All phases</option>
          </select>
        </div>
        <button id="btn-inject" style="${actionButton("#173c66", "#ffffff")}">Inject</button>
        <button id="btn-compact" style="${actionButton("#1d4f38", "#ffffff")}">Compact</button>
        <button id="btn-resume" style="${actionButton("#8fd3ff", "#05111d", true)}">Resume</button>
        <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: #d5d5d5; align-self: flex-end; padding-bottom: 10px;">
          <input id="compact-before-resume" type="checkbox" /> Compact ctx
        </label>
      </div>
      <details style="margin-top: 8px;">
        <summary style="cursor: pointer; color: #8c8c8c; font-size: 12px; user-select: none;">Add instruction&hellip;</summary>
        <textarea
          id="operator-instruction"
          rows="3"
          placeholder="Inject a directive, remediation note, or priority correction."
          style="${textAreaStyle()}; margin-top: 8px;"
        ></textarea>
      </details>
    </section>

    <nav class="mc-tabs" style="display: flex; padding: 0 16px; background: #070707; border-bottom: 1px solid #1a1a1a; gap: 0; overflow-x: auto;">
      <button class="mc-tab" data-tab="pulse" style="${tabStyle(true)}">Pulse</button>
      <button class="mc-tab" data-tab="workflow" style="${tabStyle(false)}">Workflow</button>
      <button class="mc-tab" data-tab="team" style="${tabStyle(false)}">Team</button>
      <button class="mc-tab" data-tab="memory" style="${tabStyle(false)}">Memory</button>
      <button class="mc-tab" data-tab="logs" style="${tabStyle(false)}">Logs</button>
    </nav>

    <div id="panel-pulse" class="mc-panel" style="padding: 16px; display: grid; gap: 16px;">
      <div class="mc-panel-split">
        <div style="display: grid; gap: 10px; align-content: start;">
          <div style="padding: 12px; background: #0b0b0b; border: 1px solid #202020; border-radius: 8px;">
            <div style="font-size: 11px; color: #8c8c8c; margin-bottom: 6px;">Now</div>
            <div id="focus-panel-title" style="font-size: 16px; font-weight: 600; color: #f3f3f3;">Waiting for events</div>
            <div id="focus-panel-body" style="font-size: 12px; color: #b5b5b5; margin-top: 6px; line-height: 1.5;">Open the run, inject instructions, or resume from any enabled step.</div>
          </div>
          <div id="focus-panel-grid" style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;"></div>
        </div>
        <section style="padding: 14px; background: #111111; border: 1px solid #272727; border-radius: 8px; display: grid; gap: 10px; align-content: start;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 14px; font-weight: 600;">Live Timeline</div>
            <button id="btn-follow-live" style="${miniButtonStyle("#173c66", "#ffffff")}">Follow Live</button>
          </div>
          <div id="event-log" style="max-height: 320px; overflow-y: auto; display: grid; gap: 6px;"></div>
        </section>
      </div>
      <section style="padding: 14px; background: #111111; border: 1px solid #272727; border-radius: 8px;">
        <div style="font-size: 13px; font-weight: 600; margin-bottom: 10px; color: #9c9c9c; text-transform: uppercase; letter-spacing: 0;">Event Detail</div>
        <div id="event-detail" style="padding: 12px; background: #0b0b0b; border: 1px solid #202020; border-radius: 8px; min-height: 180px;"></div>
      </section>
    </div>

    <div id="panel-workflow" class="mc-panel" hidden style="padding: 16px; display: grid; gap: 16px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;">
        <div>
          <div style="font-size: 15px; font-weight: 600;">Workflow</div>
          <div style="font-size: 12px; color: #8c8c8c; margin-top: 3px;">Drag to reorder. Toggle steps. Click to inspect.</div>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
          <button id="btn-add-checkpoint" style="${actionButton("#51411b", "#ffffff")}">Add Checkpoint</button>
          <button id="btn-reload-workflow" style="${actionButton("#173c66", "#ffffff")}">Reload</button>
          <button id="btn-save-workflow" style="${actionButton("#1d4f38", "#ffffff")}">Save</button>
        </div>
      </div>
      <div class="mc-workflow-grid">
        <div id="workflow-board" style="display: grid; gap: 10px;"></div>
        <div id="workflow-inspector" style="padding: 12px; background: #0b0b0b; border: 1px solid #202020; border-radius: 8px;"></div>
      </div>
      <details>
        <summary style="cursor: pointer; color: #8fd3ff; font-size: 13px; user-select: none;">Advanced workflow JSON</summary>
        <textarea
          id="workflow-editor"
          rows="14"
          style="${textAreaStyle("12px", "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace")}; margin-top: 10px;"
        ></textarea>
      </details>
    </div>

    <div id="panel-team" class="mc-panel" hidden style="padding: 16px; display: grid; gap: 16px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;">
        <div>
          <div style="font-size: 15px; font-weight: 600;">Founding Team</div>
          <div style="font-size: 12px; color: #8c8c8c; margin-top: 3px;">Personas shape how the forum debates trade-offs.</div>
        </div>
        <div style="display: flex; gap: 8px;">
          <button id="btn-build-team" style="${actionButton("#61318b", "#ffffff")}">Build Team</button>
          <button id="btn-add-persona" style="${actionButton("#173c66", "#ffffff")}">Add Persona</button>
          <button id="btn-save-team" style="${actionButton("#1d4f38", "#ffffff")}">Save Team</button>
        </div>
      </div>
      <div id="persona-list" style="display: grid; gap: 10px;"></div>
    </div>

    <div id="panel-memory" class="mc-panel" hidden style="padding: 16px; display: grid; gap: 16px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;">
        <div>
          <div style="font-size: 15px; font-weight: 600;">Palace Memory</div>
          <div style="font-size: 12px; color: #a996b6; margin-top: 3px;">Mine the project, refresh wake-up context, search the palace.</div>
        </div>
        <div id="memory-status-badge" style="padding: 5px 10px; border-radius: 999px; background: #1f1527; border: 1px solid #352145; color: #d8cae4; font-size: 12px;">Checking...</div>
      </div>
      <div class="mc-memory-grid">
        <div style="display: grid; gap: 10px; align-content: start;">
          <div id="memory-meta" style="display: grid; gap: 8px;"></div>
          <button id="btn-memory-sync" style="${actionButton("#61318b", "#ffffff")}">Sync Palace</button>
          <button id="btn-memory-wakeup" style="${actionButton("#173c66", "#ffffff")}">Refresh Wake-Up</button>
          <input id="memory-query" placeholder="Search: why did we switch to GraphQL" style="${inputStyle()}" />
          <input id="memory-room" placeholder="Optional room scope" style="${inputStyle()}" />
          <button id="btn-memory-search" style="${actionButton("#1d4f38", "#ffffff")}">Search Palace</button>
        </div>
        <div style="padding: 12px; background: #09070d; border: 1px solid #24192e; border-radius: 8px; min-height: 260px;">
          <pre id="memory-output" style="margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.6; color: #eadff2; white-space: pre-wrap; word-break: break-word;">Loading memory status...</pre>
        </div>
      </div>
    </div>

    <div id="panel-logs" class="mc-panel" hidden style="padding: 16px; display: grid; gap: 12px;">
      <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;">
        <div>
          <div style="font-size: 15px; font-weight: 600;">Terminal Peek</div>
          <div style="font-size: 12px; color: #8c8c8c; margin-top: 3px;">Phase logs with preserved indentation and wrapped output.</div>
        </div>
        <div id="log-phase-tabs" style="display: flex; flex-wrap: wrap; gap: 6px;"></div>
      </div>
      <div id="phase-log-shell" style="padding: 12px; background: #080808; border: 1px solid #1d1d1d; border-radius: 8px; min-height: 280px;">
        <pre id="phase-log-detail" style="margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.6; color: #d8d8d8; white-space: pre-wrap; word-break: break-word;"></pre>
      </div>
    </div>
  `;

  const dirtyIndicator = container.querySelector("#dirty-indicator") as HTMLDivElement;
  const focusStep = container.querySelector("#focus-step") as HTMLDivElement;
  const focusDetail = container.querySelector("#focus-detail") as HTMLDivElement;
  const focusNext = container.querySelector("#focus-next") as HTMLDivElement;
  const focusNextDetail = container.querySelector("#focus-next-detail") as HTMLDivElement;
  const tokS = container.querySelector("#tok-s") as HTMLDivElement;
  const vram = container.querySelector("#vram") as HTMLDivElement;
  const latestSignal = container.querySelector("#latest-signal") as HTMLDivElement;
  const latestSignalDetail = container.querySelector("#latest-signal-detail") as HTMLDivElement;
  const runStrip = container.querySelector("#run-strip") as HTMLDivElement;
  const resumeStep = container.querySelector("#resume-step") as HTMLSelectElement;
  const instructionScope = container.querySelector("#instruction-scope") as HTMLSelectElement;
  const instructionInput = container.querySelector("#operator-instruction") as HTMLTextAreaElement;
  const compactCheckbox = container.querySelector("#compact-before-resume") as HTMLInputElement;
  const controlStatus = container.querySelector("#control-status") as HTMLDivElement;
  const focusPanelTitle = container.querySelector("#focus-panel-title") as HTMLDivElement;
  const focusPanelBody = container.querySelector("#focus-panel-body") as HTMLDivElement;
  const focusPanelGrid = container.querySelector("#focus-panel-grid") as HTMLDivElement;
  const workflowBoard = container.querySelector("#workflow-board") as HTMLDivElement;
  const workflowInspector = container.querySelector("#workflow-inspector") as HTMLDivElement;
  const workflowEditor = container.querySelector("#workflow-editor") as HTMLTextAreaElement;
  const personaList = container.querySelector("#persona-list") as HTMLDivElement;
  const memoryStatusBadge = container.querySelector("#memory-status-badge") as HTMLDivElement;
  const memoryMeta = container.querySelector("#memory-meta") as HTMLDivElement;
  const memoryQuery = container.querySelector("#memory-query") as HTMLInputElement;
  const memoryRoom = container.querySelector("#memory-room") as HTMLInputElement;
  const memoryOutput = container.querySelector("#memory-output") as HTMLPreElement;
  const eventLog = container.querySelector("#event-log") as HTMLDivElement;
  const eventDetail = container.querySelector("#event-detail") as HTMLDivElement;
  const logPhaseTabs = container.querySelector("#log-phase-tabs") as HTMLDivElement;
  const phaseLogDetail = container.querySelector("#phase-log-detail") as HTMLPreElement;

  const btnInject = container.querySelector("#btn-inject") as HTMLButtonElement;
  const btnCompact = container.querySelector("#btn-compact") as HTMLButtonElement;
  const btnResume = container.querySelector("#btn-resume") as HTMLButtonElement;
  const btnBuildTeam = container.querySelector("#btn-build-team") as HTMLButtonElement;
  const btnAddCheckpoint = container.querySelector("#btn-add-checkpoint") as HTMLButtonElement;
  const btnReloadWorkflow = container.querySelector("#btn-reload-workflow") as HTMLButtonElement;
  const btnSaveWorkflow = container.querySelector("#btn-save-workflow") as HTMLButtonElement;
  const btnAddPersona = container.querySelector("#btn-add-persona") as HTMLButtonElement;
  const btnSaveTeam = container.querySelector("#btn-save-team") as HTMLButtonElement;
  const btnMemorySync = container.querySelector("#btn-memory-sync") as HTMLButtonElement;
  const btnMemoryWakeup = container.querySelector("#btn-memory-wakeup") as HTMLButtonElement;
  const btnMemorySearch = container.querySelector("#btn-memory-search") as HTMLButtonElement;
  const btnFollowLive = container.querySelector("#btn-follow-live") as HTMLButtonElement;

  let workflowSteps: WorkflowStep[] = [];
  let workflowDirty = false;
  let selectedWorkflowStepId = "";
  let selectedLogPhase = PHASE_ORDER[0];
  let evtSource: EventSource | null = null;
  let refreshTimer: number | null = null;
  let eventHistory: JsonRecord[] = [];
  let followLiveDetail = true;
  let selectedEventIndex = -1;
  let phaseSummaries: PhaseSummary[] = [];
  let selectedPhaseLogEntries: JsonRecord[] = [];
  let stepStatuses: Record<string, StepRunState> = {};
  let currentSignal = "";
  let currentSignalDetail = "";
  let currentStepId = "";
  let currentTokS = "-";
  let currentVram = "-";
  let memoryState: MemoryResponse | null = null;

  function switchTab(tab: string): void {
    for (const t of ["pulse", "workflow", "team", "memory", "logs"]) {
      const panel = container.querySelector(`#panel-${t}`) as HTMLElement;
      panel.hidden = t !== tab;
    }
    for (const btn of container.querySelectorAll(".mc-tab")) {
      const b = btn as HTMLButtonElement;
      const active = b.dataset.tab === tab;
      b.style.cssText = tabStyle(active);
    }
  }

  for (const btn of container.querySelectorAll(".mc-tab")) {
    btn.addEventListener("click", () => {
      switchTab((btn as HTMLButtonElement).dataset.tab ?? "pulse");
    });
  }

  function setDirty(dirty: boolean): void {
    workflowDirty = dirty;
    dirtyIndicator.textContent = dirty ? "Unsaved edits" : "Workflow synced";
    dirtyIndicator.style.color = dirty ? "#f0c36f" : "#8c8c8c";
  }

  function setStatus(message: string, isError = false): void {
    controlStatus.textContent = message;
    controlStatus.style.color = isError ? "#ff7a7a" : "#8c8c8c";
  }

  function setBusy(button: HTMLButtonElement, busy: boolean, label: string): void {
    button.disabled = busy;
    button.textContent = label;
    button.style.opacity = busy ? "0.7" : "1";
  }

  function syncStepStateStore(): void {
    (window as unknown as { __guildrStepStates?: Record<string, StepRunState> }).__guildrStepStates = { ...stepStatuses };
  }

  function getPersonaStep(): WorkflowStep | undefined {
    return workflowSteps.find((step) => step.id === "persona_forum");
  }

  function getPersonas(): Persona[] {
    return getPersonasFromStep(getPersonaStep());
  }

  function setPersonas(personas: Persona[]): void {
    updateStep("persona_forum", (step) => ({
      ...step,
      config: {
        ...(step.config ?? {}),
        personas: personas.map((persona) => ({
          name: persona.name,
          perspective: persona.perspective,
          mandate: persona.mandate,
          turn_order: persona.turn_order,
          veto_scope: persona.veto_scope,
        })),
      },
    }));
  }

  function getNextEnabledStep(currentId: string): WorkflowStep | undefined {
    const enabled = workflowSteps.filter((step) => step.enabled);
    const index = enabled.findIndex((step) => step.id === currentId);
    if (index < 0) {
      return enabled[0];
    }
    return enabled[index + 1];
  }

  function replaceWorkflow(nextSteps: WorkflowStep[], dirty = false): void {
    workflowSteps = nextSteps.map(cloneStep);
    if (!selectedWorkflowStepId || !workflowSteps.some((step) => step.id === selectedWorkflowStepId)) {
      selectedWorkflowStepId = workflowSteps[0]?.id ?? "";
    }
    if (!selectedLogPhase || !workflowSteps.some((step) => step.id === selectedLogPhase && step.type === "phase")) {
      selectedLogPhase = workflowSteps.find((step) => step.type === "phase")?.id ?? PHASE_ORDER[0];
    }
    renderResumeOptions();
    renderInstructionScopeOptions();
    syncWorkflowEditor();
    syncStepStateStore();
    setDirty(dirty);
    renderWorkflowBoard();
    renderWorkflowInspector();
    renderRunStrip();
    renderPersonas();
    renderFocus();
    renderLogPhaseTabs();
  }

  function updateStep(stepId: string, updater: (step: WorkflowStep) => WorkflowStep): void {
    const next = workflowSteps.map((step) => (step.id === stepId ? updater(cloneStep(step)) : cloneStep(step)));
    replaceWorkflow(next, true);
  }

  function syncWorkflowEditor(): void {
    workflowEditor.value = JSON.stringify(workflowSteps, null, 2);
  }

  function renderResumeOptions(): void {
    const enabled = workflowSteps.filter((step) => step.enabled);
    resumeStep.innerHTML = enabled
      .map((step) => `<option value="${escapeHtml(step.id)}">${escapeHtml(step.title || step.id)}</option>`)
      .join("");
    if (enabled.length > 0 && !enabled.some((step) => step.id === resumeStep.value)) {
      resumeStep.value = enabled[0].id;
    }
  }

  function renderInstructionScopeOptions(): void {
    const phases = workflowSteps.filter((step) => step.type === "phase");
    const currentValue = instructionScope.value;
    instructionScope.innerHTML = [
      `<option value="">All phases</option>`,
      ...phases.map((step) => `<option value="${escapeHtml(step.id)}">${escapeHtml(step.title || step.id)}</option>`),
    ].join("");
    instructionScope.value = phases.some((step) => step.id === currentValue) ? currentValue : "";
  }

  function renderRunStrip(): void {
    runStrip.innerHTML = "";
    if (workflowSteps.length === 0) {
      runStrip.innerHTML = `<div style="color: #8c8c8c; font-size: 12px;">Workflow not loaded yet.</div>`;
      return;
    }

    for (const step of workflowSteps) {
      const state = getStepState(step.id, step.enabled);
      const palette = statePalette(state);
      const card = document.createElement("button");
      card.type = "button";
      card.style.cssText = `
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid ${palette.border};
        background: ${palette.background};
        color: ${palette.text};
        text-align: left;
        cursor: pointer;
      `;
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; gap: 6px; align-items: center; margin-bottom: 5px;">
          <span style="font-size: 10px; color: ${palette.muted}; text-transform: uppercase; letter-spacing: 0;">${escapeHtml(step.type)}</span>
          <span style="width: 8px; height: 8px; border-radius: 999px; background: ${palette.dot};"></span>
        </div>
        <div style="font-size: 12px; font-weight: 600;">${escapeHtml(step.title || step.id)}</div>
      `;
      card.addEventListener("click", () => {
        selectedWorkflowStepId = step.id;
        if (step.type === "phase") {
          selectedLogPhase = step.id;
          void refreshSelectedPhaseLog();
        }
        renderWorkflowBoard();
        renderWorkflowInspector();
        renderRunStrip();
        renderLogPhaseTabs();
        switchTab("workflow");
      });
      runStrip.appendChild(card);
    }
  }

  function renderWorkflowBoard(): void {
    workflowBoard.innerHTML = "";
    if (workflowSteps.length === 0) {
      workflowBoard.innerHTML = `<div style="color: #8c8c8c; font-size: 13px;">Workflow not loaded yet.</div>`;
      return;
    }

    for (const step of workflowSteps) {
      const state = getStepState(step.id, step.enabled);
      const palette = statePalette(state);
      const card = document.createElement("div");
      card.draggable = true;
      card.style.cssText = `
        padding: 12px;
        border-radius: 8px;
        border: 1px solid ${selectedWorkflowStepId === step.id ? "#8fd3ff" : palette.border};
        background: ${selectedWorkflowStepId === step.id ? "#111d2f" : palette.background};
        cursor: grab;
      `;
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;">
          <div style="display: grid; gap: 5px; min-width: 0;">
            <div style="display: flex; flex-wrap: wrap; gap: 5px; align-items: center;">
              <span style="padding: 2px 6px; border-radius: 999px; background: rgba(255,255,255,0.05); color: ${palette.text}; font-size: 10px; text-transform: uppercase;">${escapeHtml(step.type)}</span>
              <span style="padding: 2px 6px; border-radius: 999px; background: rgba(255,255,255,0.05); color: ${palette.muted}; font-size: 10px;">${escapeHtml(state)}</span>
            </div>
            <div style="font-size: 14px; font-weight: 600; color: #f2f2f2;">${escapeHtml(step.title || step.id)}</div>
            <div style="font-size: 11px; color: #8c8c8c;">${escapeHtml(step.id)}</div>
            <div style="font-size: 12px; color: #bcbcbc; line-height: 1.4;">${escapeHtml(step.description || summarizeStepConfig(step))}</div>
          </div>
          <label style="display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: #d5d5d5; flex-shrink: 0;">
            <input type="checkbox" ${step.enabled ? "checked" : ""} data-action="toggle-enabled" data-step-id="${escapeHtml(step.id)}" />
            On
          </label>
        </div>
      `;

      card.addEventListener("click", (event: MouseEvent) => {
        const target = event.target as HTMLElement;
        if (target.closest('input[data-action="toggle-enabled"]')) {
          return;
        }
        selectedWorkflowStepId = step.id;
        if (step.type === "phase") {
          selectedLogPhase = step.id;
        }
        renderWorkflowBoard();
        renderWorkflowInspector();
        renderRunStrip();
        renderLogPhaseTabs();
        void refreshSelectedPhaseLog();
      });

      card.addEventListener("dragstart", (event: DragEvent) => {
        event.dataTransfer?.setData("text/plain", step.id);
      });
      card.addEventListener("dragover", (event: DragEvent) => {
        event.preventDefault();
      });
      card.addEventListener("drop", (event: DragEvent) => {
        event.preventDefault();
        const sourceId = event.dataTransfer?.getData("text/plain");
        if (!sourceId || sourceId === step.id) {
          return;
        }
        const next = reorderSteps(workflowSteps, sourceId, step.id);
        replaceWorkflow(next, true);
      });

      workflowBoard.appendChild(card);
    }

    for (const input of workflowBoard.querySelectorAll('input[data-action="toggle-enabled"]')) {
      input.addEventListener("change", (event) => {
        const target = event.currentTarget as HTMLInputElement;
        const stepId = target.dataset.stepId ?? "";
        updateStep(stepId, (step) => ({ ...step, enabled: target.checked }));
      });
    }
  }

  function renderWorkflowInspector(): void {
    const step = workflowSteps.find((item) => item.id === selectedWorkflowStepId);
    if (!step) {
      workflowInspector.innerHTML = `<div style="color: #8c8c8c; font-size: 13px;">Select a workflow step.</div>`;
      return;
    }

    workflowInspector.innerHTML = `
      <div style="display: grid; gap: 12px;">
        <div>
          <div style="font-size: 14px; font-weight: 600; color: #f2f2f2;">${escapeHtml(step.title || step.id)}</div>
          <div style="font-size: 11px; color: #8c8c8c; margin-top: 3px;">${escapeHtml(step.id)} &middot; ${escapeHtml(step.type)} &middot; ${escapeHtml(step.handler)}</div>
        </div>
        <div>
          <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Title</label>
          <input id="inspector-title" value="${escapeHtml(step.title || "")}" style="${inputStyle()}" />
        </div>
        <div>
          <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Description</label>
          <textarea id="inspector-description" rows="3" style="${textAreaStyle()}">${escapeHtml(step.description || "")}</textarea>
        </div>
        <label style="display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #d5d5d5;">
          <input id="inspector-enabled" type="checkbox" ${step.enabled ? "checked" : ""} />
          Step enabled
        </label>
        <div>
          <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Config JSON</label>
          <textarea id="inspector-config" rows="8" style="${textAreaStyle("12px", "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace")}">${escapeHtml(JSON.stringify(step.config ?? {}, null, 2))}</textarea>
        </div>
        <div id="inspector-config-status" style="font-size: 12px; color: #8c8c8c;"></div>
      </div>
    `;

    const titleInput = workflowInspector.querySelector("#inspector-title") as HTMLInputElement;
    const descriptionInput = workflowInspector.querySelector("#inspector-description") as HTMLTextAreaElement;
    const enabledInput = workflowInspector.querySelector("#inspector-enabled") as HTMLInputElement;
    const configInput = workflowInspector.querySelector("#inspector-config") as HTMLTextAreaElement;
    const configStatus = workflowInspector.querySelector("#inspector-config-status") as HTMLDivElement;

    titleInput.addEventListener("input", () => {
      updateStep(step.id, (current) => ({ ...current, title: titleInput.value }));
    });
    descriptionInput.addEventListener("input", () => {
      updateStep(step.id, (current) => ({ ...current, description: descriptionInput.value }));
    });
    enabledInput.addEventListener("change", () => {
      updateStep(step.id, (current) => ({ ...current, enabled: enabledInput.checked }));
    });
    configInput.addEventListener("input", () => {
      try {
        const parsed = JSON.parse(configInput.value) as JsonRecord;
        configStatus.textContent = "Config valid";
        configStatus.style.color = "#7de5b1";
        updateStep(step.id, (current) => ({ ...current, config: parsed }));
      } catch (err: unknown) {
        configStatus.textContent = err instanceof Error ? err.message : "Invalid JSON";
        configStatus.style.color = "#ff7a7a";
      }
    });
  }

  function renderPersonas(): void {
    personaList.innerHTML = "";
    const personas = getPersonas();
    if (personas.length === 0) {
      personaList.innerHTML = `<div style="padding: 14px; border: 1px dashed #2d2d2d; border-radius: 8px; color: #8c8c8c; font-size: 13px;">No personas yet. Build the team or add one manually.</div>`;
      return;
    }

    personas
      .slice()
      .sort((a, b) => a.turn_order - b.turn_order)
      .forEach((persona, index) => {
        const card = document.createElement("div");
        card.style.cssText = "padding: 12px; background: #0b0b0b; border: 1px solid #202020; border-radius: 8px;";
        card.innerHTML = `
          <div style="display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 10px;">
            <div>
              <span style="font-size: 14px; font-weight: 600; color: #f2f2f2;">${escapeHtml(persona.name || `Persona ${index + 1}`)}</span>
              <span style="font-size: 11px; color: #8c8c8c; margin-left: 8px;">#${persona.turn_order}</span>
            </div>
            <button type="button" data-remove-index="${index}" style="${miniButtonStyle("#4d2020", "#ffffff")}">Remove</button>
          </div>
          <details>
            <summary style="cursor: pointer; color: #8c8c8c; font-size: 12px; user-select: none;">Edit fields&hellip;</summary>
            <div style="display: grid; gap: 10px; margin-top: 10px;">
              <div>
                <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Name</label>
                <input data-field="name" data-index="${index}" value="${escapeHtml(persona.name)}" style="${inputStyle()}" />
              </div>
              <div>
                <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Perspective</label>
                <textarea data-field="perspective" data-index="${index}" rows="2" style="${textAreaStyle()}">${escapeHtml(persona.perspective)}</textarea>
              </div>
              <div>
                <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Mandate</label>
                <textarea data-field="mandate" data-index="${index}" rows="3" style="${textAreaStyle()}">${escapeHtml(persona.mandate)}</textarea>
              </div>
              <div style="display: grid; grid-template-columns: 110px 1fr; gap: 10px;">
                <div>
                  <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Turn Order</label>
                  <input data-field="turn_order" data-index="${index}" type="number" min="1" value="${String(persona.turn_order)}" style="${inputStyle()}" />
                </div>
                <div>
                  <label style="display: block; font-size: 11px; color: #8c8c8c; margin-bottom: 5px;">Veto Scope</label>
                  <input data-field="veto_scope" data-index="${index}" value="${escapeHtml(persona.veto_scope)}" style="${inputStyle()}" />
                </div>
              </div>
            </div>
          </details>
        `;
        personaList.appendChild(card);
      });

    for (const field of personaList.querySelectorAll("[data-field]")) {
      field.addEventListener("input", (event) => {
        const target = event.currentTarget as HTMLInputElement | HTMLTextAreaElement;
        const index = Number(target.dataset.index ?? "-1");
        const key = target.dataset.field as keyof Persona;
        const currentPersonas = getPersonas();
        if (!currentPersonas[index]) {
          return;
        }
        const nextValue: string | number = key === "turn_order" ? Number(target.value || "0") : target.value;
        const nextPersonas = currentPersonas.map((item, itemIndex) => (
          itemIndex === index ? { ...item, [key]: nextValue } : { ...item }
        ));
        setPersonas(nextPersonas);
      });
    }

    for (const button of personaList.querySelectorAll("[data-remove-index]")) {
      button.addEventListener("click", (event) => {
        const target = event.currentTarget as HTMLButtonElement;
        const index = Number(target.dataset.removeIndex ?? "-1");
        const next = getPersonas().filter((_, itemIndex) => itemIndex !== index);
        setPersonas(next);
      });
    }
  }

  function renderMemory(): void {
    const available = memoryState?.available ?? false;
    const initialized = memoryState?.initialized ?? false;
    const badgeText = !available ? "MemPalace required" : initialized ? "Palace ready" : "Needs sync";
    const badgeColors = !available
      ? { background: "#2a1216", border: "#5d232c", color: "#ffd0d7" }
      : initialized
        ? { background: "#132018", border: "#244734", color: "#c8f0da" }
        : { background: "#22180f", border: "#5d4520", color: "#ffe0b0" };

    memoryStatusBadge.textContent = badgeText;
    memoryStatusBadge.style.background = badgeColors.background;
    memoryStatusBadge.style.borderColor = badgeColors.border;
    memoryStatusBadge.style.color = badgeColors.color;

    memoryMeta.innerHTML = [
      quickStateTile("Wing", memoryState?.wing || projectId),
      quickStateTile("Init", initialized ? "ready" : "not yet"),
      quickStateTile("Command", memoryState?.command || "not found"),
      quickStateTile("Search cache", memoryState?.last_search ? "present" : "empty"),
    ].join("");

    const visible = memoryState?.wake_up || memoryState?.output || memoryState?.cached_wakeup || memoryState?.cached_status || "No palace output yet.";
    memoryOutput.textContent = visible;
  }

  async function loadMemoryStatus(): Promise<void> {
    try {
      memoryState = await apiGet<MemoryResponse>(`/api/projects/${projectId}/memory/status`);
    } catch (err: unknown) {
      memoryState = {
        project_id: projectId,
        available: false,
        command: null,
        initialized: false,
        wing: projectId,
        cached_wakeup: "",
        cached_status: err instanceof Error ? err.message : "Failed to load memory status.",
        last_search: "",
        metadata: {},
      };
    }
    renderMemory();
  }

  function renderEventTimeline(): void {
    eventLog.innerHTML = "";
    if (eventHistory.length === 0) {
      eventLog.innerHTML = `<div style="padding: 12px; border: 1px dashed #2d2d2d; border-radius: 8px; color: #8c8c8c; font-size: 12px;">Connecting to event stream...</div>`;
      return;
    }

    eventHistory.forEach((entry, index) => {
      const type = String(entry.type ?? "event");
      const phase = String(entry.name ?? entry.phase ?? entry.gate ?? "");
      const active = index === selectedEventIndex;
      const palette = eventPalette(type);
      const row = document.createElement("button");
      row.type = "button";
      row.style.cssText = `
        width: 100%;
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid ${active ? "#8fd3ff" : palette.border};
        background: ${active ? "#111d2f" : palette.background};
        color: #f3f3f3;
        text-align: left;
        cursor: pointer;
      `;
      row.innerHTML = `
        <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;">
          <div style="display: flex; gap: 6px; align-items: center; min-width: 0;">
            <span style="width: 7px; height: 7px; border-radius: 999px; background: ${palette.dot}; flex: 0 0 auto;"></span>
            <span style="font-size: 12px; font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(describeEvent(entry))}</span>
          </div>
          <span style="font-size: 10px; color: #8c8c8c; flex: 0 0 auto;">${escapeHtml(readableTime(entry.ts))}</span>
        </div>
        <div style="display: flex; justify-content: space-between; gap: 8px; margin-top: 4px;">
          <span style="font-size: 10px; color: ${palette.dot}; text-transform: uppercase;">${escapeHtml(type)}</span>
          <span style="font-size: 10px; color: #8c8c8c;">${escapeHtml(phase || "run")}</span>
        </div>
      `;
      row.addEventListener("click", () => {
        selectedEventIndex = index;
        followLiveDetail = false;
        renderEventTimeline();
        renderEventDetail();
      });
      eventLog.appendChild(row);
    });
  }

  function renderEventDetail(): void {
    const entry = eventHistory[selectedEventIndex];
    if (!entry) {
      eventDetail.innerHTML = `<div style="color: #8c8c8c; font-size: 13px;">No event selected.</div>`;
      return;
    }

    const type = String(entry.type ?? "event");
    const phase = String(entry.name ?? entry.phase ?? entry.gate ?? "run");
    eventDetail.innerHTML = `
      <div style="display: grid; gap: 10px;">
        <div>
          <div style="display: flex; justify-content: space-between; gap: 10px; align-items: center;">
            <div style="font-size: 15px; font-weight: 600; color: #f2f2f2;">${escapeHtml(describeEvent(entry))}</div>
            <div style="font-size: 11px; color: #8c8c8c;">${escapeHtml(readableTime(entry.ts))}</div>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;">
            <span style="padding: 3px 7px; border-radius: 999px; background: #151515; border: 1px solid #262626; font-size: 11px; color: #d0d0d0;">${escapeHtml(type)}</span>
            <span style="padding: 3px 7px; border-radius: 999px; background: #151515; border: 1px solid #262626; font-size: 11px; color: #d0d0d0;">${escapeHtml(phase)}</span>
            <span style="padding: 3px 7px; border-radius: 999px; background: #151515; border: 1px solid #262626; font-size: 11px; color: #d0d0d0;">${followLiveDetail ? "Following live" : "Pinned"}</span>
          </div>
        </div>
        <div style="font-size: 12px; color: #b8b8b8; line-height: 1.6;">${escapeHtml(eventNarrative(entry))}</div>
        <pre style="margin: 0; padding: 10px; background: #070707; border: 1px solid #1d1d1d; border-radius: 8px; color: #d8d8d8; font-size: 11px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;">${escapeHtml(JSON.stringify(entry, null, 2))}</pre>
      </div>
    `;
  }

  function renderLogPhaseTabs(): void {
    logPhaseTabs.innerHTML = "";
    const phases = phaseSummaries.length > 0
      ? phaseSummaries
      : workflowSteps.filter((step) => step.type === "phase").map((step) => ({
          phase: step.id,
          exists: false,
          count: 0,
          entries: [],
          last_event: null,
        }));

    for (const phase of phases) {
      const active = phase.phase === selectedLogPhase;
      const button = document.createElement("button");
      button.type = "button";
      button.style.cssText = active
        ? miniButtonStyle("#173c66", "#ffffff")
        : miniButtonStyle("#181818", "#d8d8d8", "#292929");
      button.textContent = `${phase.phase} (${phase.count})`;
      button.addEventListener("click", () => {
        selectedLogPhase = phase.phase;
        renderLogPhaseTabs();
        void refreshSelectedPhaseLog();
      });
      logPhaseTabs.appendChild(button);
    }
  }

  function renderSelectedPhaseLog(): void {
    if (!selectedLogPhase) {
      phaseLogDetail.textContent = "No phase selected.";
      return;
    }
    if (selectedPhaseLogEntries.length === 0) {
      phaseLogDetail.textContent = `No log entries yet for ${selectedLogPhase}.`;
      return;
    }
    phaseLogDetail.textContent = selectedPhaseLogEntries.map((entry) => formatLogEntry(entry)).join("\n\n");
  }

  function renderFocus(): void {
    const current = currentStepId ? workflowSteps.find((step) => step.id === currentStepId) : undefined;
    const currentTitle = current?.title || current?.id || "Waiting for run state";
    const currentState = current ? getStepState(current.id, current.enabled) : "idle";
    const nextStep = current
      ? getNextEnabledStep(current.id)
      : workflowSteps.find((step) => step.enabled);

    focusStep.textContent = currentTitle;
    focusDetail.textContent = currentSignalDetail || summarizeStepConfig(current || null);
    focusNext.textContent = nextStep?.title || nextStep?.id || "-";
    focusNextDetail.textContent = nextStep ? `Ready at ${nextStep.id}` : "No enabled follow-up step.";
    latestSignal.textContent = currentSignal || "Waiting for live signal";
    latestSignalDetail.textContent = currentSignalDetail || "The event stream will fill this in.";
    tokS.textContent = currentTokS;
    vram.textContent = currentVram;
    focusPanelTitle.textContent = currentTitle;
    focusPanelBody.textContent = currentSignalDetail || "The selected run will stream details here.";

    focusPanelGrid.innerHTML = [
      quickStateTile("State", currentState),
      quickStateTile("Resume target", resumeStep.value || "-"),
      quickStateTile("Log phase", selectedLogPhase || "-"),
      quickStateTile("Events", String(eventHistory.length)),
    ].join("");
  }

  async function apiGet<T>(url: string): Promise<T> {
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error(`API ${resp.status}: ${resp.statusText}`);
    }
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

  async function apiPut<T>(url: string, body: unknown): Promise<T> {
    const resp = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      throw new Error(`API ${resp.status}: ${resp.statusText}`);
    }
    return resp.json() as Promise<T>;
  }

  async function loadWorkflow(): Promise<void> {
    const response = await apiGet<WorkflowResponse>(`/api/projects/${projectId}/control/workflow`);
    replaceWorkflow(response.steps, false);
  }

  async function refreshLogs(): Promise<void> {
    try {
      const data = await apiGet<LogResponse>(`/api/projects/${projectId}/logs?limit=12`);
      phaseSummaries = data.phases;
      applyLogStateHints();
      renderLogPhaseTabs();
      if (!selectedLogPhase || !phaseSummaries.some((phase) => phase.phase === selectedLogPhase)) {
        selectedLogPhase = phaseSummaries[0]?.phase || selectedLogPhase;
      }
      await refreshSelectedPhaseLog(false);
      renderFocus();
    } catch (err: unknown) {
      phaseLogDetail.textContent = err instanceof Error ? err.message : "Failed to load logs.";
    }
  }

  async function refreshSelectedPhaseLog(showErrors = true): Promise<void> {
    if (!selectedLogPhase) {
      renderSelectedPhaseLog();
      return;
    }
    try {
      const response = await apiGet<PhaseLogResponse>(`/api/projects/${projectId}/logs/${selectedLogPhase}?limit=160`);
      selectedPhaseLogEntries = response.entries;
      renderSelectedPhaseLog();
    } catch (err: unknown) {
      if (showErrors) {
        phaseLogDetail.textContent = err instanceof Error ? err.message : "Failed to load phase log.";
      }
    }
  }

  async function loadEventHistory(): Promise<void> {
    try {
      const response = await apiGet<EventListResponse>(`/api/projects/${projectId}/events?limit=240`);
      eventHistory = response.events;
      if (followLiveDetail || selectedEventIndex < 0) {
        selectedEventIndex = eventHistory.length - 1;
      }
      renderEventTimeline();
      renderEventDetail();
    } catch (err: unknown) {
      if (eventHistory.length === 0) {
        eventDetail.innerHTML = `<div style="color: #8c8c8c; font-size: 13px;">${escapeHtml(err instanceof Error ? err.message : "Failed to load event history.")}</div>`;
      }
    }
  }

  function connectStream(): void {
    evtSource?.close();
    evtSource = new EventSource(`/api/projects/${projectId}/stream`);

    evtSource.onmessage = (event: MessageEvent): void => {
      if (event.data.startsWith(":")) {
        return;
      }

      let data: JsonRecord;
      try {
        data = JSON.parse(event.data) as JsonRecord;
      } catch {
        currentSignal = "Malformed stream event";
        currentSignalDetail = "A payload could not be parsed.";
        renderFocus();
        return;
      }

      eventHistory.push(data);
      if (eventHistory.length > 240) {
        eventHistory = eventHistory.slice(-240);
      }
      if (followLiveDetail || selectedEventIndex < 0) {
        selectedEventIndex = eventHistory.length - 1;
      }

      applyStreamEvent(data);
      renderEventTimeline();
      renderEventDetail();
      renderRunStrip();
      renderWorkflowBoard();
      renderFocus();
    };

    evtSource.onerror = (): void => {
      currentSignal = "Stream disconnected";
      currentSignalDetail = "Reconnecting in 3 seconds.";
      renderFocus();
      evtSource?.close();
      window.setTimeout(connectStream, 3000);
    };
  }

  function applyStreamEvent(entry: JsonRecord): void {
    const type = String(entry.type ?? "event");
    const phase = String(entry.name ?? entry.phase ?? entry.gate ?? "");
    currentSignal = describeEvent(entry);
    currentSignalDetail = eventNarrative(entry);

    if (entry.tok_s !== undefined) {
      currentTokS = typeof entry.tok_s === "number" ? entry.tok_s.toFixed(1) : String(entry.tok_s);
    }
    if (entry.vram !== undefined) {
      currentVram = typeof entry.vram === "number" ? `${entry.vram.toFixed(0)} MB` : String(entry.vram);
    }

    if (type === "run_started") {
      stepStatuses = {};
      currentStepId = String(entry.start_at ?? workflowSteps.find((step) => step.enabled)?.id ?? "");
      syncStepStateStore();
      return;
    }
    if (type === "run_complete") {
      if (currentStepId) {
        stepStatuses[currentStepId] = "done";
      }
      syncStepStateStore();
      return;
    }
    if (!phase) {
      return;
    }

    if (type === "phase_start") {
      currentStepId = phase;
      stepStatuses[phase] = "active";
      syncStepStateStore();
      return;
    }
    if (type === "phase_done") {
      currentStepId = phase;
      stepStatuses[phase] = "done";
      syncStepStateStore();
      return;
    }
    if (type === "phase_retry") {
      currentStepId = phase;
      stepStatuses[phase] = "active";
      syncStepStateStore();
      return;
    }
    if (type === "phase_error") {
      currentStepId = phase;
      stepStatuses[phase] = "error";
      syncStepStateStore();
      return;
    }
    if (type === "gate_opened") {
      currentStepId = phase;
      stepStatuses[phase] = "waiting";
      syncStepStateStore();
      return;
    }
    if (type === "gate_decided") {
      currentStepId = phase;
      stepStatuses[phase] = entry.decision === "approved" ? "done" : "error";
      syncStepStateStore();
      return;
    }
    if (type === "checkpoint") {
      currentStepId = phase;
      stepStatuses[phase] = "done";
      syncStepStateStore();
    }
  }

  function applyLogStateHints(): void {
    for (const phase of phaseSummaries) {
      if (stepStatuses[phase.phase] === "active" || stepStatuses[phase.phase] === "waiting" || stepStatuses[phase.phase] === "error") {
        continue;
      }
      if (phase.count === 0) {
        continue;
      }
      const level = String(phase.last_event?.level ?? "");
      stepStatuses[phase.phase] = level === "ERROR" ? "error" : "done";
    }
    syncStepStateStore();
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
        phase: instructionScope.value || null,
        instruction,
      });
      instructionInput.value = "";
      setStatus("Instruction queued.");
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
        start_at: resumeStep.value,
        instruction: instructionInput.value.trim() || null,
        compact_context: compactCheckbox.checked,
        max_chars: 18000,
      };
      const result = await apiPost<{ started: boolean; start_at: string }>(`/api/projects/${projectId}/control/resume`, payload);
      instructionInput.value = "";
      setStatus(result.started ? `Run resumed from ${result.start_at}.` : "A run is already active.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Resume failed", true);
    } finally {
      setBusy(btnResume, false, "Resume");
    }
  });

  btnBuildTeam.addEventListener("click", async () => {
    setBusy(btnBuildTeam, true, "Building...");
    try {
      const response = await apiPost<PersonaSynthesisResponse>(`/api/projects/${projectId}/control/personas/synthesize`, {});
      replaceWorkflow(response.steps, false);
      setStatus(`Built ${response.personas.length} personas.`);
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Team synthesis failed", true);
    } finally {
      setBusy(btnBuildTeam, false, "Build Team");
    }
  });

  btnAddCheckpoint.addEventListener("click", () => {
    const checkpoint = createCheckpointStep(workflowSteps);
    const deploymentIndex = workflowSteps.findIndex((step) => step.id === "deployment");
    const next = workflowSteps.map(cloneStep);
    const insertAt = deploymentIndex >= 0 ? deploymentIndex : next.length;
    next.splice(insertAt, 0, checkpoint);
    selectedWorkflowStepId = checkpoint.id;
    replaceWorkflow(next, true);
    setStatus("Checkpoint added locally. Save to persist.");
  });

  btnReloadWorkflow.addEventListener("click", async () => {
    setBusy(btnReloadWorkflow, true, "Reloading...");
    try {
      await loadWorkflow();
      setStatus("Workflow reloaded.");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Workflow reload failed", true);
    } finally {
      setBusy(btnReloadWorkflow, false, "Reload");
    }
  });

  async function saveWorkflowFromState(): Promise<void> {
    const response = await apiPut<WorkflowResponse>(`/api/projects/${projectId}/control/workflow`, { steps: workflowSteps });
    replaceWorkflow(response.steps, false);
  }

  btnSaveWorkflow.addEventListener("click", async () => {
    setBusy(btnSaveWorkflow, true, "Saving...");
    try {
      await saveWorkflowFromState();
      setStatus("Workflow updated.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Workflow save failed", true);
    } finally {
      setBusy(btnSaveWorkflow, false, "Save");
    }
  });

  btnSaveTeam.addEventListener("click", async () => {
    setBusy(btnSaveTeam, true, "Saving...");
    try {
      await saveWorkflowFromState();
      setStatus("Founding team saved.");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Team save failed", true);
    } finally {
      setBusy(btnSaveTeam, false, "Save Team");
    }
  });

  btnAddPersona.addEventListener("click", () => {
    const next = [...getPersonas(), {
      name: "New Persona",
      perspective: "State the perspective this role brings to the forum.",
      mandate: "Define what this role protects or pushes for.",
      turn_order: getPersonas().length + 1,
      veto_scope: "critical product or quality concerns",
    }];
    setPersonas(next);
    setStatus("Persona added locally. Save to persist.");
  });

  btnMemorySync.addEventListener("click", async () => {
    setBusy(btnMemorySync, true, "Syncing...");
    try {
      memoryState = await apiPost<MemoryResponse>(`/api/projects/${projectId}/memory/sync`, {});
      renderMemory();
      setStatus("Palace memory synced.");
      await refreshLogs();
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Memory sync failed", true);
    } finally {
      setBusy(btnMemorySync, false, "Sync Palace");
    }
  });

  btnMemoryWakeup.addEventListener("click", async () => {
    setBusy(btnMemoryWakeup, true, "Refreshing...");
    try {
      memoryState = await apiPost<MemoryResponse>(`/api/projects/${projectId}/memory/wake-up`, {});
      renderMemory();
      setStatus("Wake-up packet refreshed.");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Wake-up refresh failed", true);
    } finally {
      setBusy(btnMemoryWakeup, false, "Refresh Wake-Up");
    }
  });

  btnMemorySearch.addEventListener("click", async () => {
    const query = memoryQuery.value.trim();
    if (!query) {
      setStatus("Enter a memory query first.", true);
      return;
    }
    setBusy(btnMemorySearch, true, "Searching...");
    try {
      memoryState = await apiPost<MemoryResponse>(`/api/projects/${projectId}/memory/search`, {
        query,
        room: memoryRoom.value.trim() || null,
        results: 5,
      });
      renderMemory();
      setStatus("Palace search complete.");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Memory search failed", true);
    } finally {
      setBusy(btnMemorySearch, false, "Search Palace");
    }
  });

  btnFollowLive.addEventListener("click", () => {
    followLiveDetail = true;
    selectedEventIndex = eventHistory.length - 1;
    renderEventTimeline();
    renderEventDetail();
  });

  workflowEditor.addEventListener("input", () => {
    setDirty(true);
  });

  workflowEditor.addEventListener("blur", () => {
    try {
      const parsed = JSON.parse(workflowEditor.value) as WorkflowStep[];
      replaceWorkflow(parsed, true);
      setStatus("Advanced JSON applied locally.");
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Workflow JSON is invalid.", true);
    }
  });

  connectStream();
  void loadWorkflow()
    .then(async () => {
      await loadEventHistory();
      await refreshLogs();
      await loadMemoryStatus();
    })
    .catch((err: unknown) => {
      setStatus(err instanceof Error ? err.message : "Failed to load workflow.", true);
    });

  refreshTimer = window.setInterval(() => {
    void refreshLogs();
    void loadMemoryStatus();
  }, 4000);

  window.addEventListener("hashchange", () => {
    evtSource?.close();
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
    }
  }, { once: true });
}

function cloneStep(step: WorkflowStep): WorkflowStep {
  return {
    ...step,
    config: { ...(step.config ?? {}) },
  };
}

function reorderSteps(steps: WorkflowStep[], sourceId: string, targetId: string): WorkflowStep[] {
  const next = steps.map(cloneStep);
  const sourceIndex = next.findIndex((step) => step.id === sourceId);
  const targetIndex = next.findIndex((step) => step.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0) {
    return next;
  }
  const [source] = next.splice(sourceIndex, 1);
  next.splice(targetIndex, 0, source);
  return next;
}

function createCheckpointStep(existing: WorkflowStep[]): WorkflowStep {
  let index = 1;
  while (existing.some((step) => step.id === `operator_checkpoint_${index}`)) {
    index += 1;
  }
  return {
    id: `operator_checkpoint_${index}`,
    title: `Operator Checkpoint ${index}`,
    type: "checkpoint",
    handler: "operator_checkpoint",
    enabled: true,
    description: "Pause here for user review, instruction injection, or fast-forward decisions.",
    config: {},
  };
}

function quickStateTile(label: string, value: string): string {
  return `
    <div style="padding: 9px; background: #101010; border: 1px solid #1d1d1d; border-radius: 8px;">
      <div style="font-size: 10px; color: #8c8c8c; text-transform: uppercase; letter-spacing: 0; margin-bottom: 4px;">${escapeHtml(label)}</div>
      <div style="font-size: 12px; color: #f2f2f2; font-weight: 600;">${escapeHtml(value)}</div>
    </div>
  `;
}

function getStepState(stepId: string, enabled: boolean): StepRunState {
  if (!enabled) {
    return "disabled";
  }
  return (window as unknown as { __guildrStepStates?: Record<string, StepRunState> }).__guildrStepStates?.[stepId]
    || localStepState(stepId)
    || "idle";
}

function localStepState(stepId: string): StepRunState | null {
  const stateStore = (window as unknown as { __guildrStepStates?: Record<string, StepRunState> }).__guildrStepStates;
  return stateStore?.[stepId] ?? null;
}

function statePalette(state: StepRunState): { background: string; border: string; text: string; muted: string; dot: string } {
  const palette: Record<StepRunState, { background: string; border: string; text: string; muted: string; dot: string }> = {
    idle:     { background: "#0e0e0e", border: "#242424", text: "#f0f0f0", muted: "#8c8c8c", dot: "#6a6a6a" },
    active:   { background: "#101b2d", border: "#26456d", text: "#f0f7ff", muted: "#9fc4e6", dot: "#8fd3ff" },
    done:     { background: "#0f1813", border: "#26533e", text: "#f0fff6", muted: "#96d7b4", dot: "#7de5b1" },
    waiting:  { background: "#1a1409", border: "#5d4520", text: "#fff6e8", muted: "#f0c36f", dot: "#f0c36f" },
    error:    { background: "#210f12", border: "#6d2d39", text: "#fff0f2", muted: "#ff9cab", dot: "#ff7a7a" },
    disabled: { background: "#0a0a0a", border: "#1d1d1d", text: "#8c8c8c", muted: "#676767", dot: "#454545" },
  };
  return palette[state];
}

function describeEvent(data: JsonRecord): string {
  const type = String(data.type ?? "event");
  const name = String(data.name ?? data.phase ?? data.gate ?? "");
  const attempt = data.attempt;
  const error = data.error;
  if (type === "run_started") {
    const mode = data.dry_run ? "dry-run" : "live";
    const startAt = data.start_at ? ` from ${String(data.start_at)}` : "";
    return `Run started (${mode}${startAt})`;
  }
  if (type === "run_complete") { return "Run complete"; }
  if (type === "run_error") { return `Run failed: ${String(error ?? "unknown error")}`; }
  if (type === "phase_start") { return `Entering ${name}${attempt ? ` (retry ${String(attempt)})` : ""}`; }
  if (type === "phase_done") { return `Completed ${name}`; }
  if (type === "phase_retry") { return `Retrying ${name} (${String(attempt ?? "?")})`; }
  if (type === "phase_error") { return `${name} failed: ${String(error ?? "error")}`; }
  if (type === "gate_opened") { return `Gate opened: ${name}`; }
  if (type === "gate_decided") { return `Gate ${name}: ${data.decision === "approved" ? "approved" : "rejected"}`; }
  if (type === "checkpoint") { return `Checkpoint reached: ${name}`; }
  return typeof data.message === "string" ? data.message : type;
}

function eventNarrative(data: JsonRecord): string {
  const type = String(data.type ?? "event");
  const attempt = data.attempt ? ` Attempt ${String(data.attempt)}.` : "";
  const error = typeof data.error === "string" ? ` ${data.error}` : "";
  if (type === "phase_error") { return `The current phase reported an error.${attempt}${error}`.trim(); }
  if (type === "phase_retry") { return `The framework scheduled another pass for this phase.${attempt}`.trim(); }
  if (type === "gate_opened") { return "A decision gate is now waiting for operator input."; }
  if (type === "gate_decided") { return `The gate closed with decision '${String(data.decision ?? "unknown")}'.`; }
  if (type === "run_started") { return "A new run was launched and the control room is now following it live."; }
  if (type === "run_complete") { return "The enabled workflow completed without another blocking event."; }
  if (typeof data.message === "string" && data.message.trim()) { return data.message.trim(); }
  return describeEvent(data);
}

function formatLogEntry(entry: JsonRecord): string {
  const timestamp = readableTime(entry.ts);
  const level = String(entry.level ?? "INFO");
  const message = typeof entry.message === "string"
    ? entry.message
    : typeof entry.event === "string"
      ? entry.event
      : JSON.stringify(entry);
  const extra = Object.fromEntries(Object.entries(entry).filter(([key]) => !["ts", "level", "message", "event"].includes(key)));
  const suffix = Object.keys(extra).length > 0 ? `\n${JSON.stringify(extra, null, 2)}` : "";
  return `[${timestamp}] [${level}] ${message}${suffix}`;
}

function readableTime(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleTimeString();
    }
  }
  return new Date().toLocaleTimeString();
}

function summarizeStepConfig(step: WorkflowStep | null): string {
  if (!step) { return "No active step yet."; }
  if (step.description && step.description.trim()) { return step.description.trim(); }
  const config = step.config ?? {};
  if (step.id === "persona_forum") {
    const personas = Array.isArray(config.personas) ? config.personas.length : 0;
    const mode = config.auto_generate === false ? "manual persona roster" : "auto-build persona roster";
    return `${mode}; ${personas} personas configured.`;
  }
  if (step.id === "guru_escalation") {
    const providers = Array.isArray(config.providers) ? config.providers.join(", ") : "configured providers";
    return `Escalation advisors: ${providers}.`;
  }
  const keys = Object.keys(config);
  if (keys.length > 0) { return `Config keys: ${keys.join(", ")}`; }
  return "No extra config yet.";
}

function getPersonasFromStep(step: WorkflowStep | undefined): Persona[] {
  const raw = step?.config?.personas;
  if (!Array.isArray(raw)) { return []; }
  return raw.map((item, index) => normalizePersona(item, index));
}

function normalizePersona(item: unknown, index: number): Persona {
  const record = typeof item === "object" && item !== null ? item as JsonRecord : {};
  return {
    name: String(record.name ?? `Persona ${index + 1}`),
    perspective: String(record.perspective ?? ""),
    mandate: String(record.mandate ?? ""),
    turn_order: Number(record.turn_order ?? index + 1) || index + 1,
    veto_scope: String(record.veto_scope ?? ""),
  };
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function tabStyle(active: boolean): string {
  return `padding: 10px 16px; background: none; border: none; border-bottom: 2px solid ${active ? "#8fd3ff" : "transparent"}; color: ${active ? "#8fd3ff" : "#8c8c8c"}; cursor: pointer; font-size: 13px; white-space: nowrap;`;
}

function actionButton(background: string, color: string, bold = false): string {
  return `padding: 9px 12px; background: ${background}; color: ${color}; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;${bold ? " font-weight: 600;" : ""}`;
}

function miniButtonStyle(background: string, color: string, border = "transparent"): string {
  return `padding: 6px 10px; background: ${background}; color: ${color}; border: 1px solid ${border}; border-radius: 6px; cursor: pointer; font-size: 12px;`;
}

function selectStyle(): string {
  return "padding: 8px 10px; background: #090909; color: #f1f1f1; border: 1px solid #2d2d2d; border-radius: 6px; font-size: 13px;";
}

function inputStyle(): string {
  return "width: 100%; padding: 9px; box-sizing: border-box; background: #090909; color: #f1f1f1; border: 1px solid #2d2d2d; border-radius: 6px; font-size: 13px;";
}

function textAreaStyle(fontSize = "13px", fontFamily = "inherit"): string {
  return `width: 100%; padding: 9px; box-sizing: border-box; background: #090909; color: #f1f1f1; border: 1px solid #2d2d2d; border-radius: 6px; resize: vertical; font-size: ${fontSize}; font-family: ${fontFamily}; line-height: 1.5;`;
}

function eventPalette(type: string): { background: string; border: string; dot: string } {
  if (type.includes("error") || type.includes("fail")) {
    return { background: "#170d10", border: "#4f2330", dot: "#ff7a7a" };
  }
  if (type.includes("done") || type.includes("complete") || type.includes("approved")) {
    return { background: "#0d1612", border: "#244734", dot: "#7de5b1" };
  }
  if (type.includes("gate") || type.includes("checkpoint")) {
    return { background: "#181308", border: "#4e3d17", dot: "#f0c36f" };
  }
  return { background: "#0d131c", border: "#223653", dot: "#8fd3ff" };
}

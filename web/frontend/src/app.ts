/**
 * Orchestrator PWA — main application entry point.
 *
 * Hash-based routing, module-level store, vanilla TS views.
 */

import { renderNewProject } from "./views/NewProject.js";
import { renderQuiz } from "./views/Quiz.js";
import { renderProgress } from "./views/Progress.js";
import { renderGate } from "./views/Gate.js";
import { renderArtifacts } from "./views/Artifacts.js";

// -- hash-based router -------------------------------------------------------

type Route = { view: string; params: Record<string, string> };

function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "") || "/";
  const parts = path.split("/").filter(Boolean);

  if (parts[0] === "project" && parts.length >= 2) {
    return {
      view: `project/${parts[1]}`,
      params: { id: parts[1], ...(parts[2] ? { sub: parts[2] } : {}) },
    };
  }

  return { view: parts[0] || "projects", params: {} };
}

function navigate(route: string): void {
  window.location.hash = route;
}

// Several view templates use inline onclick="navigate(...)" handlers, which
// run in the global scope and can't see the module-local `navigate` symbol.
// Expose it on window so those handlers actually work.
(window as unknown as { navigate: typeof navigate }).navigate = navigate;
(window as unknown as { _navigate: typeof navigate }) ._navigate = navigate;

// -- API client --------------------------------------------------------------

const API_BASE = "";

async function apiGet(url: string): Promise<unknown> {
  const resp = await fetch(`${API_BASE}${url}`);
  if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
  return resp.json();
}

async function apiPost(url: string, body: unknown): Promise<unknown> {
  const resp = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
  return resp.json();
}

// -- module-level store ------------------------------------------------------

interface AppState {
  currentView: string;
  selectedProject: string | null;
}

const state: AppState = {
  currentView: "projects",
  selectedProject: null,
};

const stateChangeListeners: Set<() => void> = new Set();

function setState(partial: Partial<AppState>): void {
  Object.assign(state, partial);
  for (const listener of stateChangeListeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  stateChangeListeners.add(listener);
  return () => stateChangeListeners.delete(listener);
}

// -- view rendering ----------------------------------------------------------

function render(): void {
  const app = document.getElementById("app");
  if (!app) return;

  const { view, params } = parseHash(window.location.hash);
  setState({ currentView: view, selectedProject: params.id || null });

  // Full view dispatcher — Task 8
  switch (view) {
    case "":
    case "projects":
      renderProjectsList(app);
      break;
    case "new-project":
      renderNewProjectView(app);
      break;
    default:
      if (view.startsWith("project/")) {
        renderProjectView(app, view, params);
      } else {
        renderNotFound(app, view);
      }
  }
}

function renderProjectView(container: Element, view: string, params: Record<string, string>): void {
  const projectId = params.id || "unknown";
  const sub = params.sub || "";

  switch (sub) {
    case "quiz":
      renderQuiz(container, navigate, projectId);
      break;
    case "progress":
      renderProgress(container, navigate, projectId);
      break;
    case "gate":
      renderGate(container, navigate, projectId, params.id || "");
      break;
    case "artifacts":
      renderArtifacts(container, navigate, projectId, params.sub ? params.sub : undefined);
      break;
    default:
      renderProjectDetail(container, params);
      break;
  }
}

function renderNewProjectView(container: Element): void {
  renderNewProject(container, navigate);
}

function renderProjectsList(container: Element): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <h1 style="font-size: 20px;">guildr</h1>
    </header>
    <main style="padding: 16px;">
      <button
        class="tap-target"
        onclick="navigate('#new-project')"
        style="width: 100%; padding: 12px; margin-bottom: 16px;
               background: #0f3460; color: white; border: none;
               border-radius: 8px; font-size: 16px; cursor: pointer;"
      >
        + New Project
      </button>
      <div id="project-list">
        <p style="color: #888; text-align: center; padding: 32px 0;">
          Loading...
        </p>
      </div>
    </main>
  `;
  loadProjectsList(container);
}

async function loadProjectsList(container: Element): Promise<void> {
  const listEl = container.querySelector("#project-list") as HTMLDivElement;
  try {
    const resp = await apiGet("/api/projects") as {
      projects: Array<{
        id: string; name: string; current_phase: string | null; created_at: string;
      }>;
    };
    const projects = resp.projects;

    if (projects.length === 0) {
      listEl.innerHTML = `<p style="color: #888; text-align: center; padding: 32px 0;">
        No projects yet. Create one to get started.
      </p>`;
      return;
    }

    listEl.innerHTML = "";
    for (const proj of projects) {
      const div = document.createElement("div");
      div.style.cssText = "margin-bottom: 8px; padding: 12px; background: #16213e; border-radius: 8px; cursor: pointer;";
      div.innerHTML = `
        <div style="font-size: 15px; font-weight: 600; margin-bottom: 4px;">${escapeHtml(proj.name)}</div>
        <div style="font-size: 13px; color: #888;">
          ${proj.current_phase ? "Phase: " + proj.current_phase : "Not started"} · ${formatRelative(proj.created_at)}
        </div>
      `;
      div.addEventListener("click", () => navigate(`#project/${proj.id}`));
      listEl.appendChild(div);
    }
  } catch (err: unknown) {
    listEl.innerHTML = `<p style="color: #e74c3c; text-align: center; padding: 32px 0;">
      Failed to load projects: ${err instanceof Error ? err.message : "Unknown error"}
    </p>`;
  }
}

function renderProjectDetail(container: Element, params: Record<string, string>): void {
  const projectId = params.id || "unknown";
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <button
        onclick="navigate('#projects')"
        style="background: none; border: none; color: #4fc3f7;
               font-size: 14px; cursor: pointer; padding: 8px 0;"
      >
        ← Back
      </button>
      <h1 style="font-size: 18px; margin-top: 8px;">Project ${escapeHtml(projectId)}</h1>
    </header>
    <main style="padding: 16px;">
      <div id="project-info" style="margin-bottom: 24px;">
        <p style="color: #888;">Loading project info...</p>
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <button class="tap-target" id="btn-progress" style="width: 100%; padding: 14px; background: #0f3460; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer;">
            Progress
        </button>
        <button class="tap-target" id="btn-gates" style="width: 100%; padding: 14px; background: #0f3460; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer;">
            Gates
        </button>
        <button class="tap-target" id="btn-artifacts" style="width: 100%; padding: 14px; background: #0f3460; color: white; border: none; border-radius: 8px; font-size: 16px; cursor: pointer;">
            Artifacts
        </button>
        <button class="tap-target" id="btn-start" style="width: 100%; padding: 14px; background: #4fc3f7; color: #0a0a0a; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; font-weight: 600;">
            Start Run
        </button>
      </div>
    </main>
  `;

  loadProjectInfo(container, projectId);

  const btnProgress = container.querySelector("#btn-progress") as HTMLButtonElement;
  const btnGates = container.querySelector("#btn-gates") as HTMLButtonElement;
  const btnArtifacts = container.querySelector("#btn-artifacts") as HTMLButtonElement;
  const btnStart = container.querySelector("#btn-start") as HTMLButtonElement;

  btnProgress.addEventListener("click", () => navigate(`#project/${projectId}/progress`));
  btnGates.addEventListener("click", () => navigate(`#project/${projectId}/gates`));
  btnArtifacts.addEventListener("click", () => navigate(`#project/${projectId}/artifacts`));
  btnStart.addEventListener("click", async () => {
    btnStart.disabled = true;
    btnStart.textContent = "Starting...";
    try {
      await apiPost(`/api/projects/${projectId}/start`, {});
      btnStart.textContent = "Run Started!";
      setTimeout(() => navigate(`#project/${projectId}/progress`), 1000);
    } catch (err: unknown) {
      btnStart.textContent = "Start Run";
      btnStart.disabled = false;
      alert(err instanceof Error ? err.message : "Failed to start run");
    }
  });
}

async function loadProjectInfo(container: Element, projectId: string): Promise<void> {
  const infoEl = container.querySelector("#project-info") as HTMLDivElement;
  try {
    const proj = await apiGet(`/api/projects/${projectId}`) as {
      name: string; current_phase: string | null; created_at: string;
    };

    infoEl.innerHTML = `
      <div style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">${escapeHtml(proj.name)}</div>
      <div style="font-size: 14px; color: #888;">
        ${proj.current_phase ? "Current phase: " + proj.current_phase : "No active phase"}
      </div>
    `;
  } catch (err: unknown) {
    infoEl.innerHTML = `<p style="color: #e74c3c;">Failed to load: ${err instanceof Error ? err.message : "Unknown error"}</p>`;
  }
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatRelative(iso: string): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diffSec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return new Date(t).toLocaleDateString();
}

function renderNotFound(container: Element, view: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <h1 style="font-size: 20px;">guildr</h1>
    </header>
    <main style="padding: 16px; text-align: center;">
      <h2 style="margin-bottom: 16px;">Not Found</h2>
      <p style="color: #888;">View: ${view}</p>
      <button
        onclick="navigate('#projects')"
        style="margin-top: 16px; padding: 12px 24px;
               background: #0f3460; color: white; border: none;
               border-radius: 8px; font-size: 16px; cursor: pointer;"
      >
        Go Home
      </button>
    </main>
  `;
}

// -- initialization ----------------------------------------------------------

window.addEventListener("hashchange", render);
render();

// Export for testing and view modules
export { navigate, apiGet, apiPost, state, setState, subscribe, render };

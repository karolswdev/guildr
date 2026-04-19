/**
 * Orchestrator PWA — main application entry point.
 *
 * Hash-based routing, module-level store, vanilla TS views.
 */

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

  // Simple view dispatcher — full views implemented in Task 8
  switch (view) {
    case "":
    case "projects":
      renderProjectsList(app);
      break;
    case "project":
      renderProjectDetail(app, params);
      break;
    default:
      renderNotFound(app, view);
  }
}

function renderProjectsList(container: Element): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <h1 style="font-size: 20px;">Orchestrator</h1>
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
          No projects yet. Create one to get started.
        </p>
      </div>
    </main>
  `;
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
      <h1 style="font-size: 18px; margin-top: 8px;">Project ${projectId}</h1>
    </header>
    <main style="padding: 16px;">
      <p style="color: #888;">Project detail view — loading...</p>
    </main>
  `;
}

function renderNotFound(container: Element, view: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <h1 style="font-size: 20px;">Orchestrator</h1>
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

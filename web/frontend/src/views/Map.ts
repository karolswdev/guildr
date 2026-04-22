import { AssetManager } from "../game/assets/AssetManager.js";
import { EventEngine } from "../game/EventEngine.js";
import { GameShell, type ProjectBrief } from "../game/GameShell.js";
import type { WorkflowStep } from "../game/types.js";

type WorkflowResponse = {
  project_id: string;
  steps: WorkflowStep[];
};

export function renderMap(
  container: Element,
  navigate: (route: string) => void,
  projectId: string,
  assetManager: AssetManager,
): void {
  container.innerHTML = `
    <section style="position: fixed; inset: 0; display: grid; place-items: center; background: #0D0F14; color: #E8EAF0; padding: 16px;">
      <div style="display: grid; gap: 8px; text-align: center;">
        <div style="font-size: 14px; font-weight: 700;">Loading orchestration map</div>
        <div id="map-load-status" style="font-size: 12px; color: #7A7E92;">Fetching workflow</div>
      </div>
    </section>
  `;
  const status = container.querySelector("#map-load-status") as HTMLDivElement;
  let shell: GameShell | null = null;

  void Promise.all([loadWorkflow(projectId), loadProjectBrief(projectId)])
    .then(([workflow, projectBrief]) => {
      const engine = new EventEngine(projectId, workflow);
      shell = new GameShell(container, {
        projectId,
        workflow,
        projectBrief,
        engine,
        assetManager,
        navigate,
      });
    })
    .catch((err: unknown) => {
      status.textContent = err instanceof Error ? err.message : "Map failed to load.";
      status.style.color = "#ffd0d7";
    });

  window.addEventListener("hashchange", () => {
    shell?.dispose();
  }, { once: true });
}

async function loadWorkflow(projectId: string): Promise<WorkflowStep[]> {
  const response = await fetch(`/api/projects/${projectId}/control/workflow`);
  if (!response.ok) {
    throw new Error(`Workflow ${response.status}: ${response.statusText}`);
  }
  const payload = await response.json() as WorkflowResponse;
  return payload.steps;
}

async function loadProjectBrief(projectId: string): Promise<ProjectBrief | null> {
  const response = await fetch(`/api/projects/${projectId}/brief`);
  if (!response.ok) {
    return null;
  }
  return response.json() as Promise<ProjectBrief>;
}

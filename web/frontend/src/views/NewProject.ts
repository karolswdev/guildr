/**
 * NewProject view — create project with quiz or paste qwendea.md.
 */

export function renderNewProject(container: Element, navigate: (route: string) => void): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <h1 style="font-size: 20px;">New Project</h1>
    </header>
    <main style="padding: 16px;">
      <div style="margin-bottom: 24px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 600;">Project Name</label>
        <input
          id="project-name"
          type="text"
          placeholder="My Project"
          style="width: 100%; padding: 12px; background: #16213e;
                 border: 1px solid #333; border-radius: 8px;
                 color: white; font-size: 16px;"
        />
      </div>

      <div style="margin-bottom: 24px;">
        <label style="display: block; margin-bottom: 8px; font-weight: 600;">
          Initial Idea (optional — leave blank for quiz)
        </label>
        <textarea
          id="initial-idea"
          rows="4"
          placeholder="Describe your project idea..."
          style="width: 100%; padding: 12px; background: #16213e;
                 border: 1px solid #333; border-radius: 8px;
                 color: white; font-size: 16px; resize: vertical;"
        ></textarea>
      </div>

      <button
        id="create-project-btn"
        class="tap-target"
        style="width: 100%; padding: 14px; background: #0f3460;
               color: white; border: none; border-radius: 8px;
               font-size: 16px; cursor: pointer;"
      >
        Create Project
      </button>

      <div id="create-error" style="color: #e74c3c; margin-top: 12px; display: none;"></div>
    </main>
  `;

  const btn = container.querySelector("#create-project-btn") as HTMLButtonElement;
  const errorEl = container.querySelector("#create-error") as HTMLDivElement;

  btn.addEventListener("click", async () => {
    const name = (container.querySelector("#project-name") as HTMLInputElement).value.trim();
    const idea = (container.querySelector("#initial-idea") as HTMLTextAreaElement).value.trim();

    if (!name) {
      errorEl.textContent = "Project name is required.";
      errorEl.style.display = "block";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Creating...";

    try {
      const resp = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, initial_idea: idea || undefined }),
      });

      if (!resp.ok) {
        throw new Error(`Failed to create project: ${resp.status}`);
      }

      const data = await resp.json();
      const route = data.needs_quiz
        ? `#project/${data.id}/quiz`
        : `#project/${data.id}`;
      navigate(route);
    } catch (err: unknown) {
      errorEl.textContent = err instanceof Error ? err.message : "Unknown error";
      errorEl.style.display = "block";
    } finally {
      btn.disabled = false;
      btn.textContent = "Create Project";
    }
  });
}

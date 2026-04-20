/**
 * Artifacts view — file tree + markdown/code viewer.
 */

export function renderArtifacts(container: Element, navigate: (route: string) => void, projectId: string, fileName?: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <button
        onclick="navigate('#project/${projectId}')"
        style="background: none; border: none; color: #4fc3f7;
               font-size: 14px; cursor: pointer; padding: 8px 0;"
      >
        ← Back
      </button>
      <h1 style="font-size: 18px; margin-top: 8px;">Artifacts</h1>
    </header>
    <main style="padding: 16px;">
      <div style="display: flex; gap: 16px;">
        <!-- File tree sidebar -->
        <div
          id="file-tree"
          style="flex: 0 0 220px; max-height: 60vh; overflow-y: auto;
                 background: #16213e; border-radius: 8px; padding: 12px;"
        >
          <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #888;">Files</div>
          <div id="tree-content">
            <div style="color: #888; font-size: 13px; padding: 8px 0;">Loading...</div>
          </div>
        </div>

        <!-- File content viewer -->
        <div style="flex: 1; min-width: 0;">
          <div id="file-header" style="display: none; margin-bottom: 12px; font-size: 14px; font-weight: 600;"></div>
          <div
            id="file-content"
            style="background: #0a0a0a; border-radius: 8px; padding: 16px;
                   overflow: auto; font-size: 14px; line-height: 1.6;
                   white-space: pre; max-height: 60vh; tab-size: 2;
                   font-family: ui-monospace, SFMono-Regular, Menlo, Monaco,
                   Consolas, 'Liberation Mono', monospace;"
          >
            <span style="color: #888;">Select a file to view.</span>
          </div>
        </div>
      </div>
    </main>
  `;

  const treeContent = container.querySelector("#tree-content") as HTMLDivElement;
  const fileHeader = container.querySelector("#file-header") as HTMLDivElement;
  const fileContent = container.querySelector("#file-content") as HTMLDivElement;

  // -- load file tree --------------------------------------------------------

  async function loadTree(): Promise<void> {
    try {
      const resp = await fetch(`/api/projects/${projectId}/tree`);
      if (!resp.ok) {
        treeContent.innerHTML = '<div style="color: #888; font-size: 13px; padding: 8px 0;">No files yet.</div>';
        return;
      }
      const files = await resp.json() as Array<{ path: string; is_dir: boolean }>;
      renderTree(files);

      // Auto-select first artifact if fileName specified
      if (fileName) {
        const file = files.find(f => f.path === fileName);
        if (file) {
          loadFile(fileName);
          return;
        }
      }

      // Default: show qwendea.md if it exists
      const qwendea = files.find(f => f.path === "qwendea.md");
      if (qwendea) {
        loadFile("qwendea.md");
      }
    } catch (err: unknown) {
      treeContent.innerHTML = `<div style="color: #e74c3c; font-size: 13px; padding: 8px 0;">Failed to load: ${err instanceof Error ? err.message : "Unknown error"}</div>`;
    }
  }

  function renderTree(files: Array<{ path: string; is_dir: boolean }>): void {
    treeContent.innerHTML = "";

    for (const file of files) {
      const div = document.createElement("div");
      const indent = (file.path.split("/").length - 1) * 16;

      if (file.is_dir) {
        div.style.cssText = `padding: 6px ${indent + 8}px; cursor: pointer; font-size: 13px; color: #4fc3f7;`;
        div.textContent = "📁 " + file.path.split("/").pop();
      } else {
        div.style.cssText = `padding: 6px ${indent + 8}px; cursor: pointer; font-size: 13px; color: #ccc;`;
        const icon = isMarkdown(file.path) ? "📝" : isSource(file.path) ? "💻" : "📄";
        div.textContent = `${icon} ${file.path.split("/").pop()}`;

        div.addEventListener("click", () => loadFile(file.path));

        // Highlight active file
        if (fileName === file.path) {
          div.style.background = "#0f3460";
          div.style.borderRadius = "4px";
        }
      }

      treeContent.appendChild(div);
    }
  }

  async function loadFile(path: string): Promise<void> {
    try {
      fileHeader.style.display = "block";
      fileHeader.textContent = path;

      const resp = await fetch(`/api/projects/${projectId}/artifacts/${encodeURIComponent(path)}`);
      if (!resp.ok) throw new Error(`Failed to load: ${resp.status}`);

      const content = await resp.text();
      fileContent.textContent = decodeArtifactContent(content);
    } catch (err: unknown) {
      fileContent.innerHTML = `<span style="color: #e74c3c;">${err instanceof Error ? err.message : "Unknown error"}</span>`;
    }
  }

  // -- helpers ----------------------------------------------------------------

  function isMarkdown(path: string): boolean {
    return path.endsWith(".md");
  }

  function isSource(path: string): boolean {
    return /\.(ts|js|py|toml|yaml|yml|json|html|css|sh)$/.test(path);
  }

  function decodeArtifactContent(content: string): string {
    const trimmed = content.trim();
    if (trimmed.startsWith("\"") && trimmed.endsWith("\"")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === "string") return parsed;
      } catch {
        // Fall through to raw content.
      }
    }
    return content;
  }

  loadTree();
}

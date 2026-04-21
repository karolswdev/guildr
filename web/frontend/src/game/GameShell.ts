import * as THREE from "three";
import { AssetManager } from "./assets/AssetManager.js";
import { EventEngine } from "./EventEngine.js";
import { SceneManager, type SpatialViewLevel } from "./SceneManager.js";
import type { EngineSnapshot, WorkflowStep } from "./types.js";

type GameShellOptions = {
  projectId: string;
  workflow: WorkflowStep[];
  engine: EventEngine;
  assetManager: AssetManager;
  navigate: (route: string) => void;
};

type ComposeAction = "shape" | "interject" | "intercept";

export class GameShell {
  private readonly root = document.createElement("section");
  private readonly canvas = document.createElement("canvas");
  private readonly topbar = document.createElement("div");
  private readonly bottomHud = document.createElement("div");
  private readonly actionRing = document.createElement("div");
  private readonly composeDock = document.createElement("div");
  private readonly timelineRibbon = document.createElement("div");
  private renderer: THREE.WebGLRenderer | null = null;
  private sceneManager: SceneManager | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private frame = 0;
  private unsubscribeSnapshot: (() => void) | null = null;
  private unsubscribeEvent: (() => void) | null = null;
  private disposed = false;
  private lastSnapshot: EngineSnapshot | null = null;
  private selectedAtomId = "";
  private selectedScope = "";
  private composeAction: ComposeAction = "interject";
  private timelineHideTimer = 0;
  private viewLevel: SpatialViewLevel = "global";

  constructor(private readonly container: Element, private readonly options: GameShellOptions) {
    this.mountShell();
    void this.start();
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.options.engine.close();
    this.unsubscribeSnapshot?.();
    this.unsubscribeEvent?.();
    if (this.frame) {
      cancelAnimationFrame(this.frame);
    }
    if (this.timelineHideTimer) {
      window.clearTimeout(this.timelineHideTimer);
    }
    this.resizeObserver?.disconnect();
    this.sceneManager?.dispose();
    this.renderer?.dispose();
    this.root.remove();
  }

  private mountShell(): void {
    this.container.innerHTML = "";
    this.root.style.cssText = [
      "position: fixed",
      "inset: 0",
      "overflow: hidden",
      "background: #0D0F14",
      "color: #E8EAF0",
      "font-family: Inter, system-ui, sans-serif",
      "--glass: rgba(13, 15, 20, 0.72)",
      "--line: #2A3042",
    ].join("; ");
    this.canvas.style.cssText = "position: absolute; inset: 0; width: 100%; height: 100%; touch-action: none; display: block;";
    this.topbar.dataset.role = "map-topbar";
    this.topbar.style.cssText = [
      "position: absolute",
      "left: 0",
      "right: 0",
      "top: 0",
      "z-index: 4",
      "height: 56px",
      "padding: max(8px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) 0 max(12px, env(safe-area-inset-left))",
      "display: grid",
      "grid-template-columns: 44px 1fr 44px",
      "align-items: center",
      "pointer-events: none",
    ].join("; ");
    this.topbar.innerHTML = `
      <button data-action="back" aria-label="Back" style="${glassButtonStyle()}">Back</button>
      <button data-action="live-pill" data-role="map-status" style="${statusPillStyle()}">
        <span style="width: 8px; height: 8px; border-radius: 999px; background: #41C7C7; box-shadow: 0 0 14px rgba(65,199,199,0.72);"></span>
        <span data-role="status-text">LOADING</span>
      </button>
      <span></span>
    `;

    this.bottomHud.dataset.role = "bottom-chip-cluster";
    this.bottomHud.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: max(14px, env(safe-area-inset-bottom))",
      "z-index: 4",
      "transform: translateX(-50%)",
      "max-width: calc(100vw - 24px)",
      "min-height: 54px",
      "display: flex",
      "gap: 8px",
      "align-items: center",
      "overflow-x: auto",
      "scrollbar-width: none",
      "padding: 7px",
      "border: 1px solid var(--line)",
      "border-radius: 999px",
      "background: rgba(13,15,20,0.74)",
      "box-shadow: 0 18px 42px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.05)",
      "backdrop-filter: blur(14px)",
      "pointer-events: auto",
    ].join("; ");

    this.actionRing.dataset.role = "radial-action-ring";
    this.actionRing.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(86px, env(safe-area-inset-bottom) + 86px))",
      "z-index: 5",
      "display: none",
      "width: min(310px, calc(100vw - 28px))",
      "height: 128px",
      "transform: translateX(-50%)",
      "pointer-events: auto",
    ].join("; ");

    this.composeDock.dataset.role = "compose-dock";
    this.composeDock.style.cssText = [
      "position: absolute",
      "left: max(12px, env(safe-area-inset-left))",
      "right: max(12px, env(safe-area-inset-right))",
      "bottom: max(12px, env(safe-area-inset-bottom))",
      "z-index: 5",
      "display: none",
      "max-height: 25vh",
      "overflow: hidden",
      "padding: 10px",
      "border: 1px solid var(--line)",
      "border-radius: 18px",
      "background: linear-gradient(180deg, rgba(21,26,40,0.94), rgba(12,15,24,0.96))",
      "box-shadow: 0 -20px 46px rgba(0,0,0,0.48), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.timelineRibbon.dataset.role = "timeline-ribbon";
    this.timelineRibbon.style.cssText = [
      "position: absolute",
      "left: max(12px, env(safe-area-inset-left))",
      "right: max(12px, env(safe-area-inset-right))",
      "top: calc(58px + env(safe-area-inset-top))",
      "z-index: 5",
      "display: none",
      "padding: 9px 10px",
      "border: 1px solid var(--line)",
      "border-radius: 999px",
      "background: rgba(13,15,20,0.76)",
      "box-shadow: 0 18px 42px rgba(0,0,0,0.32)",
      "backdrop-filter: blur(14px)",
      "pointer-events: auto",
    ].join("; ");

    this.root.appendChild(this.canvas);
    this.root.appendChild(this.topbar);
    this.root.appendChild(this.actionRing);
    this.root.appendChild(this.bottomHud);
    this.root.appendChild(this.composeDock);
    this.root.appendChild(this.timelineRibbon);
    this.container.appendChild(this.root);

    this.canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      this.sceneManager?.dispose();
      this.sceneManager = null;
      this.renderer?.dispose();
      this.renderer = null;
      if (this.frame) {
        cancelAnimationFrame(this.frame);
        this.frame = 0;
      }
      this.mountFallback();
    });
    this.root.addEventListener("pointerdown", (event) => this.handleEdgeGesture(event));
    (this.topbar.querySelector('[data-action="back"]') as HTMLButtonElement).addEventListener("click", () => this.options.navigate(`#project/${this.options.projectId}`));
    (this.topbar.querySelector('[data-action="live-pill"]') as HTMLButtonElement).addEventListener("click", () => {
      this.options.engine.resumeLive();
      this.focusActiveAtom();
    });
  }

  private async start(): Promise<void> {
    try {
      await this.options.assetManager.preloadCore();
      this.unsubscribeSnapshot = this.options.engine.onSnapshot((snapshot) => this.applySnapshot(snapshot));

      if (!canUseWebGL()) {
        this.mountFallback();
        await this.options.engine.init(this.options.projectId, this.options.workflow);
        return;
      }

      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: shouldPreserveDrawingBuffer(),
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.sceneManager = new SceneManager({
        canvas: this.canvas,
        renderer: this.renderer,
        workflow: this.options.workflow,
        assets: this.options.assetManager,
        onSelectAtom: (atomId) => this.openActionRing(atomId),
      });
      this.unsubscribeEvent = this.options.engine.onEvent((event, snapshot) => {
        this.sceneManager?.applyRunEvent(event, snapshot);
      });
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.root);
      this.resize();
      this.animate();
      void this.options.assetManager.loadDeferred().then(() => {
        this.sceneManager?.applyDeferredAssets(this.options.assetManager);
      }).catch(() => undefined);
      await this.options.engine.init(this.options.projectId, this.options.workflow);
    } catch {
      this.mountFallback();
      await this.options.engine.init(this.options.projectId, this.options.workflow).catch(() => undefined);
    }
  }

  private resize(): void {
    if (!this.renderer || !this.sceneManager) {
      return;
    }
    const rect = this.root.getBoundingClientRect();
    this.sceneManager.resize(Math.max(1, rect.width), Math.max(1, rect.height));
  }

  private animate = (): void => {
    if (this.disposed) {
      return;
    }
    this.sceneManager?.render(performance.now());
    this.frame = requestAnimationFrame(this.animate);
  };

  private applySnapshot(snapshot: EngineSnapshot): void {
    this.lastSnapshot = snapshot;
    this.sceneManager?.applySnapshot(snapshot);
    this.renderTopbar(snapshot);
    this.renderBottomHud(snapshot);
    this.renderTimeline(snapshot);
    if (this.actionRing.style.display !== "none") {
      this.renderActionRing();
    }
    if (this.composeDock.style.display !== "none") {
      this.renderComposeDock();
    }
  }

  private renderTopbar(snapshot: EngineSnapshot): void {
    const text = this.topbar.querySelector('[data-role="status-text"]') as HTMLSpanElement;
    text.textContent = snapshot.live ? "LIVE" : `REPLAY ${snapshot.replayIndex + 1}/${snapshot.historyLength}`;
  }

  private renderBottomHud(snapshot: EngineSnapshot): void {
    const active = activeAtom(snapshot);
    const total = Object.keys(snapshot.atoms).length;
    const done = Object.values(snapshot.atoms).filter((atom) => atom.state === "done").length;
    const remaining = snapshot.cost.remainingRunBudgetUsd !== null ? ` · ${formatUsd(snapshot.cost.remainingRunBudgetUsd)} left` : "";
    const unknown = snapshot.cost.unknownCostCount > 0 ? `<span title="Unknown costs" style="width: 8px; height: 8px; border-radius: 999px; background: #CC3333;"></span>` : "";
    this.bottomHud.innerHTML = `
      <button data-action="focus-active" style="${hudChipStyle("#E8EAF0")}"><span style="color: #41C7C7;">●</span>${escapeHtml(active?.id || "overview")}</button>
      <button data-view-level="global" aria-label="Global view" style="${viewChipStyle(this.viewLevel === "global")}">Run</button>
      <button data-view-level="cluster" aria-label="Loop cluster view" style="${viewChipStyle(this.viewLevel === "cluster")}">Loop</button>
      <button data-view-level="surface" aria-label="Object surface view" style="${viewChipStyle(this.viewLevel === "surface")}">Object</button>
      <button data-action="open-timeline" style="${hudChipStyle("#D9B84D")}">${done}/${total}</button>
      <button data-action="cost" style="${hudChipStyle("#D9B84D")}">${formatUsd(snapshot.cost.effectiveUsd)}${escapeHtml(remaining)}${unknown}</button>
      <div data-role="loop-dots" style="display: flex; gap: 4px; align-items: center; padding: 0 6px;">${loopDots(snapshot)}</div>
    `;
    (this.bottomHud.querySelector('[data-action="focus-active"]') as HTMLButtonElement).addEventListener("click", () => this.focusActiveAtom());
    (this.bottomHud.querySelector('[data-action="open-timeline"]') as HTMLButtonElement).addEventListener("click", () => this.showTimeline(3000));
    this.bottomHud.querySelectorAll<HTMLButtonElement>("[data-view-level]").forEach((button) => {
      button.addEventListener("click", () => this.setViewLevel(button.dataset.viewLevel as SpatialViewLevel));
    });
  }

  private renderTimeline(snapshot: EngineSnapshot): void {
    const max = Math.max(0, snapshot.historyLength - 1);
    this.timelineRibbon.innerHTML = `
      <input data-role="timeline-scrub" type="range" min="0" max="${max}" value="${snapshot.replayIndex >= 0 ? snapshot.replayIndex : max}" style="width: 100%; accent-color: #4D6FFF;" />
    `;
    (this.timelineRibbon.querySelector('[data-role="timeline-scrub"]') as HTMLInputElement).addEventListener("input", (event) => {
      const index = Number((event.currentTarget as HTMLInputElement).value);
      if (Number.isFinite(index)) {
        this.options.engine.scrubTo(index);
        this.showTimeline(3000);
      }
    });
  }

  private openActionRing(atomId: string): void {
    this.selectedAtomId = atomId;
    this.selectedScope = this.selectedScope || atomId;
    this.viewLevel = "surface";
    this.composeDock.style.display = "none";
    this.bottomHud.style.display = "none";
    this.actionRing.style.display = "block";
    this.sceneManager?.focusAtomInView(atomId, 0.36);
    this.renderActionRing();
  }

  private renderActionRing(): void {
    const atomId = this.selectedAtomId;
    const step = this.options.workflow.find((item) => item.id === atomId);
    this.actionRing.innerHTML = `
      <button data-action-command="shape" style="${ringButtonStyle("left: 0; top: 46px;", "#41C7C7")}">Shape</button>
      <button data-action-command="interject" style="${ringButtonStyle("left: 50%; top: 0; transform: translateX(-50%);", "#E8EAF0")}">Nudge</button>
      <button data-action-command="intercept" style="${ringButtonStyle("right: 0; top: 46px;", "#E09B2A")}">Intercept</button>
      <button data-action="ring-close" aria-label="Close" style="${ringCloseStyle()}">Close</button>
      <div style="position: absolute; left: 50%; bottom: 0; transform: translateX(-50%); min-width: 170px; max-width: 230px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px; background: rgba(13,15,20,0.74); color: #C7CAD6; font-size: 11px; font-weight: 800; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; backdrop-filter: blur(14px);">${escapeHtml(step?.title || atomId || "Object")}</div>
    `;
    this.actionRing.querySelectorAll<HTMLButtonElement>("[data-action-command]").forEach((button) => {
      button.addEventListener("click", () => this.openComposeDock(atomId, button.dataset.actionCommand as ComposeAction));
    });
    (this.actionRing.querySelector('[data-action="ring-close"]') as HTMLButtonElement).addEventListener("click", () => this.closeActionRing());
  }

  private openComposeDock(atomId: string, action: ComposeAction): void {
    this.selectedAtomId = atomId;
    this.selectedScope = this.selectedScope || atomId;
    this.composeAction = action;
    this.actionRing.style.display = "none";
    this.bottomHud.style.display = "none";
    this.composeDock.style.display = "grid";
    this.sceneManager?.focusAtomInView(atomId, 0.4);
    this.renderComposeDock();
  }

  private renderComposeDock(): void {
    const atomId = this.selectedAtomId;
    const step = this.options.workflow.find((item) => item.id === atomId);
    const textarea = this.composeDock.querySelector('[data-role="compose-draft"]') as HTMLTextAreaElement | null;
    const currentDraft = textarea?.value ?? "";
    this.composeDock.innerHTML = `
      <div style="display: grid; gap: 8px;">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 13px; font-weight: 850; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(step?.title || atomId || "Compose")}</div>
            <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase;">${this.composeAction} · live command</div>
          </div>
          <button data-action="dock-cancel" style="${ghostButtonStyle()}">Cancel</button>
        </div>
        <div data-role="scope-chips" style="display: flex; gap: 7px; overflow-x: auto; padding-bottom: 2px;">
          ${scopeChip("", "Whole run", this.selectedScope === "")}
          ${this.options.workflow.map((item) => scopeChip(item.id, item.title || item.id, this.selectedScope === item.id)).join("")}
        </div>
        <div style="display: grid; grid-template-columns: minmax(0, 1fr) 86px; gap: 8px; align-items: end;">
          <textarea data-role="compose-draft" rows="1" placeholder="${composePlaceholder(this.composeAction)}" style="width: 100%; min-height: 44px; max-height: calc(25vh - 108px); box-sizing: border-box; resize: none; border: 1px solid var(--line); border-radius: 999px; background: #10141E; color: #E8EAF0; padding: 11px 14px; font: 14px Inter, system-ui, sans-serif; line-height: 1.35;">${escapeHtml(currentDraft)}</textarea>
          <button data-action="dock-queue" style="${primaryButtonStyle()}">Queue</button>
        </div>
      </div>
    `;
    this.composeDock.querySelectorAll<HTMLButtonElement>("[data-scope]").forEach((button) => {
      button.addEventListener("click", () => {
        this.selectedScope = button.dataset.scope || "";
        this.renderComposeDock();
      });
    });
    (this.composeDock.querySelector('[data-action="dock-cancel"]') as HTMLButtonElement).addEventListener("click", () => this.closeComposeDock());
    (this.composeDock.querySelector('[data-action="dock-queue"]') as HTMLButtonElement).addEventListener("click", () => void this.queueCompose());
    const draft = this.composeDock.querySelector('[data-role="compose-draft"]') as HTMLTextAreaElement;
    draft.addEventListener("input", () => {
      draft.style.height = "auto";
      draft.style.height = `${Math.min(96, draft.scrollHeight)}px`;
    });
  }

  private closeComposeDock(): void {
    this.composeDock.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.sceneManager?.setViewLevel(this.viewLevel, this.selectedAtomId);
  }

  private closeActionRing(): void {
    this.actionRing.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.sceneManager?.setViewLevel(this.viewLevel, this.selectedAtomId);
  }

  private async queueCompose(): Promise<void> {
    const draft = this.composeDock.querySelector('[data-role="compose-draft"]') as HTMLTextAreaElement | null;
    const instruction = draft?.value.trim() || "";
    if (!instruction) {
      return;
    }
    const atomId = this.selectedAtomId || this.selectedScope || null;
    if (this.composeAction === "intercept" || this.composeAction === "shape") {
      await apiPost(`/api/projects/${this.options.projectId}/intents`, {
        kind: this.composeAction === "shape" ? "reroute" : "intercept",
        atom_id: atomId,
        payload: { instruction, scope: this.selectedScope || null, source: "map" },
      });
    } else {
      await apiPost(`/api/projects/${this.options.projectId}/intents`, {
        kind: "interject",
        atom_id: atomId,
        payload: { instruction, scope: this.selectedScope || null, source: "map" },
      });
    }
    this.closeComposeDock();
  }

  private focusActiveAtom(): void {
    const active = this.lastSnapshot ? activeAtom(this.lastSnapshot) : null;
    const target = active?.id || this.options.workflow.find((step) => step.enabled)?.id || this.options.workflow[0]?.id || "";
    if (target) {
      this.selectedAtomId = target;
      this.setViewLevel("surface");
    }
  }

  private setViewLevel(level: SpatialViewLevel): void {
    this.viewLevel = level;
    const active = this.lastSnapshot ? activeAtom(this.lastSnapshot) : null;
    const target = this.selectedAtomId || active?.id || this.options.workflow.find((step) => step.enabled)?.id || this.options.workflow[0]?.id || "";
    this.sceneManager?.setViewLevel(level, target);
    if (this.lastSnapshot && this.bottomHud.style.display !== "none") {
      this.renderBottomHud(this.lastSnapshot);
    }
  }

  private showTimeline(ms: number): void {
    this.timelineRibbon.style.display = "block";
    if (this.timelineHideTimer) {
      window.clearTimeout(this.timelineHideTimer);
    }
    this.timelineHideTimer = window.setTimeout(() => {
      this.timelineRibbon.style.display = "none";
    }, ms);
  }

  private handleEdgeGesture(event: PointerEvent): void {
    if (event.clientY < 28) {
      this.showTimeline(3000);
    }
  }

  private mountFallback(): void {
    if (this.root.querySelector('[data-role="map-fallback"]')) {
      return;
    }
    this.canvas.remove();
    this.actionRing.style.display = "none";
    this.composeDock.style.display = "none";
    this.bottomHud.style.display = "none";
    const fallback = document.createElement("div");
    fallback.dataset.role = "map-fallback";
    fallback.style.cssText = "position: absolute; inset: 56px 0 0 0; overflow: auto; padding: 16px; background: #0D0F14;";
    this.root.appendChild(fallback);
    this.options.engine.onSnapshot((snapshot) => {
      fallback.innerHTML = fallbackHtml(this.options.workflow, snapshot);
    });
    fallback.innerHTML = fallbackHtml(this.options.workflow, this.options.engine.snapshot());
  }
}

export function canUseWebGL(): boolean {
  try {
    if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("fallback") === "1") {
      return false;
    }
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function shouldPreserveDrawingBuffer(): boolean {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).get("capture") === "1";
}

function fallbackHtml(workflow: WorkflowStep[], snapshot: EngineSnapshot): string {
  return `
    <div style="display: grid; gap: 10px;">
      <div style="font-size: 13px; color: #7A7E92;">WebGL unavailable. The same event replay state is shown as an accessible list.</div>
      ${workflow.map((step) => {
        const atom = snapshot.atoms[step.id];
        return `
          <div style="padding: 12px; border: 1px solid #2A3042; border-radius: 8px; background: #141822;">
            <div style="font-size: 14px; font-weight: 700;">${escapeHtml(step.title || step.id)}</div>
            <div style="font-size: 12px; color: #7A7E92; margin-top: 4px;">${escapeHtml(step.type)} · ${escapeHtml(atom?.state || (step.enabled ? "idle" : "skipped"))}</div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function activeAtom(snapshot: EngineSnapshot) {
  return Object.values(snapshot.atoms).find((atom) => atom.state === "active" || atom.state === "waiting" || atom.state === "error") ?? null;
}

function loopDots(snapshot: EngineSnapshot): string {
  const stages = ["discover", "plan", "build", "verify", "repair", "review", "ship", "learn"];
  return stages.map((stage) => {
    const active = (snapshot.loops.activeStageCounts as Record<string, number>)[stage] > 0;
    return `<span title="${stage}" style="width: 7px; height: 7px; border-radius: 999px; background: ${active ? loopStageColor(stage) : "#303647"};"></span>`;
  }).join("");
}

function formatUsd(value: number): string {
  return value > 0 && value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

function loopStageColor(stage: string): string {
  const colors: Record<string, string> = {
    discover: "#41C7C7",
    plan: "#4D6FFF",
    build: "#E8EAF0",
    verify: "#1A8C5A",
    repair: "#E09B2A",
    review: "#7A5CFF",
    ship: "#28B8A8",
    learn: "#9B7EFF",
  };
  return colors[stage] ?? "#303647";
}

function glassButtonStyle(): string {
  return [
    "width: 44px",
    "height: 44px",
    "border: 1px solid var(--line)",
    "border-radius: 999px",
    "background: rgba(13,15,20,0.72)",
    "color: #E8EAF0",
    "font-size: 12px",
    "font-weight: 800",
    "backdrop-filter: blur(14px)",
    "pointer-events: auto",
  ].join("; ");
}

function statusPillStyle(): string {
  return [
    "justify-self: center",
    "height: 34px",
    "display: inline-flex",
    "align-items: center",
    "gap: 8px",
    "border: 1px solid var(--line)",
    "border-radius: 999px",
    "background: rgba(13,15,20,0.62)",
    "color: #E8EAF0",
    "font: 700 12px JetBrains Mono, monospace",
    "letter-spacing: 0",
    "padding: 0 13px",
    "backdrop-filter: blur(14px)",
    "pointer-events: auto",
  ].join("; ");
}

function hudChipStyle(color: string): string {
  return [
    "height: 40px",
    "display: inline-flex",
    "align-items: center",
    "gap: 6px",
    "border: 0",
    "border-radius: 999px",
    "background: rgba(22,27,40,0.9)",
    `color: ${color}`,
    "font: 800 12px Inter, system-ui, sans-serif",
    "padding: 0 12px",
    "white-space: nowrap",
    "max-width: 132px",
    "overflow: hidden",
    "text-overflow: ellipsis",
  ].join("; ");
}

function viewChipStyle(selected: boolean): string {
  return [
    "height: 40px",
    "display: inline-flex",
    "align-items: center",
    "border: 1px solid " + (selected ? "#41C7C7" : "rgba(232,234,240,0.12)"),
    "border-radius: 999px",
    "background: " + (selected ? "rgba(65,199,199,0.16)" : "rgba(22,27,40,0.72)"),
    "color: #E8EAF0",
    "font: 900 11px Inter, system-ui, sans-serif",
    "padding: 0 10px",
    "white-space: nowrap",
  ].join("; ");
}

function ringButtonStyle(position: string, color: string): string {
  return [
    "position: absolute",
    position,
    "width: 94px",
    "height: 46px",
    "border: 1px solid rgba(232,234,240,0.18)",
    "border-radius: 999px",
    "background: rgba(18,23,34,0.84)",
    `color: ${color}`,
    "font: 900 12px Inter, system-ui, sans-serif",
    "box-shadow: 0 14px 34px rgba(0,0,0,0.36), inset 0 1px 0 rgba(255,255,255,0.06)",
    "backdrop-filter: blur(14px)",
  ].join("; ");
}

function ringCloseStyle(): string {
  return [
    "position: absolute",
    "left: 50%",
    "top: 54px",
    "transform: translateX(-50%)",
    "height: 30px",
    "border: 1px solid var(--line)",
    "border-radius: 999px",
    "background: rgba(13,15,20,0.68)",
    "color: #8C92A8",
    "font: 800 11px Inter, system-ui, sans-serif",
    "padding: 0 11px",
  ].join("; ");
}

function scopeChip(value: string, label: string, selected: boolean): string {
  return `<button data-scope="${escapeHtml(value)}" style="${[
    "min-height: 34px",
    "border: 1px solid " + (selected ? "#4D6FFF" : "var(--line)"),
    "border-radius: 999px",
    "background: " + (selected ? "#1F2842" : "#10141E"),
    "color: #E8EAF0",
    "font-size: 12px",
    "font-weight: 800",
    "padding: 0 12px",
    "white-space: nowrap",
  ].join("; ")}">${escapeHtml(label)}</button>`;
}

function composePlaceholder(action: ComposeAction): string {
  if (action === "shape") {
    return "Redirect this object...";
  }
  if (action === "intercept") {
    return "Stop or capture before it proceeds...";
  }
  return "Nudge this run...";
}

function ghostButtonStyle(): string {
  return "height: 34px; border: 1px solid var(--line); border-radius: 999px; background: #10141E; color: #C7CAD6; font-size: 12px; font-weight: 800; padding: 0 12px;";
}

function primaryButtonStyle(): string {
  return "height: 44px; border: 0; border-radius: 999px; background: #E8EAF0; color: #0D0F14; font-size: 13px; font-weight: 900;";
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function apiPost<T = Record<string, unknown>>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

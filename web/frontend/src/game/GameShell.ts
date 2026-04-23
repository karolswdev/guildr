import * as THREE from "three";
import { AssetManager } from "./assets/AssetManager.js";
import { EventEngine } from "./EventEngine.js";
import { SceneManager, type SpatialViewLevel } from "./SceneManager.js";
import type { ArtifactPreview, CostBucket, CostSnapshot, DemoArtifact, DemoPlan, DemoStatus, DemoViewport, DiscussionEntry, DiscussionHighlight, EngineSnapshot, NarrativeDigest, NextStepPacket, OperatorIntentState, WorkflowStep } from "./types.js";

type GameShellOptions = {
  projectId: string;
  workflow: WorkflowStep[];
  projectBrief: ProjectBrief | null;
  engine: EventEngine;
  assetManager: AssetManager;
  navigate: (route: string) => void;
};

export type ProjectBrief = {
  id: string;
  name: string;
  title: string;
  summary: string;
  founding_team: Array<{
    name: string;
    archetype: string | null;
    mandate: string | null;
    stance: string | null;
    veto_scope: string | null;
  }>;
  forum_excerpt: string | null;
  source_refs: string[];
};

type ComposeAction = "shape" | "interject" | "intercept" | "hero";
type BudgetGateDecision = "approved" | "rejected";

type BudgetGateDecisionBody = {
  decision: BudgetGateDecision;
  reason: string;
  new_run_budget_usd: number | null;
  new_phase_budget_usd: number | null;
  budget_at_decision: {
    run_budget_usd: number | null;
    phase_budget_usd: number | null;
    remaining_run_budget_usd: number | null;
    remaining_phase_budget_usd: number | null;
  };
};

type NarrationCue = {
  key: string;
  speaker: string;
  title: string;
  text: string;
  sourceLabel: string;
  mode: string;
};

export class GameShell {
  private readonly root = document.createElement("section");
  private readonly canvas = document.createElement("canvas");
  private readonly topbar = document.createElement("div");
  private readonly bottomHud = document.createElement("div");
  private readonly actionRing = document.createElement("div");
  private readonly composeDock = document.createElement("div");
  private readonly nextStepSheet = document.createElement("div");
  private readonly goalCoreSheet = document.createElement("div");
  private readonly memorySheet = document.createElement("div");
  private readonly costSheet = document.createElement("div");
  private readonly objectLensSheet = document.createElement("div");
  private readonly storyLensSheet = document.createElement("div");
  private readonly narratorBox = document.createElement("div");
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
  private narratorTimer = 0;
  private narratorKey = "";
  private narratorFullText = "";
  private narratorVisibleText = "";
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
    if (this.narratorTimer) {
      window.clearTimeout(this.narratorTimer);
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

    this.nextStepSheet.dataset.role = "next-step-sheet";
    this.nextStepSheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 5",
      "display: none",
      "width: min(720px, calc(100vw - 24px))",
      "max-height: min(58vh, calc(100vh - 146px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 12px",
      "border: 1px solid var(--line)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(21,26,40,0.95), rgba(12,15,24,0.97))",
      "box-shadow: 0 -20px 46px rgba(0,0,0,0.48), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.goalCoreSheet.dataset.role = "goal-core-sheet";
    this.goalCoreSheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 4",
      "display: none",
      "width: min(720px, calc(100vw - 24px))",
      "max-height: min(52vh, calc(100vh - 148px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 11px",
      "border: 1px solid rgba(217,184,77,0.30)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(18,19,28,0.92), rgba(8,10,16,0.96))",
      "box-shadow: 0 -18px 42px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.memorySheet.dataset.role = "memory-core-sheet";
    this.memorySheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 4",
      "display: none",
      "width: min(720px, calc(100vw - 24px))",
      "max-height: min(52vh, calc(100vh - 148px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 11px",
      "border: 1px solid rgba(65,199,199,0.32)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(14,23,31,0.92), rgba(7,11,17,0.96))",
      "box-shadow: 0 -18px 42px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.costSheet.dataset.role = "cost-sheet";
    this.costSheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 4",
      "display: none",
      "width: min(760px, calc(100vw - 24px))",
      "max-height: min(54vh, calc(100vh - 148px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 11px",
      "border: 1px solid rgba(217,184,77,0.34)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(24,22,14,0.92), rgba(9,9,13,0.96))",
      "box-shadow: 0 -18px 42px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.objectLensSheet.dataset.role = "object-lens-sheet";
    this.objectLensSheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 4",
      "display: none",
      "width: min(680px, calc(100vw - 24px))",
      "max-height: min(44vh, calc(100vh - 148px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 11px",
      "border: 1px solid rgba(65,199,199,0.26)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(16,22,33,0.90), rgba(8,11,18,0.94))",
      "box-shadow: 0 -18px 42px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.storyLensSheet.dataset.role = "story-lens-sheet";
    this.storyLensSheet.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(78px, env(safe-area-inset-bottom) + 78px))",
      "z-index: 4",
      "display: none",
      "width: min(760px, calc(100vw - 24px))",
      "max-height: min(52vh, calc(100vh - 148px))",
      "overflow: auto",
      "transform: translateX(-50%)",
      "padding: 11px",
      "border: 1px solid rgba(217,184,77,0.30)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(17,18,28,0.91), rgba(8,9,15,0.95))",
      "box-shadow: 0 -18px 42px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.06)",
      "backdrop-filter: blur(16px)",
      "pointer-events: auto",
    ].join("; ");

    this.narratorBox.dataset.role = "narrator-dialogue";
    this.narratorBox.style.cssText = [
      "position: absolute",
      "left: 50%",
      "bottom: calc(max(82px, env(safe-area-inset-bottom) + 82px))",
      "z-index: 4",
      "display: none",
      "width: min(780px, calc(100vw - 24px))",
      "min-height: 104px",
      "box-sizing: border-box",
      "transform: translateX(-50%)",
      "padding: 12px 13px 13px",
      "border: 1px solid rgba(217,184,77,0.68)",
      "border-radius: 8px",
      "background: linear-gradient(180deg, rgba(11,14,24,0.94), rgba(5,7,13,0.96))",
      "box-shadow: 0 -18px 44px rgba(0,0,0,0.48), 0 0 0 1px rgba(255,255,255,0.05), inset 0 1px 0 rgba(255,255,255,0.12)",
      "backdrop-filter: blur(14px)",
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
    this.root.appendChild(this.nextStepSheet);
    this.root.appendChild(this.goalCoreSheet);
    this.root.appendChild(this.memorySheet);
    this.root.appendChild(this.costSheet);
    this.root.appendChild(this.objectLensSheet);
    this.root.appendChild(this.storyLensSheet);
    this.root.appendChild(this.narratorBox);
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
        onSelectGoalCore: () => this.openGoalCoreSheet(),
        onSelectMemoryCore: () => this.openMemorySheet(),
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
    this.renderNarrator(snapshot);
    if (this.actionRing.style.display !== "none") {
      this.renderActionRing();
    }
    if (this.composeDock.style.display !== "none") {
      this.renderComposeDock();
    }
    if (this.nextStepSheet.style.display !== "none") {
      this.renderNextStepSheet(snapshot);
    }
    if (this.goalCoreSheet.style.display !== "none") {
      this.renderGoalCoreSheet(snapshot);
    }
    if (this.memorySheet.style.display !== "none") {
      this.renderMemorySheet(snapshot);
    }
    if (this.costSheet.style.display !== "none") {
      this.renderCostSheet(snapshot);
    }
    if (this.objectLensSheet.style.display !== "none") {
      this.renderObjectLens(snapshot);
    }
    if (this.storyLensSheet.style.display !== "none") {
      this.renderStoryLens(snapshot);
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
    const nextLabel = snapshot.nextStepPacket?.title || snapshot.nextStepPacket?.step || "No packet";
    const memoryLabel = snapshot.memPalaceStatus?.wakeUpHash
      ? `Memory: ${snapshot.memPalaceStatus.wakeUpHash.slice(0, 8)}`
      : snapshot.memPalaceStatus?.error
        ? "Memory: error"
        : "Memory";
    const storyCount = snapshot.digests.length + snapshot.discussionHighlights.length;
    this.bottomHud.innerHTML = `
      <button data-action="focus-active" style="${hudChipStyle("#E8EAF0")}"><span style="color: #41C7C7;">●</span>${escapeHtml(active?.id || "overview")}</button>
      <button data-action="open-goal-core" data-role="goal-core-control" style="${hudChipStyle("#D9B84D")}">Goal</button>
      <button data-action="open-memory-core" data-role="memory-core-control" style="${hudChipStyle("#41C7C7")}">${escapeHtml(memoryLabel)}</button>
      <button data-action="open-next-step" data-role="next-step-control" style="${hudChipStyle("#41C7C7")}">Next: ${escapeHtml(nextLabel)}</button>
      <button data-view-level="global" aria-label="Global view" style="${viewChipStyle(this.viewLevel === "global")}">Run</button>
      <button data-view-level="cluster" aria-label="Loop cluster view" style="${viewChipStyle(this.viewLevel === "cluster")}">Loop</button>
      <button data-view-level="surface" aria-label="Object surface view" style="${viewChipStyle(this.viewLevel === "surface")}">Object</button>
      <button data-view-level="story" data-role="story-lens-control" aria-label="Story view" style="${viewChipStyle(this.viewLevel === "story")}">Story: ${storyCount}</button>
      <button data-action="open-timeline" style="${hudChipStyle("#D9B84D")}">${done}/${total}</button>
      <button data-action="open-cost" data-role="cost-control" style="${hudChipStyle("#D9B84D")}">${formatUsd(snapshot.cost.effectiveUsd)}${escapeHtml(remaining)}${unknown}</button>
      <div data-role="loop-dots" style="display: flex; gap: 4px; align-items: center; padding: 0 6px;">${loopDots(snapshot)}</div>
    `;
    (this.bottomHud.querySelector('[data-action="focus-active"]') as HTMLButtonElement).addEventListener("click", () => this.focusActiveAtom());
    (this.bottomHud.querySelector('[data-action="open-goal-core"]') as HTMLButtonElement).addEventListener("click", () => this.openGoalCoreSheet());
    (this.bottomHud.querySelector('[data-action="open-memory-core"]') as HTMLButtonElement).addEventListener("click", () => this.openMemorySheet());
    (this.bottomHud.querySelector('[data-action="open-next-step"]') as HTMLButtonElement).addEventListener("click", () => this.openNextStepSheet());
    (this.bottomHud.querySelector('[data-action="open-cost"]') as HTMLButtonElement).addEventListener("click", () => this.openCostSheet());
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

  private renderNarrator(snapshot: EngineSnapshot): void {
    const narration = narrationForSnapshot(snapshot);
    const overlayOpen = (
      this.nextStepSheet.style.display !== "none" ||
      this.goalCoreSheet.style.display !== "none" ||
      this.memorySheet.style.display !== "none" ||
      this.costSheet.style.display !== "none" ||
      this.objectLensSheet.style.display !== "none" ||
      this.storyLensSheet.style.display !== "none" ||
      this.composeDock.style.display !== "none" ||
      this.actionRing.style.display !== "none"
    );
    if (!narration || overlayOpen) {
      this.narratorBox.style.display = "none";
      return;
    }

    this.narratorBox.style.display = "block";
    if (narration.key !== this.narratorKey) {
      this.narratorKey = narration.key;
      this.narratorFullText = narration.text;
      this.narratorVisibleText = prefersReducedMotion() ? narration.text : "";
      this.renderNarratorFrame(narration);
      if (!prefersReducedMotion()) {
        this.advanceNarratorText(narration);
      }
      return;
    }
    this.renderNarratorFrame(narration);
  }

  private renderNarratorFrame(narration: NarrationCue): void {
    const text = this.narratorVisibleText || (prefersReducedMotion() ? narration.text : "");
    const complete = text.length >= narration.text.length;
    this.narratorBox.innerHTML = `
      <div style="display: grid; gap: 8px;">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
          <div style="display: inline-flex; align-items: center; gap: 8px; min-width: 0;">
            <span style="width: 10px; height: 10px; border-radius: 999px; background: #D9B84D; box-shadow: 0 0 16px rgba(217,184,77,0.78);"></span>
            <span style="font: 900 11px JetBrains Mono, ui-monospace, monospace; color: #D9B84D; text-transform: uppercase; letter-spacing: 0;">${escapeHtml(narration.speaker)}</span>
            <span style="color: #5E6578; font-size: 11px;">/</span>
            <span style="min-width: 0; color: #C7CAD6; font-size: 12px; font-weight: 850; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(narration.title)}</span>
          </div>
          <div style="display: inline-flex; gap: 6px; flex: 0 0 auto;">
            <button data-action="narrator-replay" style="${tinyNarratorButtonStyle()}">Replay</button>
            <button data-action="narrator-skip" style="${tinyNarratorButtonStyle()}">${complete ? "Done" : "Skip"}</button>
          </div>
        </div>
        <div data-role="narrator-text" style="min-height: 44px; color: #F4F0DD; font-family: Georgia, 'Times New Roman', serif; font-size: 17px; line-height: 1.42; overflow-wrap: anywhere; text-shadow: 0 1px 0 rgba(0,0,0,0.54);">${escapeHtml(text)}${complete ? "" : `<span style="color: #D9B84D;">▌</span>`}</div>
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
          <div style="min-width: 0; color: #8C92A8; font: 800 10px JetBrains Mono, ui-monospace, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(narration.sourceLabel)}</div>
          <div style="color: #7A7E92; font-size: 10px; font-weight: 850; text-transform: uppercase;">${escapeHtml(narration.mode)}</div>
        </div>
      </div>
    `;
    (this.narratorBox.querySelector('[data-action="narrator-skip"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      if (this.narratorTimer) {
        window.clearTimeout(this.narratorTimer);
        this.narratorTimer = 0;
      }
      this.narratorVisibleText = narration.text;
      this.renderNarratorFrame(narration);
    });
    (this.narratorBox.querySelector('[data-action="narrator-replay"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      if (this.narratorTimer) {
        window.clearTimeout(this.narratorTimer);
      }
      this.narratorVisibleText = prefersReducedMotion() ? narration.text : "";
      this.renderNarratorFrame(narration);
      if (!prefersReducedMotion()) {
        this.advanceNarratorText(narration);
      }
    });
  }

  private advanceNarratorText(narration: NarrationCue): void {
    if (this.narratorVisibleText.length >= narration.text.length) {
      this.narratorTimer = 0;
      this.renderNarratorFrame(narration);
      return;
    }
    const step = narration.text.charAt(this.narratorVisibleText.length) === " " ? 2 : 1;
    this.narratorVisibleText = narration.text.slice(0, Math.min(narration.text.length, this.narratorVisibleText.length + step));
    this.renderNarratorFrame(narration);
    this.narratorTimer = window.setTimeout(() => this.advanceNarratorText(narration), 18);
  }

  private openActionRing(atomId: string): void {
    this.selectedAtomId = atomId;
    this.selectedScope = this.selectedScope || atomId;
    this.viewLevel = "surface";
    this.nextStepSheet.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.composeDock.style.display = "none";
    this.actionRing.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.objectLensSheet.style.display = "block";
    this.sceneManager?.setViewLevel("surface", atomId);
    this.sceneManager?.focusAtomInView(atomId, 0.36);
    if (this.lastSnapshot) {
      this.renderObjectLens(this.lastSnapshot);
    }
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
    this.nextStepSheet.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.actionRing.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "none";
    this.composeDock.style.display = "grid";
    this.sceneManager?.setViewLevel("surface", atomId);
    this.sceneManager?.focusAtomInView(atomId, 0.4);
    this.renderComposeDock();
  }

  private openNextStepSheet(): void {
    const packet = this.lastSnapshot?.nextStepPacket ?? null;
    this.actionRing.style.display = "none";
    this.composeDock.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.nextStepSheet.style.display = "block";
    if (packet?.step) {
      this.selectedAtomId = packet.step;
      this.selectedScope = packet.step;
      this.viewLevel = "surface";
      this.sceneManager?.setViewLevel("surface", packet.step);
      this.sceneManager?.focusAtomInView(packet.step, 0.42);
    }
    if (this.lastSnapshot) {
      this.renderNextStepSheet(this.lastSnapshot);
    }
  }

  private openGoalCoreSheet(): void {
    this.actionRing.style.display = "none";
    this.composeDock.style.display = "none";
    this.nextStepSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.goalCoreSheet.style.display = "block";
    this.viewLevel = "global";
    this.sceneManager?.focusGoalCore();
    if (this.lastSnapshot) {
      this.renderGoalCoreSheet(this.lastSnapshot);
    }
  }

  private renderGoalCoreSheet(snapshot: EngineSnapshot): void {
    const brief = this.options.projectBrief;
    const next = snapshot.nextStepPacket;
    const latest = snapshot.latestDigest;
    const title = brief?.title || brief?.name || "Project goal";
    const summary = brief?.summary || "No synthesized project brief is available yet.";
    const founders = brief?.founding_team ?? [];
    this.goalCoreSheet.innerHTML = `
      <div style="display: grid; gap: 11px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 10px; color: #D9B84D; text-transform: uppercase; font-weight: 900;">Goal Core · ${escapeHtml(snapshot.live ? "Live" : "Replay")}</div>
            <div style="font-size: 17px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(title)}</div>
            <div style="font-size: 11px; color: #8C92A8; margin-top: 4px;">${founders.length} founders · ${Object.values(snapshot.atoms).filter((atom) => atom.state === "done").length}/${Object.keys(snapshot.atoms).length} objects done</div>
          </div>
          <button data-action="goal-core-close" style="${ghostButtonStyle()}">Close</button>
        </div>
        <div style="${sheetPanelStyle()}">
          <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 4px;">Project brief</div>
          <div style="font-size: 13px; color: #E8EAF0; line-height: 1.38; overflow-wrap: anywhere;">${escapeHtml(summary)}</div>
        </div>
        ${founders.length > 0 ? `
          <div data-role="founding-team-brief" style="display: grid; gap: 7px;">
            <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Founding team</div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 7px;">
              ${founders.map((persona) => founderCard(persona)).join("")}
            </div>
          </div>
        ` : `<div style="${sheetEmptyStyle()}">No founding-team artifact has been synthesized yet.</div>`}
        ${brief?.forum_excerpt ? sheetSection("Forum pulse", [brief.forum_excerpt], "No forum excerpt yet.") : ""}
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 7px;">
          ${sheetField("Next", next ? `${next.title || next.step}: ${next.objective || next.whyNow || next.role}` : "No next-step packet is available yet.")}
          ${sheetField("Latest story", latest ? `${latest.title}: ${latest.summary}` : "No narrative digest has landed yet.")}
        </div>
        ${sheetRefs("Sources", brief?.source_refs ?? [])}
        <div style="display: grid; grid-template-columns: minmax(0, 1fr) ${next?.step ? "118px" : "0"}; gap: 8px; align-items: center;">
          <div style="min-width: 0; color: #AEB4C6; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(next?.step || "Waiting for the first actionable step.")}</div>
          ${next?.step ? `<button data-action="goal-nudge-next" style="${primaryButtonStyle()}">Nudge</button>` : ""}
        </div>
      </div>
    `;
    (this.goalCoreSheet.querySelector('[data-action="goal-core-close"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      this.goalCoreSheet.style.display = "none";
    });
    (this.goalCoreSheet.querySelector('[data-action="goal-nudge-next"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      if (next?.step) {
        this.openComposeDock(next.step, "interject");
      }
    });
  }

  private openMemorySheet(): void {
    this.actionRing.style.display = "none";
    this.composeDock.style.display = "none";
    this.nextStepSheet.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.memorySheet.style.display = "block";
    this.viewLevel = "global";
    this.sceneManager?.focusGoalCore();
    if (this.lastSnapshot) {
      this.renderMemorySheet(this.lastSnapshot);
    }
  }

  private renderMemorySheet(snapshot: EngineSnapshot): void {
    this.memorySheet.innerHTML = `
      <div style="display: grid; gap: 11px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 10px; color: #41C7C7; text-transform: uppercase; font-weight: 900;">Memory Spine · ${escapeHtml(snapshot.live ? "Live" : "Replay")}</div>
            <div style="font-size: 17px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">MemPalace wake-up packet</div>
            <div style="font-size: 11px; color: #8C92A8; margin-top: 4px;">${snapshot.memoryEvents.length} memory events folded into this replay point</div>
          </div>
          <div style="display: inline-flex; gap: 6px; flex: 0 0 auto;">
            <button data-action="memory-sync" data-role="memory-sync-control" style="${primaryButtonStyle()}">Sync</button>
            <button data-action="memory-close" style="${ghostButtonStyle()}">Close</button>
          </div>
        </div>
        ${memoryStatusCard(snapshot)}
      </div>
    `;
    (this.memorySheet.querySelector('[data-action="memory-close"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      this.memorySheet.style.display = "none";
    });
    (this.memorySheet.querySelector('[data-action="memory-sync"]') as HTMLButtonElement | null)?.addEventListener("click", () => void this.syncMemory());
  }

  private async syncMemory(): Promise<void> {
    const button = this.memorySheet.querySelector('[data-action="memory-sync"]') as HTMLButtonElement | null;
    if (button) {
      button.disabled = true;
      button.textContent = "Syncing";
    }
    try {
      await apiPost(`/api/projects/${this.options.projectId}/memory/sync`, {});
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Sync";
      }
    }
  }

  private openCostSheet(): void {
    this.actionRing.style.display = "none";
    this.composeDock.style.display = "none";
    this.nextStepSheet.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "flex";
    this.costSheet.style.display = "block";
    if (this.lastSnapshot) {
      this.renderCostSheet(this.lastSnapshot);
    }
  }

  private renderCostSheet(snapshot: EngineSnapshot): void {
    const mode = snapshot.live ? "Live" : `Replay ${snapshot.replayIndex + 1}/${snapshot.historyLength}`;
    const providerCount = Object.keys(snapshot.cost.byProvider).length;
    const modelCount = Object.keys(snapshot.cost.byModel).length;
    this.costSheet.innerHTML = `
      <div style="display: grid; gap: 11px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 10px; color: #D9B84D; text-transform: uppercase; font-weight: 900;">Economics · ${escapeHtml(mode)}</div>
            <div style="font-size: 17px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">Cost telemetry</div>
            <div style="font-size: 11px; color: #8C92A8; margin-top: 4px;">${providerCount} providers · ${modelCount} models · ${snapshot.cost.openBudgetGateIds.length} open gates</div>
          </div>
          <div style="display: inline-flex; gap: 6px; flex: 0 0 auto;">
            <button data-action="cost-open-timeline" style="${ghostButtonStyle()}">Timeline</button>
            <button data-action="cost-close" style="${ghostButtonStyle()}">Close</button>
          </div>
        </div>
        ${costSummaryCard(snapshot.cost)}
        ${budgetGateControls(snapshot.cost)}
      </div>
    `;
    (this.costSheet.querySelector('[data-action="cost-close"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      this.costSheet.style.display = "none";
    });
    (this.costSheet.querySelector('[data-action="cost-open-timeline"]') as HTMLButtonElement | null)?.addEventListener("click", () => this.showTimeline(5000));
    this.costSheet.querySelectorAll<HTMLButtonElement>("[data-budget-gate-action]").forEach((button) => {
      button.addEventListener("click", () => void this.decideBudgetGate(button));
    });
  }

  private async decideBudgetGate(button: HTMLButtonElement): Promise<void> {
    const gateId = button.dataset.gateId || "";
    const action = button.dataset.budgetGateAction || "";
    if (!gateId || !this.lastSnapshot) {
      return;
    }
    const card = button.closest('[data-role="budget-gate-card"]') as HTMLElement | null;
    const input = card?.querySelector('[data-role="budget-gate-run-budget"]') as HTMLInputElement | null;
    const newRunBudget = action === "raise" ? inputNumberOrNull(input?.value ?? "") : null;
    const decision: BudgetGateDecision = action === "reject" ? "rejected" : "approved";
    const reason = action === "raise"
      ? "Raised run budget from PWA Economics sheet."
      : action === "reject"
        ? "Stopped from PWA Economics sheet."
        : "Continued from PWA Economics sheet.";
    const body = budgetDecisionPayload(this.lastSnapshot.cost, decision, reason, newRunBudget);
    button.disabled = true;
    button.textContent = "Sending";
    try {
      await apiPost(`/api/projects/${encodeURIComponent(this.options.projectId)}/gates/${encodeURIComponent(gateId)}/decide`, body);
      this.options.engine.resumeLive();
    } finally {
      button.disabled = false;
      if (this.lastSnapshot) {
        this.renderCostSheet(this.lastSnapshot);
      }
    }
  }

  private renderNextStepSheet(snapshot: EngineSnapshot): void {
    const packet = snapshot.nextStepPacket;
    if (!packet) {
      this.nextStepSheet.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
          <div style="font-size: 13px; font-weight: 850;">Next step</div>
          <button data-action="next-sheet-close" style="${ghostButtonStyle()}">Close</button>
        </div>
        <div style="${sheetEmptyStyle()}">Waiting for the run ledger to emit the next step packet.</div>
      `;
      this.bindNextStepSheetActions(null);
      return;
    }

    const intents = intentsForStep(snapshot, packet.step);
    this.nextStepSheet.innerHTML = `
      <div style="display: grid; gap: 12px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Next · ${escapeHtml(packet.role)}</div>
            <div style="font-size: 17px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(packet.title || packet.step)}</div>
          </div>
          <button data-action="next-sheet-close" style="${ghostButtonStyle()}">Close</button>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px;">
          ${sheetField("Objective", packet.objective || "No objective in packet.")}
          ${sheetField("Why now", packet.whyNow || "No timing reason in packet.")}
        </div>
        <div data-role="functional-readiness" style="display: grid; gap: 8px;">
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 8px;">
            ${sheetField("Demo readiness", demoReadinessLabel(packet))}
            ${sheetField("Interventions", packet.interventionOptions.length > 0 ? packet.interventionOptions.join(", ") : "No declared interventions.")}
          </div>
          ${sheetSection("Acceptance criteria", packet.acceptanceCriteria, "No acceptance criteria are declared for this next move yet.")}
          ${sheetSection("Evidence required", packet.evidenceRequired, "No explicit evidence requirements are declared yet.")}
        </div>
        ${functionalMiniSprintPanel(snapshot)}
        ${heroRosterPanel(snapshot)}
        ${latestDigestPanel(snapshot)}
        ${discussionPanel(snapshot, packet.step)}
        ${sheetSection("Context", packet.contextPreview, "No context preview yet.")}
        ${sheetRefs("Inputs", packet.inputs.map(packetInputLabel))}
        ${sheetRefs("Memory", packet.memoryRefs)}
        ${sheetRefs("Sources", packet.sourceRefs)}
        <div style="display: grid; gap: 8px;">
          <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Intents</div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(138px, 1fr)); gap: 7px;">
            ${intentColumn("Queued", intents.queued.map(queuedIntentLabel))}
            ${intentColumn("Applied", intents.applied.map(intentStateLabel))}
            ${intentColumn("Ignored", intents.ignored.map(intentStateLabel))}
          </div>
        </div>
        <div style="display: grid; grid-template-columns: minmax(0, 1fr) repeat(2, 118px); gap: 8px; align-items: center;">
          <div style="min-width: 0; color: #AEB4C6; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(packet.step)}</div>
          <button data-action="next-invite-hero" style="${ghostButtonStyle()}">Hero</button>
          <button data-action="next-interject" style="${primaryButtonStyle()}">Nudge</button>
        </div>
      </div>
    `;
    this.bindNextStepSheetActions(packet);
  }

  private renderObjectLens(snapshot: EngineSnapshot): void {
    const atomId = this.selectedAtomId || snapshot.nextStepPacket?.step || activeAtom(snapshot)?.id || "";
    const step = this.options.workflow.find((item) => item.id === atomId);
    if (!atomId || !step) {
      this.objectLensSheet.style.display = "none";
      return;
    }
    const atom = snapshot.atoms[atomId];
    const packet = snapshot.nextStepPacket?.step === atomId ? snapshot.nextStepPacket : null;
    const intents = intentsForStep(snapshot, atomId);
    const digestRows = snapshot.digests
      .filter((digest) => digest.sourceEventIds.some((eventId) => sourceEventTouchesAtom(snapshot, eventId, atomId)))
      .slice(-2)
      .map((digest) => digest.summary);
    const discussionRows = snapshot.discussion
      .filter((entry) => entry.atomId === atomId || entry.atomId === null)
      .slice(-2)
      .map((entry) => `${entry.speaker}: ${entry.text}`);
    const produced = producedRefsForAtom(snapshot, atomId);
    const consumed = packet ? [
      ...packet.inputs.map(packetInputLabel),
      ...packet.memoryRefs.map((ref) => `memory: ${ref}`),
    ] : [];
    const nextRelation = snapshot.nextStepPacket?.step === atomId
      ? `This object is slated next as ${snapshot.nextStepPacket.role}.`
      : snapshot.nextStepPacket
        ? `Next slated object: ${snapshot.nextStepPacket.title || snapshot.nextStepPacket.step}.`
        : "No next-step packet is currently available.";

    this.objectLensSheet.innerHTML = `
      <div style="display: grid; gap: 10px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 10px; color: #41C7C7; text-transform: uppercase; font-weight: 900;">Object · ${escapeHtml(step.handler)}</div>
            <div style="font-size: 16px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(step.title || step.id)}</div>
            <div style="font-size: 11px; color: #8C92A8; margin-top: 4px;">${escapeHtml(atom?.state || (step.enabled ? "idle" : "skipped"))} · ${escapeHtml(atomId)}</div>
          </div>
          <button data-action="object-lens-close" style="${ghostButtonStyle()}">Close</button>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 7px;">
          ${sheetField("What", objectWhat(step, atom?.state || "idle"))}
          ${sheetField("Next", nextRelation)}
        </div>
        ${sheetSection("Consumed", consumed, "No consumed inputs are attached to this object yet.")}
        ${sheetSection("Produced", produced, "No produced artifacts are known for this object yet.")}
        ${sheetSection("Story", [...digestRows, ...discussionRows], "No story or discussion rows are attached yet.")}
        ${(() => {
          const demos = snapshot.demos.filter((demo) => demo.atomId === atomId);
          if (demos.length === 0) {
            return "";
          }
          return `
            <div data-role="object-demo-rail" style="display: grid; gap: 7px;">
              <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Demo proof</div>
              ${demos.slice(-2).reverse().map((demo) => storyDemoCard(demo, this.options.projectId)).join("")}
            </div>
          `;
        })()}
        ${(() => {
          const previews = snapshot.previews.filter((preview) => preview.producingAtomId === atomId);
          if (previews.length === 0) {
            return "";
          }
          return `
            <div data-role="object-preview-rail" style="display: grid; gap: 7px;">
              <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Artifact previews</div>
              ${previews.slice(-2).reverse().map((preview) => artifactPreviewCard(preview)).join("")}
            </div>
          `;
        })()}
        <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px;">
          <button data-action-command="shape" style="${objectCommandStyle("#41C7C7")}">Shape</button>
          <button data-action-command="interject" style="${objectCommandStyle("#E8EAF0")}">Nudge</button>
          <button data-action-command="intercept" style="${objectCommandStyle("#E09B2A")}">Intercept</button>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 7px;">
          ${intentColumn("Queued", intents.queued.map(queuedIntentLabel))}
          ${intentColumn("Applied", intents.applied.map(intentStateLabel))}
          ${intentColumn("Ignored", intents.ignored.map(intentStateLabel))}
        </div>
      </div>
    `;
    (this.objectLensSheet.querySelector('[data-action="object-lens-close"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      this.objectLensSheet.style.display = "none";
    });
    this.objectLensSheet.querySelectorAll<HTMLButtonElement>("[data-action-command]").forEach((button) => {
      button.addEventListener("click", () => this.openComposeDock(atomId, button.dataset.actionCommand as ComposeAction));
    });
  }

  private renderStoryLens(snapshot: EngineSnapshot): void {
    const storyAtoms = storyAtomIdsForSnapshot(snapshot).filter((atomId) => this.options.workflow.some((step) => step.id === atomId));
    this.sceneManager?.setStoryFocus(storyAtoms);
    const digests = snapshot.digests.slice(-5).reverse();
    const discussionRows = snapshot.discussion.slice(-5).reverse();
    const highlights = snapshot.discussionHighlights.slice(-4).reverse();
    const next = snapshot.nextStepPacket;
    const mode = snapshot.live ? "Live" : `Replay ${snapshot.replayIndex + 1}/${snapshot.historyLength}`;

    this.storyLensSheet.innerHTML = `
      <div style="display: grid; gap: 11px;">
        <div style="display: flex; align-items: start; justify-content: space-between; gap: 10px;">
          <div style="min-width: 0;">
            <div style="font-size: 10px; color: #D9B84D; text-transform: uppercase; font-weight: 900;">Story Lens · ${escapeHtml(mode)}</div>
            <div style="font-size: 16px; font-weight: 900; line-height: 1.2; margin-top: 3px; overflow-wrap: anywhere;">Recent run path</div>
            <div style="font-size: 11px; color: #8C92A8; margin-top: 4px;">${digests.length} digests · ${discussionRows.length} discussion rows · ${highlights.length} highlights</div>
          </div>
          <div style="display: inline-flex; gap: 6px; flex: 0 0 auto;">
            <button data-action="story-open-timeline" style="${ghostButtonStyle()}">Timeline</button>
            <button data-action="story-lens-close" style="${ghostButtonStyle()}">Close</button>
          </div>
        </div>
        ${storyAtoms.length > 0 ? sheetRefs("Touched objects", storyAtoms.map((atomId) => storyStepTitle(this.options.workflow, atomId))) : ""}
        ${(() => {
          const demos = snapshot.demos.slice(-3).reverse();
          if (demos.length === 0) {
            return "";
          }
          return `
            <div data-role="story-demo-rail" style="display: grid; gap: 8px;">
              <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Demo ceremonies</div>
              ${demos.map((demo) => storyDemoCard(demo, this.options.projectId)).join("")}
            </div>
          `;
        })()}
        ${(() => {
          const previews = snapshot.previews.slice(-3).reverse();
          if (previews.length === 0) {
            return "";
          }
          return `
            <div data-role="story-preview-rail" style="display: grid; gap: 8px;">
              <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Artifact previews</div>
              ${previews.map((preview) => artifactPreviewCard(preview)).join("")}
            </div>
          `;
        })()}
        ${digests.length > 0 ? `
          <div data-role="story-card-rail" style="display: grid; gap: 8px;">
            <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">DWA Story Satellites</div>
            ${digests.map((digest) => storyDigestCard(digest)).join("")}
          </div>
        ` : `<div style="${sheetEmptyStyle()}">No narrative digests have been emitted into the event ledger yet.</div>`}
        ${highlights.length > 0 ? `
          <div data-role="story-highlight-rail" style="display: grid; gap: 6px;">
            <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Discussion highlights</div>
            ${highlights.map((highlight) => discussionHighlightCard(highlight)).join("")}
          </div>
        ` : ""}
        ${discussionRows.length > 0 ? `
          <div data-role="story-discussion-rail" style="display: grid; gap: 6px;">
            <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Recent discussion</div>
            ${discussionRows.map((entry) => discussionEntryCard(entry)).join("")}
          </div>
        ` : ""}
        <div style="display: grid; grid-template-columns: minmax(0, 1fr) ${next?.step ? "118px" : "0"}; gap: 8px; align-items: center;">
          <div style="${sheetPanelStyle()}">
            <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 4px;">Next slated step</div>
            <div style="font-size: 12px; color: #E8EAF0; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(next ? `${next.title || next.step} · ${next.objective || next.whyNow || next.role}` : "No next-step packet is currently available.")}</div>
          </div>
          ${next?.step ? `<button data-action="story-nudge-next" style="${primaryButtonStyle()}">Nudge</button>` : ""}
        </div>
      </div>
    `;
    (this.storyLensSheet.querySelector('[data-action="story-lens-close"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      this.storyLensSheet.style.display = "none";
    });
    (this.storyLensSheet.querySelector('[data-action="story-open-timeline"]') as HTMLButtonElement | null)?.addEventListener("click", () => this.showTimeline(5000));
    (this.storyLensSheet.querySelector('[data-action="story-nudge-next"]') as HTMLButtonElement | null)?.addEventListener("click", () => {
      if (next?.step) {
        this.openComposeDock(next.step, "interject");
      }
    });
  }

  private bindNextStepSheetActions(packet: NextStepPacket | null): void {
    const close = this.nextStepSheet.querySelector('[data-action="next-sheet-close"]') as HTMLButtonElement | null;
    close?.addEventListener("click", () => {
      this.nextStepSheet.style.display = "none";
    });
    const interject = this.nextStepSheet.querySelector('[data-action="next-interject"]') as HTMLButtonElement | null;
    interject?.addEventListener("click", () => {
      if (packet?.step) {
        this.openComposeDock(packet.step, "interject");
      }
    });
    const inviteHero = this.nextStepSheet.querySelector('[data-action="next-invite-hero"]') as HTMLButtonElement | null;
    inviteHero?.addEventListener("click", () => {
      if (packet?.step) {
        this.openComposeDock(packet.step, "hero");
      }
    });
    const repair = this.nextStepSheet.querySelector('[data-action="next-functional-repair"]') as HTMLButtonElement | null;
    repair?.addEventListener("click", () => {
      if (packet?.step) {
        void this.queueFunctionalAcceptanceIntent("retry", packet);
      }
    });
    const heroReview = this.nextStepSheet.querySelector('[data-action="next-functional-hero"]') as HTMLButtonElement | null;
    heroReview?.addEventListener("click", () => {
      if (packet?.step) {
        this.openComposeDock(packet.step, "hero");
      }
    });
    const override = this.nextStepSheet.querySelector('[data-action="next-functional-override"]') as HTMLButtonElement | null;
    override?.addEventListener("click", () => {
      if (packet?.step) {
        void this.queueFunctionalAcceptanceIntent("acceptance_override", packet);
      }
    });
  }

  private async queueFunctionalAcceptanceIntent(kind: "retry" | "acceptance_override", packet: NextStepPacket): Promise<void> {
    const sprint = this.lastSnapshot?.functional.currentMiniSprint ?? null;
    const blockers = sprint?.acceptance?.blockingFindings ?? [];
    const actionLabel = kind === "retry" ? "Repair blocked functional acceptance" : "Operator acceptance override";
    await apiPost(`/api/projects/${this.options.projectId}/intents`, {
      kind,
      atom_id: packet.step,
      client_intent_id: newClientIntentId(),
      payload: {
        instruction: actionLabel,
        source: "functional_acceptance",
        mini_sprint_id: sprint?.miniSprintId ?? null,
        blocking_findings: blockers,
        acceptance_passed: sprint?.acceptance?.passed ?? null,
      },
    });
    this.options.engine.resumeLive();
  }

  private renderComposeDock(): void {
    const atomId = this.selectedAtomId;
    const step = this.options.workflow.find((item) => item.id === atomId);
    const textarea = this.composeDock.querySelector('[data-role="compose-draft"]') as HTMLTextAreaElement | null;
    const currentDraft = textarea?.value ?? "";
    const heroName = (this.composeDock.querySelector('[data-role="hero-name"]') as HTMLInputElement | null)?.value ?? "";
    const heroWatchFor = (this.composeDock.querySelector('[data-role="hero-watch-for"]') as HTMLInputElement | null)?.value ?? "";
    const heroProvider = (this.composeDock.querySelector('[data-role="hero-provider"]') as HTMLInputElement | null)?.value ?? "primary";
    const heroModel = (this.composeDock.querySelector('[data-role="hero-model"]') as HTMLInputElement | null)?.value ?? "";
    const heroTerm = (this.composeDock.querySelector('[data-role="hero-term"]') as HTMLInputElement | null)?.value ?? "single_consultation";
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
        ${this.composeAction === "hero" ? heroInviteFields({ name: heroName, watchFor: heroWatchFor, provider: heroProvider, model: heroModel, termMode: heroTerm }) : ""}
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
    this.composeDock.querySelectorAll<HTMLButtonElement>("[data-hero-term-option]").forEach((button) => {
      button.addEventListener("click", () => {
        const term = normalizeHeroTermMode(button.dataset.heroTermOption || "");
        const input = this.composeDock.querySelector('[data-role="hero-term"]') as HTMLInputElement | null;
        if (input) {
          input.value = term;
        }
        this.composeDock.querySelectorAll<HTMLButtonElement>("[data-hero-term-option]").forEach((termButton) => {
          termButton.style.cssText = heroTermChipStyle(termButton.dataset.heroTermOption === term);
        });
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
    if (this.viewLevel === "surface" && this.selectedAtomId && this.lastSnapshot) {
      this.objectLensSheet.style.display = "block";
      this.renderObjectLens(this.lastSnapshot);
    } else if (this.viewLevel === "story" && this.lastSnapshot) {
      this.storyLensSheet.style.display = "block";
      this.renderStoryLens(this.lastSnapshot);
    }
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
    const clientIntentId = newClientIntentId();
    const kind = this.composeAction === "shape"
      ? "reroute"
      : this.composeAction === "intercept"
        ? "intercept"
        : this.composeAction === "hero"
          ? "invite_hero"
          : "interject";
    const payload = this.composeAction === "hero"
      ? heroInvitePayload({
        mission: instruction,
        name: (this.composeDock.querySelector('[data-role="hero-name"]') as HTMLInputElement | null)?.value || "",
        watchFor: (this.composeDock.querySelector('[data-role="hero-watch-for"]') as HTMLInputElement | null)?.value || "",
        provider: (this.composeDock.querySelector('[data-role="hero-provider"]') as HTMLInputElement | null)?.value || "",
        model: (this.composeDock.querySelector('[data-role="hero-model"]') as HTMLInputElement | null)?.value || "",
        termMode: (this.composeDock.querySelector('[data-role="hero-term"]') as HTMLInputElement | null)?.value || "",
        step: this.selectedScope || atomId,
        scope: this.selectedScope || null,
      })
      : { instruction, scope: this.selectedScope || null, source: "map" };
    await apiPost(`/api/projects/${this.options.projectId}/intents`, {
      kind,
      atom_id: atomId,
      client_intent_id: clientIntentId,
      payload,
    });
    this.closeComposeDock();
  }

  private focusActiveAtom(): void {
    const active = this.lastSnapshot ? activeAtom(this.lastSnapshot) : null;
    const target = active?.id || this.options.workflow.find((step) => step.enabled)?.id || this.options.workflow[0]?.id || "";
    if (target) {
      this.selectedAtomId = target;
      this.setViewLevel("surface");
      if (this.lastSnapshot) {
        this.objectLensSheet.style.display = "block";
        this.renderObjectLens(this.lastSnapshot);
      }
    }
  }

  private setViewLevel(level: SpatialViewLevel): void {
    this.viewLevel = level;
    const active = this.lastSnapshot ? activeAtom(this.lastSnapshot) : null;
    const target = this.selectedAtomId || active?.id || this.options.workflow.find((step) => step.enabled)?.id || this.options.workflow[0]?.id || "";
    this.selectedAtomId = target;
    if (level === "story" && this.lastSnapshot) {
      const storyAtoms = storyAtomIdsForSnapshot(this.lastSnapshot).filter((atomId) => this.options.workflow.some((step) => step.id === atomId));
      this.sceneManager?.setStoryFocus(storyAtoms);
    }
    this.sceneManager?.setViewLevel(level, target);
    if (level === "surface" && target && this.lastSnapshot) {
      this.nextStepSheet.style.display = "none";
      this.goalCoreSheet.style.display = "none";
      this.memorySheet.style.display = "none";
      this.costSheet.style.display = "none";
      this.actionRing.style.display = "none";
      this.storyLensSheet.style.display = "none";
      this.objectLensSheet.style.display = "block";
      this.renderObjectLens(this.lastSnapshot);
    } else if (level === "story" && this.lastSnapshot) {
      this.nextStepSheet.style.display = "none";
      this.goalCoreSheet.style.display = "none";
      this.memorySheet.style.display = "none";
      this.costSheet.style.display = "none";
      this.actionRing.style.display = "none";
      this.objectLensSheet.style.display = "none";
      this.storyLensSheet.style.display = "block";
      this.renderStoryLens(this.lastSnapshot);
    } else {
      this.goalCoreSheet.style.display = "none";
      this.memorySheet.style.display = "none";
      this.costSheet.style.display = "none";
      this.objectLensSheet.style.display = "none";
      this.storyLensSheet.style.display = "none";
    }
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
    this.nextStepSheet.style.display = "none";
    this.goalCoreSheet.style.display = "none";
    this.memorySheet.style.display = "none";
    this.costSheet.style.display = "none";
    this.objectLensSheet.style.display = "none";
    this.storyLensSheet.style.display = "none";
    this.bottomHud.style.display = "none";
    const fallback = document.createElement("div");
    fallback.dataset.role = "map-fallback";
    fallback.style.cssText = "position: absolute; inset: 56px 0 0 0; overflow: auto; padding: 16px; background: #0D0F14;";
    this.root.appendChild(fallback);
    this.options.engine.onSnapshot((snapshot) => {
      fallback.innerHTML = fallbackHtml(this.options.workflow, snapshot, this.options.projectBrief);
    });
    fallback.innerHTML = fallbackHtml(this.options.workflow, this.options.engine.snapshot(), this.options.projectBrief);
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

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

function compactText(value: string | null | undefined, max = 520): string {
  const text = (value || "").trim();
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}…`;
}

function fallbackHtml(workflow: WorkflowStep[], snapshot: EngineSnapshot, projectBrief: ProjectBrief | null): string {
  return `
    <div style="display: grid; gap: 10px;">
      <div style="font-size: 13px; color: #7A7E92;">WebGL unavailable. The same event replay state is shown as an accessible list.</div>
      ${projectBrief ? `
        <div data-role="goal-core-sheet" style="padding: 12px; border: 1px solid #7A5C23; border-radius: 8px; background: #141822;">
          <div style="font-size: 11px; color: #D9B84D; text-transform: uppercase; font-weight: 850;">Goal Core</div>
          <div style="font-size: 15px; font-weight: 850; margin-top: 4px;">${escapeHtml(projectBrief.title || projectBrief.name)}</div>
          <div style="font-size: 12px; color: #C7CAD6; margin-top: 6px;">${escapeHtml(projectBrief.summary || "")}</div>
        </div>
      ` : ""}
      ${snapshot.nextStepPacket ? `
        <div data-role="next-step-sheet" style="padding: 12px; border: 1px solid #2A3042; border-radius: 8px; background: #141822;">
          <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Next</div>
          <div style="font-size: 15px; font-weight: 850; margin-top: 4px;">${escapeHtml(snapshot.nextStepPacket.title || snapshot.nextStepPacket.step)}</div>
          <div style="font-size: 12px; color: #C7CAD6; margin-top: 6px;">${escapeHtml(snapshot.nextStepPacket.objective || snapshot.nextStepPacket.whyNow || "")}</div>
        </div>
      ` : ""}
      <div data-role="memory-core-sheet" style="padding: 12px; border: 1px solid #254A50; border-radius: 8px; background: #101923;">
        ${memoryStatusCard(snapshot)}
      </div>
      <div data-role="cost-sheet" style="padding: 12px; border: 1px solid #7A5C23; border-radius: 8px; background: #14120C;">
        ${costSummaryCard(snapshot.cost)}
        ${budgetGateControls(snapshot.cost)}
      </div>
      ${snapshot.latestDigest ? `
        <div data-role="narrative-digest" style="padding: 12px; border: 1px solid #2A3042; border-radius: 8px; background: #141822;">
          <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Recent story</div>
          <div style="font-size: 14px; font-weight: 850; margin-top: 4px;">${escapeHtml(snapshot.latestDigest.title)}</div>
          <div style="font-size: 12px; color: #C7CAD6; margin-top: 6px;">${escapeHtml(snapshot.latestDigest.summary)}</div>
        </div>
      ` : ""}
      ${narrationForSnapshot(snapshot) ? `
        <div data-role="narrator-dialogue" style="padding: 12px; border: 1px solid #7A5C23; border-radius: 8px; background: #11131D;">
          <div style="font-size: 11px; color: #D9B84D; text-transform: uppercase; font-weight: 900;">${escapeHtml(narrationForSnapshot(snapshot)?.speaker || "Narrator")}</div>
          <div style="font-family: Georgia, 'Times New Roman', serif; font-size: 15px; line-height: 1.38; color: #F4F0DD; margin-top: 6px;">${escapeHtml(narrationForSnapshot(snapshot)?.text || "")}</div>
        </div>
      ` : ""}
      ${snapshot.discussion.length > 0 ? `
        <div data-role="discussion-log" style="padding: 12px; border: 1px solid #2A3042; border-radius: 8px; background: #141822;">
          <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Discussion</div>
          <div style="font-size: 12px; color: #C7CAD6; margin-top: 6px;">${escapeHtml(snapshot.discussion[snapshot.discussion.length - 1].speaker)} · ${escapeHtml(snapshot.discussion[snapshot.discussion.length - 1].text)}</div>
        </div>
      ` : ""}
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

export function costSummaryCard(cost: CostSnapshot): string {
  const tokenTotal = tokenCount(cost);
  const budgetRows = [
    cost.runBudgetUsd !== null
      ? `Run budget ${formatUsd(cost.runBudgetUsd)}${cost.remainingRunBudgetUsd !== null ? ` · ${formatUsd(cost.remainingRunBudgetUsd)} left` : ""}`
      : "Run budget unset",
    cost.phaseBudgetUsd !== null
      ? `Phase budget ${formatUsd(cost.phaseBudgetUsd)}${cost.remainingPhaseBudgetUsd !== null ? ` · ${formatUsd(cost.remainingPhaseBudgetUsd)} left` : ""}`
      : "Phase budget unset",
    cost.runHalted ? "Run halted by budget gate" : "Run not halted",
    ...cost.openBudgetGateIds.map((gateId) => `gate open: ${gateId}`),
    ...cost.warnings.map((level) => `warning: ${level}`),
    ...cost.exceeded.map((level) => `exceeded: ${level}`),
  ];
  const rateCardRows = [
    ...cost.rateCardVersions.map((version) => `version: ${version}`),
    ...cost.rateCardRefs.map((ref) => `ref: ${ref}`),
    ...cost.missingRateCardVersions.map((version) => `missing: ${version}`),
  ];

  return `
    <div data-role="cost-summary-card" style="display: grid; gap: 10px;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(142px, 1fr)); gap: 7px;">
        ${sheetField("Effective", formatUsd(cost.effectiveUsd))}
        ${sheetField("Provider", formatUsd(cost.providerReportedUsd))}
        ${sheetField("Estimated", formatUsd(cost.estimatedUsd))}
        ${sheetField("Unknown", String(cost.unknownCostCount))}
        ${sheetField("Tokens", `${formatInteger(tokenTotal)} total`)}
      </div>
      ${sheetSection("Budget state", budgetRows, "No budget state has been recorded yet.")}
      ${sheetSection("Rate cards", rateCardRows, "No rate-card snapshots have been referenced yet.")}
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px;">
        ${costBucketRail("Provider", cost.byProvider, "cost-provider-rail")}
        ${costBucketRail("Model", cost.byModel, "cost-model-rail")}
        ${costBucketRail("Role", cost.byRole, "cost-role-rail")}
        ${costBucketRail("Phase", cost.byPhase, "cost-phase-rail")}
        ${costBucketRail("Atom", cost.byAtom, "cost-atom-rail")}
        ${costSourceRail(cost)}
      </div>
    </div>
  `;
}

export function budgetGateControls(cost: CostSnapshot): string {
  if (cost.openBudgetGateIds.length === 0) {
    return `
      <div data-role="budget-gate-control" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 5px;">Budget gates</div>
        <div style="font-size: 12px; color: #C7CAD6; line-height: 1.35;">No budget gate is waiting. Defaults stay advisory unless hard caps are explicitly enabled.</div>
      </div>
    `;
  }
  const suggestedRunBudget = suggestRunBudget(cost);
  const cards = cost.openBudgetGateIds.map((gateId) => `
    <div data-role="budget-gate-card" data-gate-id="${escapeHtml(gateId)}" style="display: grid; gap: 8px; padding: 10px; border: 1px solid rgba(224,155,42,0.34); border-radius: 8px; background: rgba(224,155,42,0.08);">
      <div style="display: flex; align-items: start; justify-content: space-between; gap: 8px;">
        <div style="min-width: 0;">
          <div style="font-size: 10px; color: #E09B2A; text-transform: uppercase; font-weight: 900;">Budget gate waiting</div>
          <div style="font-size: 13px; color: #E8EAF0; font-weight: 900; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(gateId)}</div>
        </div>
        <span style="${refChipStyle()}">${escapeHtml(cost.runHalted ? "halted" : "pending")}</span>
      </div>
      <div style="display: grid; grid-template-columns: minmax(0, 1fr) repeat(3, minmax(82px, auto)); gap: 7px; align-items: center;">
        <input data-role="budget-gate-run-budget" data-gate-id="${escapeHtml(gateId)}" type="number" min="0" step="0.01" value="${escapeHtml(suggestedRunBudget)}" aria-label="New run budget" style="min-width: 0; height: 36px; box-sizing: border-box; border: 1px solid rgba(232,234,240,0.14); border-radius: 999px; background: #10141E; color: #E8EAF0; padding: 0 11px; font: 800 12px Inter, system-ui, sans-serif;" />
        <button data-budget-gate-action="approved" data-gate-id="${escapeHtml(gateId)}" style="${smallCostButtonStyle("#41C7C7")}">Continue</button>
        <button data-budget-gate-action="raise" data-gate-id="${escapeHtml(gateId)}" style="${smallCostButtonStyle("#D9B84D")}">Raise</button>
        <button data-budget-gate-action="reject" data-gate-id="${escapeHtml(gateId)}" style="${smallCostButtonStyle("#D96A6A")}">Stop</button>
      </div>
    </div>
  `).join("");

  return `
    <div data-role="budget-gate-control" style="display: grid; gap: 7px;">
      <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Budget gate controls</div>
      ${cards}
    </div>
  `;
}

export function budgetDecisionPayload(
  cost: CostSnapshot,
  decision: BudgetGateDecision,
  reason: string,
  newRunBudgetUsd: number | null,
): BudgetGateDecisionBody {
  const runBudget = newRunBudgetUsd ?? cost.runBudgetUsd;
  return {
    decision,
    reason,
    new_run_budget_usd: newRunBudgetUsd,
    new_phase_budget_usd: null,
    budget_at_decision: {
      run_budget_usd: runBudget,
      phase_budget_usd: cost.phaseBudgetUsd,
      remaining_run_budget_usd: newRunBudgetUsd !== null
        ? Math.max(0, newRunBudgetUsd - cost.effectiveUsd)
        : cost.remainingRunBudgetUsd,
      remaining_phase_budget_usd: cost.remainingPhaseBudgetUsd,
    },
  };
}

function costBucketRail(label: string, buckets: Record<string, CostBucket>, role: string): string {
  const rows = Object.entries(buckets)
    .sort(([, a], [, b]) => (b.effectiveUsd - a.effectiveUsd) || (tokenCount(b) - tokenCount(a)))
    .slice(0, 5);
  const body = rows.length > 0
    ? rows.map(([name, bucket]) => costBucketRow(name, bucket)).join("")
    : `<div style="${sheetEmptyStyle()}">No ${label.toLowerCase()} cost rows yet.</div>`;
  return `
    <div data-role="${role}" style="display: grid; gap: 6px;">
      <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">${escapeHtml(label)}</div>
      <div style="display: grid; gap: 5px;">${body}</div>
    </div>
  `;
}

function costBucketRow(name: string, bucket: CostBucket): string {
  const unknown = bucket.unknownCostCount > 0 ? ` · ${bucket.unknownCostCount} unknown` : "";
  const detail = `${formatUsd(bucket.effectiveUsd)} · ${formatInteger(tokenCount(bucket))} tokens${unknown}`;
  return `<div style="${sheetLineStyle()}"><strong style="color: #E8EAF0;">${escapeHtml(name)}</strong><br>${escapeHtml(detail)}</div>`;
}

function costSourceRail(cost: CostSnapshot): string {
  const rows = Object.entries(cost.sourceCounts)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a);
  const body = rows.length > 0
    ? rows.map(([source, count]) => `<span style="${refChipStyle()}">${escapeHtml(source)}: ${formatInteger(count)}</span>`).join("")
    : `<span style="${emptyChipStyle()}">No usage sources recorded.</span>`;
  return `
    <div data-role="cost-source-rail" style="${sheetPanelStyle()}">
      <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 6px;">Sources</div>
      <div style="display: flex; flex-wrap: wrap; gap: 6px;">${body}</div>
    </div>
  `;
}

function tokenCount(bucket: CostBucket): number {
  return bucket.inputTokens + bucket.outputTokens + bucket.cacheReadTokens + bucket.cacheWriteTokens + bucket.reasoningTokens;
}

function formatInteger(value: number): string {
  return Math.round(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function suggestRunBudget(cost: CostSnapshot): string {
  const current = cost.runBudgetUsd ?? cost.effectiveUsd;
  const suggested = Math.max(100, current * 1.5, cost.effectiveUsd + 25);
  return suggested.toFixed(2);
}

function inputNumberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

export function memoryStatusCard(snapshot: EngineSnapshot): string {
  const status = snapshot.memPalaceStatus;
  const initialized = status?.initialized ? "Initialized" : "Not initialized";
  const availability = status?.available ? "CLI available" : "CLI unavailable";
  const wakeHash = status?.wakeUpHash ? status.wakeUpHash.slice(0, 16) : "No wake-up hash";
  const bytes = status ? formatBytes(status.wakeUpBytes) : "0 B";
  const wakeup = compactText(status?.cached_wakeup, 760);
  const lastSearch = compactText(status?.last_search, 420);
  const refs = status?.memoryRefs ?? [];
  const roleWings = Object.entries(status?.roleWings ?? {});
  const costAccounting = status?.costAccounting ?? {};
  const costNote = typeof costAccounting.reason === "string"
    ? costAccounting.reason
    : "No memory provider cost telemetry has been recorded.";
  const recent = snapshot.memoryEvents.slice(-5).reverse();
  const error = status?.error
    ? `<div style="font-size: 12px; color: #D96A6A; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(status.error)}</div>`
    : "";
  const recentRows = recent.length > 0
    ? recent.map((event) => {
      const detail = event.error
        ? event.error
        : typeof event.hashChanged === "boolean"
          ? `${event.hashChanged ? "memory changed" : "memory unchanged"}${event.wakeUpHash ? ` · ${event.wakeUpHash.slice(0, 12)}` : ""}`
        : event.query
          ? `query: ${event.query}${event.results !== null ? ` · ${event.results} results` : ""}`
          : event.wakeUpHash
            ? `wake: ${event.wakeUpHash.slice(0, 12)}`
            : event.eventId || "";
      return `<div style="${sheetLineStyle()}"><strong style="color: #E8EAF0;">${escapeHtml(event.type.replace(/_/g, " "))}</strong><br>${escapeHtml(detail || "Memory state recorded.")}</div>`;
    }).join("")
    : `<div style="${sheetEmptyStyle()}">No memory events have landed in this replay window yet.</div>`;

  return `
    <div data-role="memory-status-card" style="display: grid; gap: 9px;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(156px, 1fr)); gap: 7px;">
        ${sheetField("Status", `${initialized} · ${availability}`)}
        ${sheetField("Wing", status?.wing || "No project wing resolved.")}
        ${sheetField("Wake hash", wakeHash)}
        ${sheetField("Packet size", bytes)}
      </div>
      ${error}
      <div data-role="memory-wakeup-preview" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 5px;">Wake-up preview</div>
        <div style="font-size: 12px; color: #D9D2B2; line-height: 1.36; white-space: pre-wrap; overflow-wrap: anywhere;">${escapeHtml(wakeup || "No cached wake-up packet is available yet.")}</div>
      </div>
      <div data-role="memory-last-search" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 5px;">Last search</div>
        <div style="font-size: 12px; color: #C7CAD6; line-height: 1.36; white-space: pre-wrap; overflow-wrap: anywhere;">${escapeHtml(lastSearch || "No memory search has been recorded yet.")}</div>
      </div>
      <div data-role="memory-role-wings" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 5px;">Role wings</div>
        <div style="display: flex; flex-wrap: wrap; gap: 6px;">${roleWings.length > 0 ? roleWings.slice(0, 8).map(([role, wing]) => `<span style="${refChipStyle()}">${escapeHtml(role)}: ${escapeHtml(wing)}</span>`).join("") : `<span style="${emptyChipStyle()}">No role wings reserved yet.</span>`}</div>
      </div>
      <div data-role="memory-cost-accounting" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 5px;">Cost accounting</div>
        <div style="font-size: 12px; color: #C7CAD6; line-height: 1.36; overflow-wrap: anywhere;">${escapeHtml(costNote)}</div>
      </div>
      ${sheetRefs("Memory refs", refs)}
      <div data-role="memory-event-rail" style="display: grid; gap: 6px;">
        <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Recent memory events</div>
        <div style="display: grid; gap: 5px;">${recentRows}</div>
      </div>
    </div>
  `;
}

function narrationForSnapshot(snapshot: EngineSnapshot): NarrationCue | null {
  const digest = snapshot.latestDigest;
  if (digest) {
    const highlight = digest.highlights[0]?.text || "";
    const text = [digest.summary, highlight].filter(Boolean).join(" ");
    return {
      key: `digest:${digest.digestId}`,
      speaker: "Run Narrator",
      title: digest.title || "Recent story",
      text: text || "The latest run window has been recorded.",
      sourceLabel: digest.sourceEventIds.length > 0
        ? `Sources ${digest.sourceEventIds.slice(0, 3).map((id) => `event:${id}`).join(" ")}`
        : "Sources pending",
      mode: snapshot.live ? "live narration" : "replay narration",
    };
  }
  const entry = snapshot.discussion[snapshot.discussion.length - 1];
  if (entry) {
    return {
      key: `discussion:${entry.discussionEntryId}`,
      speaker: entry.speaker || "Council",
      title: entry.entryType.replace(/_/g, " "),
      text: entry.text,
      sourceLabel: entry.sourceRefs.slice(0, 3).join(" ") || "Sources pending",
      mode: snapshot.live ? "live discussion" : "replay discussion",
    };
  }
  return null;
}

function intentsForStep(snapshot: EngineSnapshot, step: string): {
  queued: Record<string, unknown>[];
  applied: OperatorIntentState[];
  ignored: OperatorIntentState[];
} {
  const queued = [...(snapshot.nextStepPacket?.step === step ? snapshot.nextStepPacket.queuedIntents : [])];
  const seenQueued = new Set(queued.map((intent) => stringValue(intent.client_intent_id, "")).filter(Boolean));
  for (const intent of Object.values(snapshot.pendingIntents)) {
    if (intent.atomId !== null && intent.atomId !== step) {
      continue;
    }
    if (seenQueued.has(intent.clientIntentId)) {
      continue;
    }
    queued.push({
      client_intent_id: intent.clientIntentId,
      kind: intent.kind,
      atom_id: intent.atomId,
      status: intent.status,
    });
    seenQueued.add(intent.clientIntentId);
  }
  const appliesToStep = (intent: OperatorIntentState): boolean => {
    return intent.atomId === step || intent.step === step || intent.atomId === null;
  };
  return {
    queued,
    applied: Object.values(snapshot.appliedIntents).filter(appliesToStep),
    ignored: Object.values(snapshot.ignoredIntents).filter(appliesToStep),
  };
}

function sheetField(label: string, value: string): string {
  return `
    <div style="${sheetPanelStyle()}">
      <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 4px;">${escapeHtml(label)}</div>
      <div style="font-size: 12px; color: #E8EAF0; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(value)}</div>
    </div>
  `;
}

function demoReadinessLabel(packet: NextStepPacket): string {
  const compatibility = packet.demoCompatibility || "unknown";
  return packet.demoRequested
    ? `Requested · ${compatibility}`
    : `Not requested · ${compatibility}`;
}

export function functionalMiniSprintPanel(snapshot: EngineSnapshot): string {
  const sprint = snapshot.functional.currentMiniSprint;
  if (!sprint) {
    return `
      <div data-role="functional-mini-sprint" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 4px;">Mini-sprint</div>
        <div style="font-size: 12px; color: #AEB4C6; line-height: 1.35;">No functional mini-sprint has been planned yet.</div>
      </div>
    `;
  }
  const acceptance = sprint.acceptance;
  const verdict = acceptance
    ? acceptance.passed ? "Accepted" : "Blocked"
    : "Not evaluated";
  const stepRows = sprint.steps.length > 0
    ? sprint.steps.slice(-4).map((step) => `${step.stepKind || step.stepId}: ${step.status}`).join(" · ")
    : "No functional steps completed yet.";
  const blockers = acceptance?.blockingFindings ?? [];
  const demoGate = demoGateLabel(sprint);
  return `
    <div data-role="functional-mini-sprint" style="display: grid; gap: 8px;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 8px;">
        ${sheetField("Mini-sprint", `${sprint.title || sprint.miniSprintId}: ${sprint.objective || "Objective pending."}`)}
        ${sheetField("Acceptance", verdict)}
        ${sheetField("Demo gate", demoGate)}
      </div>
      ${sheetSection("Functional steps", [stepRows], "No functional step state has landed yet.")}
      ${sheetRefs("Functional evidence", snapshot.functional.evidenceRefs)}
      ${sheetSection("Blocking findings", blockers, "No blocking findings recorded.")}
      ${functionalAcceptanceActions(acceptance)}
    </div>
  `;
}

function functionalAcceptanceActions(acceptance: { passed: boolean; recommendedActions?: string[] } | null): string {
  if (!acceptance || acceptance.passed) {
    return "";
  }
  const actions = new Set(acceptance.recommendedActions ?? ["repair_loop", "hero_review", "operator_override"]);
  return `
    <div data-role="functional-acceptance-actions" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr)); gap: 7px;">
      ${actions.has("repair_loop") ? `<button data-action="next-functional-repair" style="${ghostButtonStyle()}">Repair</button>` : ""}
      ${actions.has("hero_review") ? `<button data-action="next-functional-hero" style="${ghostButtonStyle()}">Hero</button>` : ""}
      ${actions.has("operator_override") ? `<button data-action="next-functional-override" style="${ghostButtonStyle()}">Override</button>` : ""}
    </div>
  `;
}

function demoGateLabel(sprint: { demoRequested: boolean; demoCompatibility: string | null; demoConfidence?: string | null; demoReason?: string | null }): string {
  const requested = sprint.demoRequested ? "Requested" : "Not requested";
  const compatibility = sprint.demoCompatibility || "unknown";
  const confidence = sprint.demoConfidence ? ` · ${sprint.demoConfidence}` : "";
  const reason = sprint.demoReason ? ` · ${sprint.demoReason}` : "";
  return `${requested} · ${compatibility}${confidence}${reason}`;
}

export function heroRosterPanel(snapshot: EngineSnapshot): string {
  const active = snapshot.heroes?.active ?? [];
  const retiredCount = snapshot.heroes?.retired?.length ?? 0;
  if (active.length === 0) {
    return `
      <div data-role="hero-roster-panel" style="${sheetPanelStyle()}">
        <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 4px;">Hero roster</div>
        <div style="font-size: 12px; color: #AEB4C6; line-height: 1.35;">No temporary Hero reviewer is active yet.</div>
      </div>
    `;
  }
  const rows = active.slice(0, 4).map((hero) => {
    const target = hero.targetStep || hero.targetDeliverable || hero.consultationTrigger || "run";
    const term = hero.termMode || "term pending";
    return `${hero.name}: ${term} for ${target}`;
  });
  return `
    <div data-role="hero-roster-panel" style="display: grid; gap: 7px;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr)); gap: 8px;">
        ${sheetField("Active Heroes", `${active.length}`)}
        ${sheetField("Retired Heroes", `${retiredCount}`)}
      </div>
      ${sheetSection("Hero assignments", rows, "No active Hero assignments.")}
    </div>
  `;
}

type HeroInvitePayloadInput = {
  mission: string;
  name: string;
  watchFor: string;
  provider: string;
  model: string;
  termMode: string;
  step: string | null;
  scope: string | null;
};

export function heroInvitePayload(input: HeroInvitePayloadInput): Record<string, unknown> {
  const mission = input.mission.trim();
  const name = input.name.trim() || "Hero Reviewer";
  return {
    instruction: mission,
    scope: input.scope,
    source: "map",
    hero: {
      name,
      provider: input.provider.trim() || "primary",
      model: input.model.trim(),
      mission,
      watch_for: input.watchFor.trim() || "risks and blind spots",
      term: { mode: normalizeHeroTermMode(input.termMode) },
    },
    target: {
      step: input.step,
      deliverable: null,
      consultation_trigger: null,
    },
  };
}

function sheetSection(label: string, rows: string[], empty: string): string {
  const body = rows.length > 0
    ? rows.slice(0, 4).map((row) => `<div style="${sheetLineStyle()}">${escapeHtml(row)}</div>`).join("")
    : `<div style="${sheetEmptyStyle()}">${escapeHtml(empty)}</div>`;
  return `
    <div style="display: grid; gap: 6px;">
      <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">${escapeHtml(label)}</div>
      <div style="display: grid; gap: 5px;">${body}</div>
    </div>
  `;
}

function sheetRefs(label: string, refs: string[]): string {
  const chips = refs.length > 0
    ? refs.slice(0, 8).map((ref) => `<span style="${refChipStyle()}">${escapeHtml(ref)}</span>`).join("")
    : `<span style="${emptyChipStyle()}">None</span>`;
  return `
    <div style="display: grid; gap: 6px;">
      <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">${escapeHtml(label)}</div>
      <div style="display: flex; flex-wrap: wrap; gap: 6px;">${chips}</div>
    </div>
  `;
}

function latestDigestPanel(snapshot: EngineSnapshot): string {
  const digest = snapshot.latestDigest;
  if (!digest) {
    return "";
  }
  const highlightRows = digest.highlights.slice(0, 3).map((highlight) => highlight.text);
  return `
    <div data-role="narrative-digest" style="display: grid; gap: 7px; padding: 10px; border: 1px solid rgba(65,199,199,0.22); border-radius: 8px; background: rgba(65,199,199,0.07);">
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
        <div style="min-width: 0;">
          <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Recent story</div>
          <div style="font-size: 13px; color: #E8EAF0; font-weight: 850; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(digest.title)}</div>
        </div>
        <div style="color: #41C7C7; font-size: 11px; font-weight: 850; white-space: nowrap;">${escapeHtml(String(digest.window.event_count ?? digest.sourceEventIds.length))} events</div>
      </div>
      <div style="font-size: 12px; color: #C7CAD6; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(digest.summary)}</div>
      ${sheetSection("Highlights", highlightRows, "No sourced highlights yet.")}
      ${digest.risks.length > 0 ? sheetSection("Risks", digest.risks, "No risks.") : ""}
    </div>
  `;
}

function discussionPanel(snapshot: EngineSnapshot, step: string): string {
  const rows = snapshot.discussion
    .filter((entry) => entry.atomId === step || entry.atomId === null || entry.atomId === "persona_forum")
    .slice(-4)
    .reverse();
  const highlights = snapshot.discussionHighlights
    .filter((highlight) => highlight.atomId === step || highlight.atomId === null || highlight.atomId === "persona_forum")
    .slice(-2)
    .map((highlight) => highlight.text);
  if (rows.length === 0 && highlights.length === 0) {
    return "";
  }
  const body = rows.map((entry) => {
    const label = `${entry.speaker} · ${entry.entryType.replace(/_/g, " ")}`;
    return `<div style="${sheetLineStyle()}"><strong style="color: #E8EAF0;">${escapeHtml(label)}</strong><br>${escapeHtml(entry.text)}</div>`;
  });
  return `
    <div data-role="discussion-log" style="display: grid; gap: 7px;">
      <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Discussion</div>
      <div style="display: grid; gap: 5px;">
        ${body.join("")}
        ${highlights.map((text) => `<div style="${sheetLineStyle()}"><strong style="color: #41C7C7;">Highlight</strong><br>${escapeHtml(text)}</div>`).join("")}
      </div>
    </div>
  `;
}

function founderCard(persona: ProjectBrief["founding_team"][number]): string {
  const title = [persona.name, persona.archetype].filter(Boolean).join(" · ");
  const body = persona.stance || persona.mandate || "No stance recorded yet.";
  const veto = persona.veto_scope ? `<div style="margin-top: 5px; color: #E09B2A; font-size: 11px; font-weight: 850;">${escapeHtml(persona.veto_scope)}</div>` : "";
  return `
    <div style="${sheetPanelStyle()}">
      <div style="font-size: 12px; color: #E8EAF0; font-weight: 900; overflow-wrap: anywhere;">${escapeHtml(title)}</div>
      <div style="font-size: 12px; color: #C7CAD6; line-height: 1.35; margin-top: 5px; overflow-wrap: anywhere;">${escapeHtml(body)}</div>
      ${veto}
    </div>
  `;
}

export function storyDigestCard(digest: NarrativeDigest): string {
  const highlights = digest.highlights.slice(0, 3).map((highlight) => highlight.text);
  const refs = [
    ...digest.sourceEventIds.slice(0, 5).map((eventId) => `event:${eventId}`),
    ...digest.artifactRefs.slice(0, 4),
    ...memoryProvenanceRefs(digest.memoryRefs, digest.wakeUpHash),
  ];
  return `
    <div data-role="story-card" style="display: grid; gap: 7px; padding: 10px; border: 1px solid rgba(217,184,77,0.24); border-radius: 8px; background: rgba(217,184,77,0.07);">
      <div style="display: flex; align-items: start; justify-content: space-between; gap: 8px;">
        <div style="min-width: 0;">
          <div style="font-size: 13px; color: #E8EAF0; font-weight: 900; line-height: 1.2; overflow-wrap: anywhere;">${escapeHtml(digest.title || "Story digest")}</div>
          <div style="font-size: 10px; color: #8C92A8; margin-top: 3px; text-transform: uppercase; font-weight: 850;">${escapeHtml(String(digest.window.event_count ?? digest.sourceEventIds.length))} events</div>
        </div>
        ${digest.nextStepHint ? `<span style="${refChipStyle()}">${escapeHtml(digest.nextStepHint)}</span>` : ""}
      </div>
      <div style="font-size: 12px; color: #D9D2B2; line-height: 1.36; overflow-wrap: anywhere;">${escapeHtml(digest.summary || "No summary recorded.")}</div>
      ${sheetSection("Highlights", highlights, "No sourced highlights yet.")}
      ${digest.risks.length > 0 ? sheetSection("Risks", digest.risks.slice(0, 2), "No risks.") : ""}
      ${sheetRefs("Sources", refs)}
    </div>
  `;
}

export function discussionEntryCard(entry: DiscussionEntry): string {
  const refs = [
    ...entry.sourceRefs.slice(0, 4),
    ...entry.artifactRefs.slice(0, 3),
    ...memoryProvenanceRefs(entry.memoryRefs, entry.wakeUpHash),
  ];
  return `
    <div data-role="story-discussion-card" style="${sheetLineStyle()}">
      <strong style="color: #E8EAF0;">${escapeHtml(entry.speaker)} · ${escapeHtml(entry.entryType.replace(/_/g, " "))}</strong>
      <br>${escapeHtml(entry.text)}
      <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px;">${refs.map((ref) => `<span style="${refChipStyle()}">${escapeHtml(ref)}</span>`).join("") || `<span style="${emptyChipStyle()}">Sources pending</span>`}</div>
    </div>
  `;
}

export function discussionHighlightCard(highlight: DiscussionHighlight): string {
  const refs = [
    ...highlight.sourceRefs.slice(0, 4),
    ...highlight.artifactRefs.slice(0, 3),
    ...memoryProvenanceRefs(highlight.memoryRefs, highlight.wakeUpHash),
  ];
  return `
    <div data-role="story-highlight-card" style="${sheetLineStyle()}">
      <strong style="color: #E8EAF0;">${escapeHtml(highlight.highlightType.replace(/_/g, " "))}</strong>
      <br>${escapeHtml(highlight.text)}
      <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px;">${refs.map((ref) => `<span style="${refChipStyle()}">${escapeHtml(ref)}</span>`).join("") || `<span style="${emptyChipStyle()}">Sources pending</span>`}</div>
    </div>
  `;
}

function memoryProvenanceRefs(memoryRefs: string[], wakeUpHash: string | null): string[] {
  return [
    ...memoryRefs.slice(0, 4).map((ref) => `memory: ${ref}`),
    ...(wakeUpHash ? [`wake: ${wakeUpHash.slice(0, 12)}`] : []),
  ];
}

const DEMO_STATUS_COLORS: Record<DemoStatus, string> = {
  planned: "#8C92A8",
  capturing: "#E09B2A",
  captured: "#41C7C7",
  presented: "#D9B84D",
  failed: "#D96A6A",
  skipped: "#6A748C",
};

const DEMO_STATUS_LABELS: Record<DemoStatus, string> = {
  planned: "Planned",
  capturing: "Capturing",
  captured: "Captured",
  presented: "Ready",
  failed: "Failed",
  skipped: "Skipped",
};

export function demoArtifactUrl(projectId: string, demo: DemoPlan, artifact: DemoArtifact): string {
  if (!projectId || !demo.demoId || !artifact.ref) {
    return "";
  }
  const prefix = `.orchestrator/demos/${demo.demoId}/`;
  const suffix = artifact.ref.startsWith(prefix) ? artifact.ref.slice(prefix.length) : artifact.ref;
  const segments = suffix.split("/").filter(Boolean).map((part) => encodeURIComponent(part));
  if (segments.length === 0) {
    return "";
  }
  return `/api/projects/${encodeURIComponent(projectId)}/demos/${encodeURIComponent(demo.demoId)}/${segments.join("/")}`;
}

function viewportLabel(viewport: DemoViewport | null): string {
  if (!viewport) {
    return "";
  }
  const name = viewport.name ?? "";
  const dims = viewport.width && viewport.height ? `${viewport.width}×${viewport.height}` : "";
  return [name, dims].filter(Boolean).join(" · ");
}

function demoStatusChip(status: DemoStatus): string {
  const color = DEMO_STATUS_COLORS[status] ?? "#8C92A8";
  const label = DEMO_STATUS_LABELS[status] ?? status;
  return `<span style="display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 99px; background: ${color}22; color: ${color}; font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px;">${escapeHtml(label)}</span>`;
}

function demoThumbnail(projectId: string, demo: DemoPlan): string {
  const preview = demo.artifacts.find((artifact) => artifact.kind === "gif")
    ?? demo.artifacts.find((artifact) => artifact.kind === "screenshot")
    ?? demo.artifacts.find((artifact) => artifact.ref.endsWith(".gif") || artifact.ref.endsWith(".png"));
  if (!preview) {
    return "";
  }
  const url = demoArtifactUrl(projectId, demo, preview);
  if (!url) {
    return "";
  }
  return `
    <a data-role="demo-thumb-link" href="${escapeHtml(url)}" target="_blank" rel="noopener" style="display: block; border-radius: 8px; overflow: hidden; border: 1px solid rgba(65,199,199,0.24); background: #12141C;">
      <img data-role="demo-thumb" src="${escapeHtml(url)}" alt="Demo preview" loading="lazy" style="display: block; width: 100%; max-height: 180px; object-fit: contain; background: #0B0D14;">
    </a>
  `;
}

function demoArtifactRow(projectId: string, demo: DemoPlan, artifact: DemoArtifact): string {
  const url = demoArtifactUrl(projectId, demo, artifact);
  const label = `${artifact.kind} · ${artifact.ref.split("/").pop() ?? artifact.ref}`;
  const chip = `<span style="${refChipStyle()}">${escapeHtml(label)}</span>`;
  if (!url) {
    return chip;
  }
  return `<a data-role="demo-artifact-link" href="${escapeHtml(url)}" target="_blank" rel="noopener" style="text-decoration: none;">${chip}</a>`;
}

export function storyDemoCard(demo: DemoPlan, projectId: string): string {
  const status = demoStatusChip(demo.status);
  const viewport = viewportLabel(demo.viewport);
  const compatibility = demo.demoCompatibility ? `${demo.demoRequested ? "requested" : "not requested"} · ${demo.demoCompatibility}` : "";
  const meta = [demo.adapter, compatibility, demo.route, viewport].filter(Boolean).join(" · ");
  const artifactChips = demo.artifacts.slice(0, 6).map((artifact) => demoArtifactRow(projectId, demo, artifact)).join("");
  const sourceChips = demo.sourceRefs.slice(0, 5).map((ref) => `<span style="${refChipStyle()}">${escapeHtml(ref)}</span>`).join("");
  const memoryChips = demo.memoryRefs.slice(0, 3).map((ref) => `<span style="${refChipStyle()}">memory: ${escapeHtml(ref)}</span>`).join("");
  const failureNote = demo.status === "failed" && demo.captureError
    ? `<div style="font-size: 11px; color: #D96A6A; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(demo.captureError)}</div>`
    : "";
  const reason = demo.reason ? `<div style="font-size: 12px; color: #D9D2B2; line-height: 1.35; overflow-wrap: anywhere;">${escapeHtml(demo.reason)}</div>` : "";
  const testStatus = demo.testStatus
    ? `<span style="${refChipStyle()}">test: ${escapeHtml(demo.testStatus)}</span>`
    : "";
  const wakeHash = demo.wakeUpHash
    ? `<span style="${refChipStyle()}">wake: ${escapeHtml(demo.wakeUpHash.slice(0, 12))}</span>`
    : "";
  const summary = demo.summaryRef
    ? `<a data-role="demo-summary-link" href="${escapeHtml(demoArtifactUrl(projectId, demo, { ref: demo.summaryRef, kind: "summary", sha256: "", bytes: 0, testStatus: null, viewport: null, eventId: null }))}" target="_blank" rel="noopener" style="text-decoration: none;"><span style="${refChipStyle()}">summary</span></a>`
    : "";

  return `
    <div data-role="demo-card" data-demo-id="${escapeHtml(demo.demoId)}" data-demo-status="${escapeHtml(demo.status)}" style="display: grid; gap: 7px; padding: 10px; border: 1px solid rgba(65,199,199,0.24); border-radius: 8px; background: rgba(65,199,199,0.07);">
      <div style="display: flex; align-items: start; justify-content: space-between; gap: 8px;">
        <div style="min-width: 0;">
          <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Demo · ${escapeHtml(demo.adapter || "demo")}</div>
          <div style="font-size: 13px; color: #E8EAF0; font-weight: 900; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(demo.specPath || demo.demoId)}</div>
          ${meta ? `<div style="font-size: 11px; color: #8C92A8; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(meta)}</div>` : ""}
        </div>
        ${status}
      </div>
      ${demoThumbnail(projectId, demo)}
      ${reason}
      ${failureNote}
      ${artifactChips ? `
        <div style="display: grid; gap: 5px;">
          <div style="font-size: 11px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Artifacts</div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">${artifactChips}${summary}</div>
        </div>
      ` : ""}
      ${sourceChips || memoryChips || testStatus || wakeHash ? `
        <div style="display: flex; flex-wrap: wrap; gap: 6px;">
          ${testStatus}
          ${wakeHash}
          ${memoryChips}
          ${sourceChips}
        </div>
      ` : ""}
    </div>
  `;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function previewExcerptBlock(preview: ArtifactPreview): string {
  if (preview.excerptKind === "binary_placeholder") {
    return `<div style="font-size: 11px; color: #8C92A8; font-style: italic;">${escapeHtml(preview.excerpt)}</div>`;
  }
  const suffix = preview.truncated
    ? `<div style="font-size: 10px; color: #8C92A8; margin-top: 3px; text-transform: uppercase; letter-spacing: 0.5px;">Truncated · ${escapeHtml(preview.excerptKind === "text_tail" ? "tail" : "head")}</div>`
    : "";
  return `
    <pre data-role="preview-excerpt" data-excerpt-kind="${escapeHtml(preview.excerptKind)}" style="margin: 0; padding: 8px; border-radius: 6px; background: #0B0D14; color: #D9D2B2; font-size: 11px; line-height: 1.4; max-height: 180px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere;">${escapeHtml(preview.excerpt)}</pre>
    ${suffix}
  `;
}

export function artifactPreviewCard(preview: ArtifactPreview): string {
  const refName = preview.artifactRef.split("/").pop() || preview.artifactRef;
  const shortHash = preview.hash ? preview.hash.slice(0, 12) : "";
  const atom = preview.producingAtomId
    ? `<span style="${refChipStyle()}">atom: ${escapeHtml(preview.producingAtomId)}</span>`
    : "";
  const mime = preview.mime
    ? `<span style="${refChipStyle()}">${escapeHtml(preview.mime)}</span>`
    : "";
  const hashChip = shortHash
    ? `<span style="${refChipStyle()}">#${escapeHtml(shortHash)}</span>`
    : "";
  const sourceChips = preview.sourceRefs.slice(0, 4)
    .map((ref) => `<span style="${refChipStyle()}">${escapeHtml(ref)}</span>`)
    .join("");

  return `
    <div data-role="preview-card" data-preview-ref="${escapeHtml(preview.artifactRef)}" data-preview-atom="${escapeHtml(preview.producingAtomId ?? "")}" data-excerpt-kind="${escapeHtml(preview.excerptKind)}" style="display: grid; gap: 6px; padding: 10px; border: 1px solid rgba(217,184,77,0.28); border-radius: 8px; background: rgba(217,184,77,0.06);">
      <div style="display: flex; align-items: start; justify-content: space-between; gap: 8px;">
        <div style="min-width: 0;">
          <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850;">Artifact preview</div>
          <div style="font-size: 13px; color: #E8EAF0; font-weight: 900; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(refName)}</div>
          <div style="font-size: 11px; color: #8C92A8; margin-top: 3px; overflow-wrap: anywhere;">${escapeHtml(preview.artifactRef)}</div>
        </div>
        <div style="display: inline-flex; gap: 5px; flex: 0 0 auto;">
          <span style="${refChipStyle()}">${escapeHtml(formatBytes(preview.bytes))}</span>
        </div>
      </div>
      ${previewExcerptBlock(preview)}
      <div style="display: flex; flex-wrap: wrap; gap: 6px;">
        ${atom}
        ${mime}
        ${hashChip}
        ${sourceChips}
      </div>
    </div>
  `;
}

function storyAtomIdsForSnapshot(snapshot: EngineSnapshot): string[] {
  const ids: string[] = [];
  const recentDigests = snapshot.digests.slice(-5);
  for (const digest of recentDigests) {
    for (const eventId of digest.sourceEventIds) {
      const event = snapshot.events.find((item) => item.event_id === eventId);
      if (event) {
        ids.push(eventAtomId(event));
      }
    }
  }
  for (const entry of snapshot.discussion.slice(-5)) {
    ids.push(entry.atomId || "");
  }
  for (const highlight of snapshot.discussionHighlights.slice(-4)) {
    ids.push(highlight.atomId || "");
  }
  ids.push(snapshot.nextStepPacket?.step || "");
  ids.push(activeAtom(snapshot)?.id || "");
  return dedupeStrings(ids.filter(Boolean)).slice(-8);
}

function eventAtomId(event: Record<string, unknown>): string {
  return stringValue(event.atom_id ?? event.step ?? event.name ?? event.gate, "");
}

function storyStepTitle(workflow: WorkflowStep[], atomId: string): string {
  const step = workflow.find((item) => item.id === atomId);
  return step?.title ? `${step.title} · ${atomId}` : atomId;
}

function intentColumn(label: string, rows: string[]): string {
  return `
    <div style="${sheetPanelStyle()}">
      <div style="font-size: 10px; color: #8C92A8; text-transform: uppercase; font-weight: 850; margin-bottom: 6px;">${escapeHtml(label)}</div>
      <div style="display: grid; gap: 5px;">
        ${rows.length > 0 ? rows.slice(0, 4).join("") : `<span style="${emptyChipStyle()}">None</span>`}
      </div>
    </div>
  `;
}

function queuedIntentLabel(intent: Record<string, unknown>): string {
  const id = stringValue(intent.client_intent_id, "queued");
  const kind = stringValue(intent.kind, "intent");
  return `<span style="${intentChipStyle("#D9B84D")}">${escapeHtml(kind)} · ${escapeHtml(id)}</span>`;
}

function intentStateLabel(intent: OperatorIntentState): string {
  const detail = intent.status === "applied"
    ? intent.appliedTo || "applied"
    : intent.reason || "ignored";
  const color = intent.status === "applied" ? "#41C7C7" : "#E09B2A";
  return `<span style="${intentChipStyle(color)}">${escapeHtml(intent.kind)} · ${escapeHtml(detail)}</span>`;
}

function packetInputLabel(input: Record<string, unknown>): string {
  const kind = stringValue(input.kind, "input");
  const ref = stringValue(input.ref ?? input.path ?? input.source, "");
  return ref ? `${kind}: ${ref}` : kind;
}

function objectWhat(step: WorkflowStep, state: string): string {
  if (step.type === "gate") {
    return `Decision point currently ${state}.`;
  }
  if (step.handler === "memory_refresh") {
    return `Memory context object currently ${state}.`;
  }
  if (step.handler === "persona_forum") {
    return `Founding-team context object currently ${state}.`;
  }
  return `Workflow ${step.type} handled by ${step.handler}; current state is ${state}.`;
}

function producedRefsForAtom(snapshot: EngineSnapshot, atomId: string): string[] {
  const refs: string[] = [];
  for (const event of snapshot.events) {
    if (!eventTouchesAtom(event, atomId)) {
      continue;
    }
    refs.push(...arrayOfStrings(event.artifact_refs));
    refs.push(...arrayOfStrings(event.source_refs).filter((ref) => ref.startsWith("artifact:")));
  }
  return dedupeStrings(refs).slice(-8);
}

function sourceEventTouchesAtom(snapshot: EngineSnapshot, eventId: string, atomId: string): boolean {
  const event = snapshot.events.find((item) => item.event_id === eventId);
  return event ? eventTouchesAtom(event, atomId) : false;
}

function eventTouchesAtom(event: Record<string, unknown>, atomId: string): boolean {
  return (
    event.atom_id === atomId ||
    event.step === atomId ||
    event.name === atomId ||
    event.gate === atomId
  );
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function dedupeStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (seen.has(value)) {
      continue;
    }
    seen.add(value);
    out.push(value);
  }
  return out;
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function newClientIntentId(): string {
  const cryptoApi = typeof crypto !== "undefined" ? crypto : null;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return `intent_${cryptoApi.randomUUID()}`;
  }
  const random = Math.random().toString(36).slice(2, 10);
  return `intent_${Date.now().toString(36)}_${random}`;
}

function sheetPanelStyle(): string {
  return "min-width: 0; padding: 9px; border: 1px solid rgba(232,234,240,0.12); border-radius: 8px; background: rgba(16,20,30,0.72);";
}

function sheetLineStyle(): string {
  return "padding: 8px 9px; border: 1px solid rgba(232,234,240,0.10); border-radius: 8px; background: rgba(13,15,20,0.52); color: #C7CAD6; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere;";
}

function refChipStyle(): string {
  return "max-width: 100%; padding: 6px 8px; border: 1px solid rgba(65,199,199,0.26); border-radius: 999px; background: rgba(65,199,199,0.10); color: #C7CAD6; font-size: 11px; font-weight: 750; overflow-wrap: anywhere;";
}

function emptyChipStyle(): string {
  return "display: inline-flex; width: fit-content; padding: 6px 8px; border: 1px solid rgba(232,234,240,0.10); border-radius: 999px; background: rgba(13,15,20,0.42); color: #7A7E92; font-size: 11px; font-weight: 750;";
}

function intentChipStyle(color: string): string {
  return `display: inline-flex; width: fit-content; max-width: 100%; padding: 6px 8px; border: 1px solid ${color}; border-radius: 999px; background: rgba(13,15,20,0.48); color: #E8EAF0; font-size: 11px; font-weight: 800; overflow-wrap: anywhere;`;
}

function tinyNarratorButtonStyle(): string {
  return [
    "height: 26px",
    "border: 1px solid rgba(217,184,77,0.42)",
    "border-radius: 999px",
    "background: rgba(217,184,77,0.08)",
    "color: #D9B84D",
    "font: 900 10px JetBrains Mono, ui-monospace, monospace",
    "letter-spacing: 0",
    "text-transform: uppercase",
    "padding: 0 9px",
  ].join("; ");
}

function objectCommandStyle(color: string): string {
  return [
    "height: 38px",
    "border: 1px solid rgba(232,234,240,0.14)",
    "border-radius: 999px",
    "background: rgba(13,15,20,0.58)",
    `color: ${color}`,
    "font: 900 11px Inter, system-ui, sans-serif",
    "padding: 0 9px",
    "white-space: nowrap",
  ].join("; ");
}

function sheetEmptyStyle(): string {
  return "padding: 9px; border: 1px solid rgba(232,234,240,0.10); border-radius: 8px; background: rgba(13,15,20,0.42); color: #7A7E92; font-size: 12px; line-height: 1.35;";
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

const HERO_TERM_MODES = ["single_consultation", "until_step_complete", "until_deliverable", "manual_dismissal"] as const;

function heroInviteFields(values: { name: string; watchFor: string; provider: string; model: string; termMode: string }): string {
  const termMode = normalizeHeroTermMode(values.termMode);
  return `
    <div data-role="hero-invite-fields" style="display: grid; gap: 8px;">
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 7px;">
        <input data-role="hero-name" value="${escapeHtml(values.name)}" placeholder="Hero name" style="${composeInputStyle()}">
        <input data-role="hero-watch-for" value="${escapeHtml(values.watchFor)}" placeholder="Watch for" style="${composeInputStyle()}">
        <input data-role="hero-provider" value="${escapeHtml(values.provider || "primary")}" placeholder="Provider" style="${composeInputStyle()}">
        <input data-role="hero-model" value="${escapeHtml(values.model)}" placeholder="Model" style="${composeInputStyle()}">
      </div>
      <input data-role="hero-term" type="hidden" value="${escapeHtml(termMode)}">
      <div data-role="hero-term-options" style="display: flex; gap: 7px; overflow-x: auto; padding-bottom: 2px;">
        ${HERO_TERM_MODES.map((mode) => `<button data-hero-term-option="${mode}" style="${heroTermChipStyle(mode === termMode)}">${escapeHtml(heroTermLabel(mode))}</button>`).join("")}
      </div>
    </div>
  `;
}

function heroTermLabel(mode: string): string {
  if (mode === "until_step_complete") {
    return "Step";
  }
  if (mode === "until_deliverable") {
    return "Deliverable";
  }
  if (mode === "manual_dismissal") {
    return "Manual";
  }
  return "One consult";
}

function normalizeHeroTermMode(value: string): string {
  return HERO_TERM_MODES.includes(value as (typeof HERO_TERM_MODES)[number]) ? value : "single_consultation";
}

function composeInputStyle(): string {
  return [
    "height: 38px",
    "min-width: 0",
    "box-sizing: border-box",
    "border: 1px solid var(--line)",
    "border-radius: 999px",
    "background: #10141E",
    "color: #E8EAF0",
    "font: 800 12px Inter, system-ui, sans-serif",
    "padding: 0 12px",
  ].join("; ");
}

function heroTermChipStyle(selected: boolean): string {
  return [
    "height: 32px",
    `border: 1px solid ${selected ? "#D9B84D" : "var(--line)"}`,
    "border-radius: 999px",
    `background: ${selected ? "rgba(217,184,77,0.16)" : "#10141E"}`,
    `color: ${selected ? "#F4D978" : "#C7CAD6"}`,
    "font: 900 11px Inter, system-ui, sans-serif",
    "padding: 0 11px",
    "white-space: nowrap",
  ].join("; ");
}

function composePlaceholder(action: ComposeAction): string {
  if (action === "shape") {
    return "Redirect this object...";
  }
  if (action === "intercept") {
    return "Stop or capture before it proceeds...";
  }
  if (action === "hero") {
    return "Mission for the Hero reviewer...";
  }
  return "Nudge this run...";
}

function ghostButtonStyle(): string {
  return "height: 34px; border: 1px solid var(--line); border-radius: 999px; background: #10141E; color: #C7CAD6; font-size: 12px; font-weight: 800; padding: 0 12px;";
}

function primaryButtonStyle(): string {
  return "height: 44px; border: 0; border-radius: 999px; background: #E8EAF0; color: #0D0F14; font-size: 13px; font-weight: 900;";
}

function smallCostButtonStyle(color: string): string {
  return [
    "height: 36px",
    "border: 1px solid rgba(232,234,240,0.14)",
    "border-radius: 999px",
    "background: rgba(13,15,20,0.58)",
    `color: ${color}`,
    "font: 900 11px Inter, system-ui, sans-serif",
    "padding: 0 10px",
    "white-space: nowrap",
  ].join("; ");
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

// Playwright recording of the full guildr PWA flow at mobile viewport.
//
// 1. Empty projects list
// 2. New Project form — type name + idea
// 3. Submit, land on project detail
// 4. Tap Start Run, navigate to Progress
// 5. Watch the live SSE event log fill as the orchestrator runs
// 6. After the run completes, jump to Artifacts and open one file
//
// Companion shell script (record_demo.sh) boots uvicorn, runs this,
// then ffmpeg-pipes the webm to a palette-optimised gif.

import { chromium, devices } from "playwright";
import { mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, "..");
const OUT_DIR = resolve(REPO, "docs/screenshots/_raw");
mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.BASE_URL || "http://127.0.0.1:8765";
const viewport = { width: 393, height: 852 };

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

async function typeSlowly(page, selector, text, perChar = 30) {
  await page.click(selector);
  for (const ch of text) {
    await page.keyboard.type(ch);
    await pause(perChar);
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({
  ...devices["iPhone 14 Pro"],
  viewport,
  recordVideo: { dir: OUT_DIR, size: viewport },
});
const page = await context.newPage();

// 1. Land on the projects list (empty state)
await page.goto(BASE + "/");
await page.waitForSelector("#project-list");
await pause(1200);

// 2. Tap "+ New Project"
await page.click("text=+ New Project");
await page.waitForSelector("#project-name");
await pause(400);

// 3. Type name + idea
await typeSlowly(page, "#project-name", "Tiny Hello CLI");
await pause(250);
await typeSlowly(
  page,
  "#initial-idea",
  "Build a one-command CLI that prints a friendly hello message.",
  20,
);
await pause(600);

// 4. Submit — SPA navigates to project detail
await page.click("#create-project-btn");
await page.waitForSelector("text=Start Run", { timeout: 5000 });
await pause(1000);

// 5. Tap Start Run, then jump to Progress to watch events
await page.click("text=Start Run");
await pause(400);
await page.click("text=Progress");
await page.waitForSelector("#event-log");
// Give the SSE stream time to receive the full run.
// Dry-run completes in ~1s; live LLM takes minutes — adjust
// DEMO_RUN_WAIT_MS at the shell level to match.
const runWaitMs = parseInt(process.env.DEMO_RUN_WAIT_MS || "5000", 10);
await pause(runWaitMs);

// 6. Hop back, then into Artifacts so the demo ends on real produced files
await page.evaluate(() => window.history.back());
await page.waitForSelector("text=Artifacts");
await pause(400);
await page.click("text=Artifacts");
await page.waitForSelector("#tree-content");
await pause(1500);

// Open one artifact if the tree has tappable entries
const firstFile = await page.$("#tree-content [data-path], #tree-content li, #tree-content button");
if (firstFile) {
  await firstFile.click();
  await pause(2000);
}

await context.close();
await browser.close();
console.log("Wrote raw video to", OUT_DIR);

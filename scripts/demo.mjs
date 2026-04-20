// Playwright script that records the guildr PWA flow at mobile viewport
// and writes a webm video to docs/screenshots/. The companion shell script
// converts that to a gif via ffmpeg.
//
// Run via: scripts/record_demo.sh

import { chromium, devices } from "playwright";
import { mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, "..");
const OUT_DIR = resolve(REPO, "docs/screenshots/_raw");
mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.BASE_URL || "http://127.0.0.1:8765";

// iPhone 14 Pro size — the PWA's canonical surface
const viewport = { width: 393, height: 852 };

async function pause(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeSlowly(page, selector, text, perChar = 40) {
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
await pause(1500);

// 2. Tap "+ New Project"
await page.click("text=+ New Project");
await page.waitForSelector("#project-name");
await pause(500);

// 3. Type the project name + idea
await typeSlowly(page, "#project-name", "Tiny Hello CLI");
await pause(300);
await typeSlowly(
  page,
  "#initial-idea",
  "Build a one-command CLI that prints a friendly hello message.",
  25,
);
await pause(800);

// 4. Submit — backend creates the project and the SPA navigates onward
await page.click("#create-project-btn");
await pause(1800);

// 5. Bounce back to the projects list to show the project landed
await page.evaluate(() => { window.location.hash = "#projects"; });
await page.waitForSelector("#project-list");
await pause(1500);

// 6. Tap into the project to show the per-project shell (Progress tab loads)
const tile = await page.$("#project-list >> div");
if (tile) {
  await tile.click();
  await pause(1500);
}

await context.close();
await browser.close();

console.log("Wrote raw video to", OUT_DIR);

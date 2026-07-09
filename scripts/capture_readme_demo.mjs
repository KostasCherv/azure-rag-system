#!/usr/bin/env node
/**
 * Capture README demo media from the running local app.
 * Prereqs: API on :8000, UI on :3000
 * Usage: node scripts/capture_readme_demo.mjs
 */

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../assets/readme");
const baseUrl = process.env.DEMO_BASE_URL ?? "http://localhost:3000";

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  recordVideo: {
    dir: outDir,
    size: { width: 1440, height: 900 },
  },
});
const page = await context.newPage();

async function shot(name) {
  await page.screenshot({ path: path.join(outDir, name), type: "png" });
}

async function waitForReady() {
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.getByText("Connected").waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
}

console.log("Capturing chat ready state…");
await waitForReady();
await shot("01-chat-ready.png");

console.log("Asking a suggested question…");
await page.getByText("How do I clean the Dyson V10 filter?").click();
await page.waitForTimeout(1200);
await shot("02-chat-question.png");

console.log("Waiting for grounded answer…");
await page
  .getByText(/clean|filter|wash|rinse/i)
  .first()
  .waitFor({ timeout: 45_000 });
await page.waitForTimeout(1500);
await shot("03-chat-answer.png");

console.log("Opening corpus browser…");
await page.goto(`${baseUrl}/corpus`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Refresh" }).waitFor({ timeout: 15_000 });
await page.waitForTimeout(1200);
await shot("04-corpus.png");

await page.waitForTimeout(1000);

const video = page.video();
await context.close();
await browser.close();

if (video) {
  const target = path.join(outDir, "demo-overview.webm");
  const { rename } = await import("node:fs/promises");
  await rename(await video.path(), target);
  console.log(`Saved video to ${target}`);
}

console.log(`Done. Assets in ${outDir}`);

#!/usr/bin/env node
/**
 * Record a repeatable, portfolio-paced walkthrough of the running app.
 * Prereqs: API on :8000, UI on :3000, and a ready Search index.
 * Usage: node scripts/capture_promo_demo.mjs
 */

import {copyFile, mkdir, rename, rm, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'video/package.json'));
const {chromium} = require('playwright');
const outDir = path.join(root, 'video/public/capture');
const diagnosticDir = path.join(root, 'output/playwright/promo');
const baseUrl = process.env.DEMO_BASE_URL ?? 'http://localhost:3000';
const recordedPath = path.join(outDir, 'app-demo.raw.webm');
const demoUserId = process.env.DEMO_USER_ID ?? `portfolio-demo-${Date.now()}`;
const demoPrincipal = Buffer.from(JSON.stringify({
  claims: [
    {typ: 'name', val: 'Portfolio Demo'},
    {typ: 'http://schemas.microsoft.com/identity/claims/objectidentifier', val: demoUserId},
  ],
})).toString('base64');

await mkdir(outDir, {recursive: true});
await mkdir(diagnosticDir, {recursive: true});

const browser = await chromium.launch({headless: true});
const context = await browser.newContext({
  viewport: {width: 1440, height: 900},
  deviceScaleFactor: 1,
  extraHTTPHeaders: {'x-ms-client-principal': demoPrincipal},
  recordVideo: {dir: outDir, size: {width: 1440, height: 900}},
});
const page = await context.newPage();
const startedAt = Date.now();
const absoluteMarkers = {};
let captureFailed = false;
const mark = (name) => {
  absoluteMarkers[name] = (Date.now() - startedAt) / 1000;
  console.log(`${name}: ${absoluteMarkers[name].toFixed(2)}s`);
};

async function failWithScreenshot(error) {
  const target = path.join(diagnosticDir, `capture-failure-${Date.now()}.png`);
  await page.screenshot({path: target, fullPage: true}).catch(() => undefined);
  throw new Error(`${error.message}; diagnostic: ${target}`, {cause: error});
}

try {
  console.log('Opening ready chat…');
  await page.goto(`${baseUrl}/`, {waitUntil: 'networkidle'});
  await page.getByText('Connected', {exact: true}).waitFor({timeout: 30_000});
  const chatInput = page.getByRole('textbox', {name: 'Ask the indexed knowledge base...'});
  await chatInput.waitFor({timeout: 20_000});
  mark('welcome');
  await page.waitForTimeout(2600);

  console.log('Asking a grounded question…');
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'POST' && url.pathname === '/api/copilotkit';
  }, {timeout: 60_000});
  mark('question');
  await chatInput.pressSequentially('How do I clean the Dyson V10 filter?', {delay: 38});
  await page.waitForTimeout(450);
  await chatInput.press('Enter');
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`CopilotKit returned HTTP ${response.status()}`);
  await response.finished();
  // The streamed response is complete once response.finished() resolves. The
  // CopilotKit copy toolbar is intentionally not used as a completion signal:
  // its DOM placement changed between 1.61 and 1.62.
  await page.waitForTimeout(800);
  mark('answer');
  await page.waitForTimeout(4200);

  console.log('Showing persistent discussion history…');
  mark('history');
  await page.getByRole('button', {name: 'New discussion'}).click();
  await page.getByText('Ask a question about the indexed documents.').waitFor({timeout: 15_000});
  await page.waitForTimeout(2800);

  console.log('Opening corpus operations…');
  await page.getByRole('link', {name: 'Corpus'}).click();
  await page.getByRole('button', {name: 'Refresh'}).waitFor({timeout: 20_000});
  mark('corpus');
  await page.waitForTimeout(1200);
  await page.locator('input[type="file"]').setInputFiles(path.join(root, 'sample_docs/ecobee-lite-spec-sheet.pdf'));
  await page.getByText('ecobee-lite-spec-sheet.pdf', {exact: true}).waitFor({timeout: 30_000});
  await page.waitForTimeout(4200);
  mark('end');
} catch (error) {
  captureFailed = true;
  await failWithScreenshot(error);
} finally {
  const video = page.video();
  await context.close();
  await browser.close();
  if (!video) throw new Error('Playwright did not create a video artifact');
  const tempPath = await video.path();
  const targetPath = captureFailed
    ? path.join(diagnosticDir, `app-demo-failed-${Date.now()}.webm`)
    : recordedPath;
  await rm(targetPath, {force: true});
  await rename(tempPath, targetPath);
}

const trimStart = absoluteMarkers.welcome;
const loadingSpeed = 2.5;
const question = absoluteMarkers.question - trimStart;
const answer = question + (absoluteMarkers.answer - absoluteMarkers.question) / loadingSpeed;
const history = answer + absoluteMarkers.history - absoluteMarkers.answer;
const corpus = history + absoluteMarkers.corpus - absoluteMarkers.history;
const manifest = {
  durationSeconds: Math.max(1, corpus + absoluteMarkers.end - absoluteMarkers.corpus),
  trimStartSeconds: trimStart,
  loadingSpeed,
  markers: {welcome: 0, question, answer, history, corpus},
};

// The Remotion composition expects visible time to begin at frame zero. Keep a
// copy of the raw recording for diagnostics and trim away navigation/readiness.
const untrimmedPath = path.join(diagnosticDir, 'app-demo-untrimmed.webm');
await copyFile(recordedPath, untrimmedPath);

const {spawnSync} = await import('node:child_process');
const trimmedPath = path.join(outDir, 'app-demo.trimmed.webm');
const filter = [
  `[0:v]trim=start=${absoluteMarkers.welcome}:end=${absoluteMarkers.question},setpts=PTS-STARTPTS[v0]`,
  `[0:v]trim=start=${absoluteMarkers.question}:end=${absoluteMarkers.answer},setpts=(PTS-STARTPTS)/${loadingSpeed}[v1]`,
  `[0:v]trim=start=${absoluteMarkers.answer}:end=${absoluteMarkers.end},setpts=PTS-STARTPTS[v2]`,
  '[v0][v1][v2]concat=n=3:v=1:a=0[outv]',
].join(';');
const trim = spawnSync('ffmpeg', [
  '-y', '-v', 'error', '-i', recordedPath, '-filter_complex', filter, '-map', '[outv]',
  '-c:v', 'libvpx', '-crf', '8', '-b:v', '4M', '-an', trimmedPath,
], {stdio: 'inherit'});
if (trim.status !== 0) {
  await rm(trimmedPath, {force: true});
  throw new Error(`ffmpeg edit failed; preserved the previous final footage and raw capture at ${recordedPath}`);
}
const finalPath = path.join(outDir, 'app-demo.webm');
await rm(finalPath, {force: true});
await rename(trimmedPath, finalPath);
await rm(recordedPath, {force: true});
await writeFile(path.join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Saved capture to ${finalPath}`);
console.log(`Saved timeline to ${path.join(outDir, 'manifest.json')}`);

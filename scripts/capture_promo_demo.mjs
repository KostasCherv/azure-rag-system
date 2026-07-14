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
const demoHost = new URL(baseUrl).hostname;
const localDemo = ['localhost', '127.0.0.1', '::1'].includes(demoHost);
const demoUserId = process.env.DEMO_USER_ID ?? (localDemo ? 'local-development-user' : `portfolio-demo-${Date.now()}`);
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
  await page.addStyleTag({content: 'nextjs-portal { display: none !important; }'});
  await page.getByText('Connected', {exact: true}).waitFor({timeout: 30_000});
  const chatInput = page.getByRole('textbox', {name: 'Ask the indexed knowledge base...'});
  await chatInput.waitFor({timeout: 20_000});
  await page.getByRole('button', {name: 'New discussion', exact: true}).click();
  const suggestedQuestion = page.getByRole('button', {name: 'Ask about 01-attention-is-all-you-need.pdf'});
  await suggestedQuestion.waitFor({timeout: 20_000});
  mark('welcome');
  await page.waitForTimeout(2200);

  console.log('Choosing a corpus-derived question…');
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'POST' && url.pathname === '/api/copilotkit';
  }, {timeout: 60_000});
  mark('query');
  await suggestedQuestion.click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`CopilotKit returned HTTP ${response.status()}`);
  await response.finished();
  // The streamed response is complete once response.finished() resolves. The
  // CopilotKit copy toolbar is intentionally not used as a completion signal:
  // its DOM placement changed between 1.61 and 1.62.
  await page.waitForTimeout(800);
  mark('answer');
  await page.waitForTimeout(3600);

  console.log('Asking a contextual follow-up…');
  const followupPromise = page.waitForResponse((candidate) => {
    const url = new URL(candidate.url());
    return candidate.request().method() === 'POST' && url.pathname === '/api/copilotkit';
  }, {timeout: 60_000});
  mark('followup');
  await chatInput.pressSequentially('How does multi-head attention improve the model?', {delay: 32});
  await page.waitForTimeout(350);
  await chatInput.press('Enter');
  const followupResponse = await followupPromise;
  if (!followupResponse.ok()) throw new Error(`CopilotKit follow-up returned HTTP ${followupResponse.status()}`);
  await followupResponse.finished();
  await page.waitForTimeout(800);
  mark('followupAnswer');
  await page.waitForTimeout(3200);

  console.log('Opening an inline citation…');
  const citations = page.getByRole('button', {name: 'Go to source 1'});
  await citations.first().waitFor({timeout: 20_000});
  const citationCount = await citations.count();
  if (citationCount < 1) throw new Error('Expected at least one source citation');
  const citation = citations.nth(citationCount - 1);
  await citation.click();
  mark('citation');
  await page.waitForTimeout(2600);
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
const query = absoluteMarkers.query - trimStart;
const answer = query + (absoluteMarkers.answer - absoluteMarkers.query) / loadingSpeed;
const followup = answer + absoluteMarkers.followup - absoluteMarkers.answer;
const followupAnswer = followup + (absoluteMarkers.followupAnswer - absoluteMarkers.followup) / loadingSpeed;
const citation = followupAnswer + absoluteMarkers.citation - absoluteMarkers.followupAnswer;
const manifest = {
  durationSeconds: Math.max(1, citation + absoluteMarkers.end - absoluteMarkers.citation),
  trimStartSeconds: trimStart,
  loadingSpeed,
  markers: {welcome: 0, query, answer, followup, followupAnswer, citation},
};

// The Remotion composition expects visible time to begin at frame zero. Keep a
// copy of the raw recording for diagnostics and trim away navigation/readiness.
const untrimmedPath = path.join(diagnosticDir, 'app-demo-untrimmed.webm');
await copyFile(recordedPath, untrimmedPath);

const {spawnSync} = await import('node:child_process');
const trimmedPath = path.join(outDir, 'app-demo.trimmed.webm');
const filter = [
  `[0:v]trim=start=${absoluteMarkers.welcome}:end=${absoluteMarkers.query},setpts=PTS-STARTPTS[v0]`,
  `[0:v]trim=start=${absoluteMarkers.query}:end=${absoluteMarkers.answer},setpts=(PTS-STARTPTS)/${loadingSpeed}[v1]`,
  `[0:v]trim=start=${absoluteMarkers.answer}:end=${absoluteMarkers.followup},setpts=PTS-STARTPTS[v2]`,
  `[0:v]trim=start=${absoluteMarkers.followup}:end=${absoluteMarkers.followupAnswer},setpts=(PTS-STARTPTS)/${loadingSpeed}[v3]`,
  `[0:v]trim=start=${absoluteMarkers.followupAnswer}:end=${absoluteMarkers.end},setpts=PTS-STARTPTS[v4]`,
  '[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[outv]',
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

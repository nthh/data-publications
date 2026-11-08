#!/usr/bin/env node
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {copyFile, mkdir, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {extname, join, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {chromium} from 'playwright-core';

const ROOT = process.cwd();
const SCRIPT = fileURLToPath(import.meta.url);
const MAX_RANGE = 8 * 1024 * 1024;
const MAX_CASE = 64 * 1024 * 1024;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const fileHash = async path => sha(await readFile(path));
function arg(name) {
  const i = process.argv.indexOf(name);
  if (i < 0 || !process.argv[i + 1]) throw new Error(`Missing ${name}`);
  return process.argv[i + 1];
}
function underRoot(path) {
  const full = resolve(ROOT, path);
  if (!full.startsWith(ROOT + sep)) throw new Error(`Path escapes repository: ${path}`);
  return full;
}
function checkHash(actual, expected, label) {
  if (!/^[a-f0-9]{64}$/.test(expected) || actual !== expected) throw new Error(`${label} SHA-256 mismatch`);
}

const planPath = underRoot(arg('--plan'));
const outDir = underRoot(arg('--out'));
const planBytes = await readFile(planPath);
const plan = JSON.parse(planBytes);
if (plan.schema_version !== 1 || !Array.isArray(plan.cases) || plan.cases.length !== 4) throw new Error('Expected schema_version 1 and exactly four cases');
if (plan.viewport?.width !== 1200 || plan.viewport?.height !== 720 || plan.viewport?.device_scale_factor !== 1) throw new Error('Expected 1200x720 viewport at device scale 1');
if (!Array.isArray(plan.bounds) || plan.bounds.length !== 2) throw new Error('Plan bounds are required');
await mkdir(resolve(outDir, '..'), {recursive: true});
try { await stat(outDir); throw new Error(`Output directory already exists: ${outDir}`); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
await mkdir(outDir, {recursive: true});
const buildDir = join(outDir, '.renderer');
let browser, server;
const report = {
  schema_version: 1,
  plan_sha256: sha(planBytes),
  inputs: {},
  browser_version: null,
  cases: [],
};
let serverOrigin;

try {
  const landPath = underRoot(plan.land.path);
  const landBytes = await readFile(landPath);
  checkHash(sha(landBytes), plan.land.sha256, 'Land input');
  const lockPath = join(ROOT, 'scripts/cloud_viewer/package-lock.json');
  report.inputs = {
    renderer_sha256: await fileHash(SCRIPT),
    client_sha256: await fileHash(join(ROOT, 'scripts/cloud_viewer/src/thumbnail.js')),
    package_lock_sha256: await fileHash(lockPath),
    land_sha256: sha(landBytes),
    plan_sha256: sha(planBytes),
  };
  const cases = [];
  for (const item of plan.cases) {
    if (!/^[a-z0-9-]+$/.test(item.dataset_id) || cases.some(value => value.dataset_id === item.dataset_id) || !item.title || !item.subtitle || !item.attribution || !item.pmtiles?.url || !Number.isSafeInteger(item.pmtiles.size_bytes)) throw new Error('Malformed case entry');
    if (new URL(item.pmtiles.url).origin !== 'https://data.source.coop' || !/^[a-f0-9]{64}$/.test(item.pmtiles.sha256)) throw new Error('Expected a pinned public Source object');
    if (item.source_tile_zoom != null && item.source_tile_zoom !== 3) throw new Error('Explicit preview source tiles must use zoom 3');
    const collectionBytes = await readFile(underRoot(`catalog/${item.dataset_id}/collection.json`));
    const collection = JSON.parse(collectionBytes);
    const object = Object.values(collection.assets).find(asset => asset.href === item.pmtiles.url);
    if (!object || object['file:checksum'] !== '1220' + item.pmtiles.sha256 || object['file:size'] !== item.pmtiles.size_bytes) throw new Error('PMTiles pin differs from the generated catalog asset');
    report.inputs[`${item.dataset_id}_collection_sha256`] = sha(collectionBytes);
    const stylePath = underRoot(item.style_path);
    const styleBytes = await readFile(stylePath);
    checkHash(sha(styleBytes), item.style_sha256, `${item.dataset_id} style`);
    const style = JSON.parse(styleBytes);
    const styleURL = style.sources?.data?.url;
    if (!styleURL || styleURL !== item.pmtiles.url) throw new Error(`${item.dataset_id} style URL differs from the pinned PMTiles URL`);
    if (!Array.isArray(style.layers) || !style.layers.some(layer => layer.source === 'data' && layer['source-layer'])) throw new Error(`${item.dataset_id} style has no data layer`);
    cases.push({...item, style});
    report.inputs[`${item.dataset_id}_style_sha256`] = sha(styleBytes);
  }
  await mkdir(buildDir, {recursive: true});
  const bundle = await build({
    entryPoints: [join(ROOT, 'scripts/cloud_viewer/src/thumbnail.js')],
    bundle: true, format: 'esm', platform: 'browser', target: ['chrome120'],
    outfile: join(buildDir, 'app.js'), write: false, minify: true,
  });
  for (const output of bundle.outputFiles) await writeFile(join(buildDir, output.path.split('/').pop()), output.contents);
  await writeFile(join(buildDir, 'land.geojson'), landBytes);
  await copyFile(join(ROOT, 'scripts/cloud_viewer/node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs'), join(buildDir, 'worker.mjs'));
  report.inputs.worker_sha256 = await fileHash(join(buildDir, 'worker.mjs'));
  report.inputs.bundle_sha256 = await fileHash(join(buildDir, 'app.js'));
  const index = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app.css"><style>
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:720px;overflow:hidden;background:#fff;color:#21343a;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.card{height:100%;display:grid;grid-template-rows:100px 1fr 44px}.heading{padding:24px 34px 10px;border-bottom:1px solid #e1e8e6;display:flex;align-items:flex-start;justify-content:space-between}.titles h1{font-size:27px;line-height:1.1;margin:0 0 7px;font-weight:650;letter-spacing:-.025em}.titles p{font-size:14px;margin:0;color:#63757a}.tag{margin-top:3px;border:1px solid #dce6e4;border-radius:4px;padding:7px 10px;color:#617278;font-size:11px;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}#map{width:100%;height:100%}.footer{padding:0 34px;display:flex;align-items:center;justify-content:space-between;background:#fbfcfa;border-top:1px solid #e1e8e6;color:#63757a;font-size:11px}.credit{max-width:74%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.brand{font-weight:600;color:#64747a;letter-spacing:.05em}</style></head><body><main class="card"><header class="heading"><div class="titles"><h1 id="title"></h1><p id="subtitle"></p></div><div class="tag">Display overview · generalized</div></header><div id="map"></div><footer class="footer"><span id="attribution" class="credit"></span><span class="brand">NTHH · DATA PUBLICATIONS</span></footer></main><script type="module" src="/app.js"></script></body></html>`;
  await writeFile(join(buildDir, 'index.html'), index);

  const mime = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.geojson': 'application/geo+json'};
  server = createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const rel = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!['index.html', 'app.js', 'app.css', 'land.geojson', 'worker.mjs'].includes(rel)) { res.writeHead(404).end(); return; }
    res.writeHead(200, {'content-type': mime[extname(rel)] || 'application/octet-stream', 'cache-control': 'no-store'});
    createReadStream(join(buildDir, rel)).pipe(res);
  });
  await new Promise((resolvePromise, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolvePromise); });
  serverOrigin = `http://127.0.0.1:${server.address().port}`;
  const executablePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  browser = await chromium.launch({headless: true, executablePath, args: ['--no-sandbox']});
  report.browser_version = browser.version();

  for (const item of cases) {
    const entry = {dataset_id: item.dataset_id, status: 'failed', requests: [], total_bytes: 0};
    report.cases.push(entry);
    let page;
    let reservedBytes = 0;
    try {
      const context = await browser.newContext({viewport: {width: 1200, height: 720}, deviceScaleFactor: 1, serviceWorkers: 'block'});
      page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      await page.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin === serverOrigin) { await route.continue(); return; }
        const remote = new URL(item.pmtiles.url);
        if (url.origin !== remote.origin || url.pathname !== remote.pathname || url.search !== remote.search || request.method() !== 'GET') {
          errors.push(`Denied unexpected network request: ${request.url()}`); await route.abort('blockedbyclient'); return;
        }
        const range = request.headers().range || '';
        const match = /^bytes=(\d+)-(\d+)$/.exec(range);
        if (!match) { errors.push(`Denied unbounded range request: ${range || '(missing)'}`); await route.abort('blockedbyclient'); return; }
        const start = Number(match[1]), end = Number(match[2]);
        if (end < start || end - start + 1 > MAX_RANGE || end >= item.pmtiles.size_bytes || reservedBytes + end - start + 1 > MAX_CASE) {
          errors.push(`Range violates size limits: ${range}`); await route.abort('blockedbyclient'); return;
        }
        reservedBytes += end - start + 1;
        const requestEntry = {range: `bytes ${start}-${end}`, requested_bytes: end - start + 1};
        entry.requests.push(requestEntry);
        try {
          const response = await fetch(item.pmtiles.url, {headers: {Range: `bytes=${start}-${end}`}, redirect: 'error', signal: AbortSignal.timeout(60000)});
          const contentRange = response.headers.get('content-range');
          const expectedHeader = `bytes ${start}-${end}/${item.pmtiles.size_bytes}`;
          if (response.status !== 206 || contentRange !== expectedHeader) {
            await response.body?.cancel();
            throw new Error(`Unexpected bounded response: status=${response.status}, Content-Range=${contentRange}`);
          }
          const chunks = []; let length = 0;
          for await (const chunk of response.body) {
            length += chunk.length;
            if (length > end - start + 1) throw new Error('Response body exceeds requested byte range');
            chunks.push(chunk);
          }
          const body = Buffer.concat(chunks);
          if (body.length !== end - start + 1) throw new Error('Truncated byte-range response');
          entry.total_bytes += body.length;
          requestEntry.status = response.status; requestEntry.bytes = body.length; requestEntry.sha256 = sha(body);
          await route.fulfill({status: 206, body, headers: {'content-type': 'application/octet-stream', 'content-range': contentRange, 'accept-ranges': 'bytes', 'access-control-allow-origin': '*', 'cache-control': 'no-store'}});
        } catch (error) {
          requestEntry.error = error.message; errors.push(error.message); await route.abort('failed').catch(() => {});
        }
      });
      // Data is transferred through a compact encoded query, without a writable profile or disk cache.
      await page.goto(`${serverOrigin}/?card=${encodeURIComponent(JSON.stringify(item))}&map=${encodeURIComponent(JSON.stringify(plan))}`, {waitUntil: 'domcontentloaded', timeout: 15000});
      await page.waitForFunction(() => Boolean(window.thumbnailReady), null, {timeout: 10000});
      const result = await page.evaluate(() => Promise.race([
        window.thumbnailReady,
        new Promise((_, reject) => setTimeout(() => reject(new Error('Thumbnail case exceeded 60 seconds')), 60000)),
      ]));
      await page.waitForTimeout(250);
      if (errors.length) throw new Error(errors.join('; '));
      if (!result.feature_count) throw new Error('No rendered features in the actual dataset source');
      await page.screenshot({path: join(outDir, `${item.dataset_id}.png`), fullPage: false, animations: 'disabled'});
      entry.camera = result.camera; entry.source_layer = result.source_layer;
      entry.rendered_features = result.feature_count;
      entry.decoded_tile_count = result.decoded_tile_count;
      entry.decoded_features = result.decoded_features;
      const png = await readFile(join(outDir, `${item.dataset_id}.png`));
      entry.png_sha256 = sha(png); entry.png_size_bytes = png.length;
      entry.status = 'rendered_pending_visual_review';
      await page.context().close();
    } catch (error) {
      entry.error = error.message;
      await page?.context().close().catch(() => {});
    }
  }
} catch (error) {
  report.error = error.message;
} finally {
  await browser?.close().catch(() => {});
  if (server) await new Promise(resolvePromise => server.close(resolvePromise));
  await rm(buildDir, {recursive: true, force: true}).catch(() => {});
  report.status = report.error || report.cases.length !== plan.cases.length || report.cases.some(item => item.status !== 'rendered_pending_visual_review') ? 'failed' : 'rendered_pending_visual_review';
  await writeFile(join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}

if (report.error || report.cases.some(item => item.status !== 'rendered_pending_visual_review')) process.exitCode = 1;

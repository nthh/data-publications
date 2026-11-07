#!/usr/bin/env node
// Browser acceptance for a loopback UI reading only exact planned Source objects.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { verifyRangeResponse, grwlWidthAtZoom, grwlWidthSampleRadiusExpression, grwlWidthExpression } from './src/core.js';
import { DEFAULT_RANGE_LIMIT, validateMetadataPolicy, boundedRange, verifyRangeBody } from './hosted-range-policy.mjs';

function option(name, fallback = null) { const i = process.argv.indexOf('--' + name); return i < 0 ? fallback : process.argv[i + 1]; }
function fail(message) { throw new Error(message); }
function sha(bytes) { return createHash('sha256').update(bytes).digest('hex'); }
function requestedRangeLength(value, objectSize) {
  const match = /^bytes=(\d+)-(\d+)$/.exec(value || '');
  if (!match) return null;
  const start = Number(match[1]), end = Number(match[2]);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || end >= objectSize) return null;
  return end - start + 1;
}
function verifyHeadResponse(status, headers, item, uiOrigin, requestRange = null) {
  const length = Number(headers['content-length']);
  if (!Number.isSafeInteger(length) || length !== item.size_bytes) fail('Object HEAD Content-Length differs from plan');
  if (requestRange === null) {
    if (status !== 200) fail('Ordinary object HEAD response is not 200');
  } else {
    if (requestRange !== 'bytes=0-' || status !== 206) fail('Ranged object HEAD has unsupported request or status');
    verifyRangeResponse(requestRange, headers['content-range'], length, item.size_bytes);
  }
  const mediaType = headers['content-type']?.split(';')[0].trim().toLowerCase();
  if (mediaType !== item.content_type.split(';')[0].trim().toLowerCase()) fail('Object HEAD MIME differs from plan');
  if (!['*', uiOrigin].includes(headers['access-control-allow-origin'])) fail('Object HEAD lacks usable CORS');
  return { status, content_length: length, content_type: headers['content-type'],
    content_range: headers['content-range'] || null,
    cors: headers['access-control-allow-origin'], expose_headers: headers['access-control-expose-headers'] || null,
    accept_ranges: headers['accept-ranges'] || null };
}
if (process.argv.includes('--self-test-head')) {
  const item = { size_bytes: 123, content_type: 'application/vnd.apache.parquet' };
  const headers = { 'content-length': '123', 'content-type': item.content_type,
    'access-control-allow-origin': '*', 'accept-ranges': 'bytes' };
  verifyHeadResponse(200, headers, item, 'http://127.0.0.1:8918');
  verifyHeadResponse(206, { ...headers, 'content-range': 'bytes 0-122/123' }, item, 'http://127.0.0.1:8918', 'bytes=0-');
  for (const [status, changed] of [[404, {}], [200, { 'content-length': '122' }],
    [200, { 'content-type': 'text/html' }], [200, { 'access-control-allow-origin': 'https://elsewhere.example' }]]) {
    try { verifyHeadResponse(status, { ...headers, ...changed }, item, 'http://127.0.0.1:8918'); fail('Unsafe HEAD response passed'); }
    catch (error) { if (error.message === 'Unsafe HEAD response passed') throw error; }
  }
  for (const [status, range, contentRange] of [[206, null, 'bytes 0-122/123'], [200, 'bytes=0-', 'bytes 0-122/123'],
    [206, 'bytes=0-', 'bytes 1-122/123'], [206, 'bytes=1-', 'bytes 1-122/123']]) {
    try { verifyHeadResponse(status, { ...headers, 'content-range': contentRange }, item, 'http://127.0.0.1:8918', range); fail('Unsafe ranged HEAD passed'); }
    catch (error) { if (error.message === 'Unsafe ranged HEAD passed') throw error; }
  }
  process.exit(0);
}
function expectedCases(config, frozen) {
  const datasets = new Map(config.datasets.map(dataset => [dataset.id, dataset]));
  if (config.object_origin !== 'https://data.source.coop' || frozen.object_origin !== config.object_origin) fail('Object origin is not pinned to Source Cooperative');
  if (config.datasets.length !== 5 || config.datasets.reduce((sum, item) => sum + item.layers.length, 0) !== 6 || frozen.cases.length !== 30) fail('Expected five datasets, six layers, and thirty frozen cases');
  const seen = new Set();
  for (const item of frozen.cases) {
    if (!/^[a-z0-9_-]+$/.test(item.id) || seen.has(item.id)) fail('Unsafe or duplicate frozen case ID');
    seen.add(item.id);
    const dataset = datasets.get(item.dataset_id), layer = dataset?.layers.find(candidate => candidate.id === item.layer_id);
    if (!layer || dataset.state !== 'prepared') fail('Frozen case refers to an absent display layer');
    if (item.view) {
      if (dataset.id !== 'grwl-raw' || !['mississippi', 'amazon', 'dateline'].includes(item.view.name) || !Array.isArray(item.view.center) || !Number.isInteger(item.view.zoom)) fail('Invalid frozen width view');
    } else if (!config.regions.some(region => region.id === item.region)) fail('Invalid frozen map region');
  }
  for (const dataset of config.datasets) for (const layer of dataset.layers) {
    const matching = frozen.cases.filter(item => item.dataset_id === dataset.id && item.layer_id === layer.id);
    if (dataset.id === 'grwl-raw') {
      if (matching.length !== 20 || layer.overview?.mode !== 'width_samples' || layer.detail_min_zoom !== 8 || layer.width_field !== 'width_m' || layer.analytic?.lookup_mode !== 'exact_id') fail('Raw GRWL overview or exact-ID plan differs');
      for (let z = 0; z <= 12; z++) if (!matching.some(item => item.view?.name === 'mississippi' && item.view.zoom === z)) fail('Raw GRWL z0–12 coverage is incomplete');
      const actual = matching.map(item => `${item.view?.name}:${item.view?.zoom}`).sort();
      const expected = [...Array.from({length: 13}, (_, z) => `mississippi:${z}`), ...[0, 3, 7, 8].map(z => `amazon:${z}`), ...[3, 7, 8].map(z => `dateline:${z}`)].sort();
      if (JSON.stringify(actual) !== JSON.stringify(expected)) fail('Raw GRWL fixed views differ');
    } else {
      const region = dataset.id === 'river-plastic-inputs' ? 'atlantic_coast' : 'north_america';
      if (matching.length !== 2 || JSON.stringify(matching.map(item => item.region).sort()) !== JSON.stringify(['global', region].sort())) fail('Layer lacks its fixed global/regional views');
    }
  }
  return datasets;
}

const ui = new URL(option('url') || 'http://127.0.0.1:8918/');
if (ui.protocol !== 'http:' || ui.hostname !== '127.0.0.1' || ui.username || ui.password || ui.search || ui.hash || ui.pathname !== '/') fail('--url must be a bare 127.0.0.1 HTTP UI origin');
if (!option('cases') || !option('out')) fail('Usage: hosted-browser-check.mjs --url http://127.0.0.1:8918/ --cases hosted-cases.json --out NEW_DIR [--chrome PATH]');
const frozenBytes = await readFile(resolve(option('cases')));
const frozen = JSON.parse(frozenBytes);
const planBytes = await readFile(resolve(option('plan', 'research/source-publication-20261106/staging-r2/immutable-upload-plan.json')));
if (sha(planBytes) !== frozen.plan_sha256) fail('Frozen cases differ from immutable upload plan bytes');
const actualPlan = JSON.parse(planBytes);
const actualObjects = Object.fromEntries(actualPlan.files.map(item => [item.raw_url_proposed, {
  size_bytes: item.size_bytes, sha256: item.sha256, content_type: item.content_type,
}]));
if (Object.keys(actualObjects).length !== actualPlan.files.length ||
    Object.keys(actualObjects).length !== Object.keys(frozen.objects).length ||
    Object.entries(actualObjects).some(([href, item]) => {
      const pinned = frozen.objects[href];
      return !pinned || pinned.size_bytes !== item.size_bytes || pinned.sha256 !== item.sha256 || pinned.content_type !== item.content_type;
    })) fail('Frozen object inventory differs from immutable upload plan');
const configResponse = await fetch(new URL('/viewer-config.json', ui));
if (!configResponse.ok) fail('Local hosted viewer config could not be read');
const configBytes = Buffer.from(await configResponse.arrayBuffer());
if (sha(configBytes) !== frozen.viewer_config_sha256) fail('UI config differs from frozen case plan');
const config = JSON.parse(configBytes);
const datasets = expectedCases(config, frozen);
const selectedDataset = option('dataset');
if (selectedDataset && !datasets.has(selectedDataset)) fail('Unknown pilot dataset');
const runCases = selectedDataset ? frozen.cases.filter(item => item.dataset_id === selectedDataset) : frozen.cases;
const planned = new Map(Object.entries(frozen.objects));
for (const [href, item] of planned) {
  const parsed = new URL(href);
  if (parsed.origin !== 'https://data.source.coop' || !parsed.pathname.startsWith('/nthh/') || parsed.search || parsed.hash || !/^[0-9a-f]{64}$/.test(item.sha256) || !Number.isSafeInteger(item.size_bytes)) fail('Unsafe planned object URL or identity');
}
const metadataPolicyPath = option('metadata-policy'), metadataPolicySha = option('metadata-policy-sha256');
if (Boolean(metadataPolicyPath) !== Boolean(metadataPolicySha)) fail('Metadata policy requires both path and independently approved SHA-256');
let metadataPolicy = null;
if (metadataPolicyPath) {
  const policyBytes = await readFile(resolve(metadataPolicyPath));
  if (sha(policyBytes) !== metadataPolicySha) fail('Metadata policy bytes differ from approved SHA-256');
  metadataPolicy = validateMetadataPolicy(JSON.parse(policyBytes), {
    planSha: frozen.plan_sha256, controlsSha: sha(frozenBytes), objects: planned,
  });
  if (selectedDataset && selectedDataset !== metadataPolicy.dataset_id) fail('Metadata policy is outside selected dataset');
}
const productByDataset = new Map(frozen.products.map(item => [item.dataset_id, item]));
if (productByDataset.size !== 5) fail('Frozen product inventory differs');
for (const staged of actualPlan.products) {
  const frozenProduct = productByDataset.get(staged.dataset_id);
  if (!frozenProduct || frozenProduct.product_id !== staged.product_id || frozenProduct.release !== staged.release || staged.owner !== 'nthh') fail('Frozen product differs from immutable upload plan');
}
for (const dataset of config.datasets) {
  const product = productByDataset.get(dataset.id);
  if (!product || product.product_id !== dataset.id || !Array.isArray(product.planned_object_prefixes)) fail('Product identity differs');
  const relative = [`${product.product_id}/releases/${product.release}/`];
  if (product.display_release) relative.push(`${product.product_id}/display/${product.display_release}/`);
  const expected = relative.map(prefix => `https://data.source.coop/nthh/${prefix}`);
  if (JSON.stringify(product.planned_object_prefixes) !== JSON.stringify(relative) ||
      JSON.stringify(product.planned_object_url_prefixes) !== JSON.stringify(expected)) fail('Product URL prefixes differ');
  for (const layer of dataset.layers) for (const asset of [layer, layer.analytic].filter(Boolean)) {
    const href = config.object_origin + asset.object_path, item = planned.get(href);
    if (!item || item.sha256 !== asset.sha256 || item.size_bytes !== asset.size_bytes || !expected.some(prefix => href.startsWith(prefix))) fail('Layer/source object is outside exact product plan');
  }
}

const out = resolve(option('out'));
await mkdir(out, { recursive: false });
const buildResponse = await fetch(new URL('/build.json', ui));
if (!buildResponse.ok) fail('Local viewer build pin is missing');
const buildBytes = Buffer.from(await buildResponse.arrayBuffer());
const build = JSON.parse(buildBytes);
const appResponse = await fetch(new URL('/app.js', ui));
if (!appResponse.ok || sha(Buffer.from(await appResponse.arrayBuffer())) !== build.files?.['app.js']?.sha256) fail('Served app.js differs from viewer build pin');
const report = { schema_version: 1, status: 'running', checked_at: new Date().toISOString(),
  scope: selectedDataset ? `Single-dataset hosted pilot: ${selectedDataset}; local UI only` : 'Thirty frozen hosted Source Cooperative browser views; local UI only',
  selected_dataset_id: selectedDataset || null, expected_case_count: runCases.length, plan_sha256: frozen.plan_sha256,
  browser_cases_sha256: sha(frozenBytes),
  viewer_config_sha256: frozen.viewer_config_sha256, viewer_build_sha256: sha(buildBytes),
  origin: config.object_origin, ui_origin: ui.origin, metadata_range_policy_sha256: metadataPolicySha,
  transfer_ceiling_bytes_per_case: 128 * 1024 * 1024,
  transfer_ceiling_bytes_total: 1024 * 1024 * 1024, cases: [], datasets: [] };
let totalBytes = 0;
const { chromium } = await import('playwright-core');
const browser = await chromium.launch({ executablePath: option('chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'), headless: true,
  args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--disable-background-networking', '--no-first-run'] });
try {
  for (const frozenCase of runCases) {
    const dataset = datasets.get(frozenCase.dataset_id), layer = dataset.layers.find(item => item.id === frozenCase.layer_id);
    const product = productByDataset.get(dataset.id), prefixes = product.planned_object_url_prefixes;
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const page = await context.newPage(), pending = [], errors = [], requests = [], heads = [], options = [], blockedRequests = [];
    let reserved = 0, transferred = 0, footerRequests = 0, footerResponses = 0;
    await context.route('**/*', route => {
      let request, href, parsed;
      try {
        request = route.request(); href = request.url(); parsed = new URL(href);
        if (parsed.origin === ui.origin) return route.continue();
        const item = planned.get(href);
        if (!item || !prefixes.some(prefix => href.startsWith(prefix))) fail('Off-plan or cross-product network request: ' + href);
        if (request.method() === 'OPTIONS') return route.continue();
        if (request.method() === 'HEAD') return route.continue();
        if (request.method() !== 'GET') fail('Unexpected object method: ' + request.method());
        const length = boundedRange(href, request.headers()['range'], item, metadataPolicy);
        if (length > DEFAULT_RANGE_LIMIT) {
          if (frozenCase.id !== metadataPolicy.case_id || footerRequests >= metadataPolicy.max_requests_per_case) fail('Metadata footer request is outside the frozen case/count');
          footerRequests += 1;
        }
        if (reserved + length > report.transfer_ceiling_bytes_per_case || totalBytes + reserved + length > report.transfer_ceiling_bytes_total) fail('Pre-request transfer ceiling exceeded');
        reserved += length;
        return route.continue();
      } catch (error) {
        errors.push(error.message);
        if (request && parsed?.origin === 'https://data.source.coop' && parsed.pathname.startsWith('/nthh/') && !parsed.search && !parsed.hash) {
          const item = planned.get(href), range = request.headers()['range'] || null;
          blockedRequests.push({ url: `${parsed.origin}${parsed.pathname}`, method: request.method(), range,
            requested_bytes: item ? requestedRangeLength(range, item.size_bytes) : null,
            reason: error.message, blocked_before_network: true });
        }
        return route.abort();
      }
    });
    page.on('pageerror', error => errors.push(error.message));
    page.on('requestfailed', request => errors.push(`Failed request ${request.method()} ${request.url()}: ${request.failure()?.errorText || 'unknown'}`));
    page.on('request', request => {
      if (request.method() === 'OPTIONS' && planned.has(request.url())) options.push({ url: request.url(), request_headers: request.headers(), status: null });
    });
    page.on('response', response => {
      const href = response.url(), item = planned.get(href);
      if (response.status() >= 400) errors.push(`HTTP ${response.status()} ${href}`);
      if (item && response.request().method() === 'OPTIONS') {
        pending.push((async () => {
          const record = options.find(value => value.url === href && value.status === null);
          if (!record) { errors.push('Unmatched object OPTIONS response'); return; }
          record.status = response.status(); record.response_headers = await response.allHeaders();
          const allow = record.response_headers['access-control-allow-origin'];
          const methods = (record.response_headers['access-control-allow-methods'] || '').toUpperCase();
          const requestedMethod = (record.request_headers['access-control-request-method'] || 'GET').toUpperCase();
          const requested = (record.request_headers['access-control-request-headers'] || '').toLowerCase().split(',').map(value => value.trim()).filter(Boolean);
          const allowed = (record.response_headers['access-control-allow-headers'] || '').toLowerCase().split(',').map(value => value.trim());
          if (![200, 204].includes(record.status) || !['*', ui.origin].includes(allow) || !methods.includes(requestedMethod) ||
              requested.some(value => !allowed.includes('*') && !allowed.includes(value))) errors.push('Object OPTIONS preflight does not authorize requested GET headers');
        })());
      }
      if (item && response.request().method() === 'HEAD') {
        pending.push((async () => {
          const entry = { url: href, method: 'HEAD', request_range: response.request().headers()['range'] || null,
            planned_sha256: item.sha256 };
          try {
            const headers = await response.allHeaders();
            Object.assign(entry, verifyHeadResponse(response.status(), headers, item, ui.origin, entry.request_range));
            const failure = await response.finished();
            if (failure) fail('Object HEAD did not complete: ' + failure);
            entry.status_check = 'passed';
          } catch (error) { entry.status_check = 'failed'; entry.failure = error.message; errors.push(error.message); }
          heads.push(entry);
        })());
      }
      if (!item || response.request().method() !== 'GET') return;
      pending.push((async () => {
        const headers = await response.allHeaders(), requestRange = response.request().headers()['range'];
        const entry = { url: href, status: response.status(), range: requestRange || null,
          content_range: headers['content-range'] || null, content_length: Number(headers['content-length']),
          content_type: headers['content-type'] || null, cors: headers['access-control-allow-origin'] || null,
          expose_headers: headers['access-control-expose-headers'] || null, planned_sha256: item.sha256 };
        try {
          const body = await response.body(); entry.body_bytes = body.length;
          entry.body_sha256 = sha(body); transferred += body.length; totalBytes += body.length;
          if (response.status() !== 206) fail('Object response is not 206');
          if (entry.cors !== '*' && entry.cors !== ui.origin) fail('Object response lacks usable CORS');
          if (!['*', 'content-range'].some(value => entry.expose_headers?.toLowerCase().split(',').map(part => part.trim()).includes(value))) fail('Object CORS does not expose Content-Range');
          if (headers['accept-ranges']?.toLowerCase() !== 'bytes') fail('Object response does not advertise byte ranges');
          if (!entry.content_type?.toLowerCase().startsWith(item.content_type.split(';')[0].toLowerCase())) fail('Object MIME differs from plan');
          if (entry.content_length !== body.length) fail('Content-Length differs from received body');
          verifyRangeResponse(requestRange, entry.content_range, body.length, item.size_bytes);
          const metadataException = verifyRangeBody(href, requestRange, item, body, metadataPolicy);
          if (metadataException) {
            if (frozenCase.id !== metadataPolicy.case_id || footerResponses >= metadataPolicy.max_requests_per_case) fail('Metadata footer response is outside the frozen case/count');
            footerResponses += 1;
            entry.metadata_range_exception = metadataException;
          }
          entry.status_check = 'passed';
        } catch (error) { entry.status_check = 'failed'; entry.failure = error.message; errors.push(error.message); }
        requests.push(entry);
      })());
    });
    const target = new URL(ui); target.searchParams.set('dataset', dataset.id); target.searchParams.set('layer', layer.id);
    if (frozenCase.region) target.searchParams.set('region', frozenCase.region);
    const entry = { id: frozenCase.id, dataset_id: dataset.id, product_id: product.product_id,
      layer_id: layer.id, region: frozenCase.region || null, view: frozenCase.view || null,
      display_object_url: config.object_origin + layer.object_path, display_sha256: layer.sha256,
      analytic_object_url: layer.analytic ? config.object_origin + layer.analytic.object_path : null,
      analytic_sha256: layer.analytic?.sha256 || null, status: 'running' };
    try {
      await page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForFunction(() => window.viewer && window.viewer.getState().phase !== 'starting', {}, { timeout: 30000 });
      if (frozenCase.view) {
        await page.evaluate(view => window.viewer.setView(view.center, view.zoom), frozenCase.view);
        await page.evaluate(() => window.viewer.waitForStableMapRender());
        const zoom = await page.evaluate(() => window.viewer.getZoom());
        const center = await page.evaluate(() => window.viewer.getCenter());
        if (Math.abs(zoom - frozenCase.view.zoom) > 1e-6 || Math.abs(center[1] - frozenCase.view.center[1]) > 1e-6 ||
            Math.abs(((center[0] - frozenCase.view.center[0] + 540) % 360) - 180) > 1e-6) fail('Fixed view center or zoom shifted');
      }
      await page.waitForFunction(() => { const state = window.viewer?.getState(); return state?.phase === 'error' || state?.phase === 'ready'; }, {}, { timeout: 60000 });
      const state = await page.evaluate(() => window.viewer.getState());
      entry.feature_count = state.feature_count;
      if (state.phase !== 'ready' || state.feature_count < 1) fail(state.error || 'No visible feature in fixed view');
      if (frozenCase.view) {
        const detail = frozenCase.view.zoom >= layer.detail_min_zoom;
        const expectedSource = detail ? layer.source_layer : layer.overview.source_layer;
        entry.rendered_source_layers = await page.evaluate(() => window.viewer.getRenderedLayerNames());
        entry.active_style_layers = await page.evaluate(() => window.viewer.getActiveStyleLayerNames());
        if (!entry.rendered_source_layers.includes(expectedSource)) fail('Expected raw GRWL source layer is absent');
        if (!entry.active_style_layers.includes(detail ? 'release-lines' : 'release-width-samples')) fail('Wrong raw GRWL width style layer');
        if (!(await page.locator('#grwl-width-legend').isVisible()) || await page.locator('.width-legend-item').count() !== 3) fail('Raw width legend is missing');
        if (!(await page.locator('#display-note').innerText()).includes('Selected observations; widest measured width per screen-scale cell')) fail('Selected-observation description is missing');
        if (detail) {
          const paint = await page.evaluate(() => window.viewer.getActiveLineWidthExpression());
          if (JSON.stringify(paint) !== JSON.stringify(grwlWidthExpression('width_m'))) fail('Detailed line paint differs from source-width scale');
        }
        if (!detail) {
          const sample = await page.evaluate(() => window.viewer.getFirstRenderedWidthSample());
          if (!sample || !Number.isSafeInteger(sample.featureID) || sample.sourceLayer !== layer.overview.source_layer) fail('No source-ID width overview sample');
          entry.width_sample = { feature_id: sample.featureID, width_m: sample.properties.width_m, width_valid: sample.properties.width_valid };
          const paint = await page.evaluate(() => window.viewer.getWidthSamplePaint());
          if (JSON.stringify(paint?.radius) !== JSON.stringify(grwlWidthSampleRadiusExpression('width_m')) ||
              !JSON.stringify(paint).includes('width_valid')) fail('Raw width overview paint differs from source-width scale');
          entry.expected_diameter_px = grwlWidthAtZoom(sample.properties.width_m === 1 ? 0 : sample.properties.width_m, frozenCase.view.zoom);
          if (!Number.isFinite(entry.expected_diameter_px)) fail('Width sample diameter is invalid');
          if (frozenCase.view.name === 'mississippi' && frozenCase.view.zoom === 7) {
            await page.mouse.click(sample.pagePoint.x, sample.pagePoint.y);
            await page.waitForFunction(id => window.viewer.getState().selected?.id === id, sample.featureID, { timeout: 10000 });
          }
        }
      }
      if (!(frozenCase.view?.name === 'mississippi' && frozenCase.view.zoom === 7)) await page.evaluate(() => window.viewer.inspectFirstFeature());
      await page.locator('#feature-panel').waitFor({ state: 'visible' });
      entry.tile_property_count = await page.locator('#properties dd').count();
      if (!entry.tile_property_count) fail('Visible feature has no inspectable properties');
      entry.viewer_traffic = await page.evaluate(() => {
        const state = window.viewer.getState();
        return { bytes: state.bytes, bytes_unavailable: state.bytes_unavailable, ranges: state.ranges, requests: state.requests,
          remote_resource_timing: performance.getEntriesByType('resource').filter(item => item.name.startsWith('https://data.source.coop/')).map(item => ({
            responseStatus: item.responseStatus, transferSize: item.transferSize, encodedBodySize: item.encodedBodySize,
          })) };
      });
      const requireAttributes = !frozenCase.view && frozenCase.region !== 'global' && !!layer.analytic || frozenCase.view?.name === 'mississippi' && frozenCase.view.zoom === 7;
      if (requireAttributes) {
        await page.evaluate(() => window.viewer.loadAllAttributes());
        await page.waitForFunction(() => { const note = document.querySelector('#feature-note')?.textContent || ''; return note.startsWith('All source attributes') || note.startsWith('Could not load attributes'); }, {}, { timeout: 60000 });
        entry.attribute_note = await page.locator('#feature-note').innerText();
        entry.source_attribute_count = await page.locator('#properties dd').count();
        const expected = layer.analytic.fields.filter(field => field !== layer.analytic.geometry_column && field !== 'bbox').length;
        if (!entry.attribute_note.startsWith('All source attributes') || entry.source_attribute_count !== expected) fail('Source attribute lookup did not return all declared fields');
        if (frozenCase.view) {
          const sourceId = Number(await page.evaluate(() => [...document.querySelectorAll('#properties dt')].find(node => node.textContent === 'feature_id')?.nextElementSibling?.textContent));
          entry.analytic_feature_id = sourceId;
          if (sourceId !== entry.width_sample.feature_id) fail('Raw overview ID differs from exact analytic feature ID');
        }
      }
      const screenshot = join(out, frozenCase.id + '.png');
      await page.screenshot({ path: screenshot, fullPage: true });
      entry.screenshot = screenshot;
      await Promise.all(pending);
      if (!requests.length || requests.some(item => item.status_check !== 'passed') || heads.some(item => item.status_check !== 'passed') || errors.length) fail('Hosted range/CORS/browser checks failed');
      if (requireAttributes && !requests.some(item => item.url === entry.analytic_object_url)) fail('Attribute lookup did not read the planned analytic source');
      if (transferred > report.transfer_ceiling_bytes_per_case || totalBytes > report.transfer_ceiling_bytes_total) fail('Transfer ceiling exceeded');
      if (metadataPolicy && frozenCase.id === metadataPolicy.case_id && (footerRequests !== metadataPolicy.max_requests_per_case || footerResponses !== metadataPolicy.max_requests_per_case)) fail('Frozen metadata footer request/response was not exercised exactly once');
      entry.transferred_bytes = transferred; entry.requests = requests; entry.heads = heads; entry.options = options;
      entry.blocked_requests = blockedRequests; entry.status = 'passed';
    } catch (error) {
      entry.status = 'failed'; entry.failure = error.message; entry.transferred_bytes = transferred;
      entry.requests = requests; entry.heads = heads; entry.options = options; entry.blocked_requests = blockedRequests; entry.errors = errors;
      try { entry.screenshot = join(out, frozenCase.id + '-failure.png'); await page.screenshot({ path: entry.screenshot, fullPage: true }); } catch {}
    }
    await Promise.allSettled(pending);
    report.cases.push(entry);
    await writeFile(join(out, 'hosted-browser-evidence.json'), JSON.stringify(report, null, 2) + '\n');
    await context.close();
    console.log(JSON.stringify({ case: entry.id, status: entry.status, features: entry.feature_count, bytes: entry.transferred_bytes, failure: entry.failure }));
  }
  report.checked_at = new Date().toISOString(); report.browser_version = browser.version();
  for (const product of frozen.products) {
    const cases = report.cases.filter(item => item.dataset_id === product.dataset_id);
    const expected = frozen.cases.filter(item => item.dataset_id === product.dataset_id).map(item => item.id);
    const status = !cases.length && selectedDataset ? 'not_run' :
      cases.length === expected.length && expected.every(id => cases.some(item => item.id === id && item.status === 'passed')) ? 'passed' : 'failed';
    report.datasets.push({ ...product, status,
      checked_at: report.checked_at, screenshots: cases.map(item => item.screenshot).filter(Boolean),
      case_ids: cases.map(item => item.id), plan_sha256: frozen.plan_sha256,
      browser_cases_sha256: report.browser_cases_sha256,
      viewer_config_sha256: frozen.viewer_config_sha256, viewer_build_sha256: report.viewer_build_sha256,
      tested_object_urls: [...new Set(cases.flatMap(item => (item.requests || []).map(request => request.url)))] });
  }
  report.status = selectedDataset ? (report.datasets.find(item => item.dataset_id === selectedDataset)?.status === 'passed' ? 'partial' : 'failed') :
    report.datasets.every(item => item.status === 'passed') ? 'passed' : 'failed';
  report.total_transferred_bytes = totalBytes;
  await writeFile(join(out, 'hosted-browser-evidence.json'), JSON.stringify(report, null, 2) + '\n');
} finally { await browser.close(); }
if (!['passed', 'partial'].includes(report.status)) process.exitCode = 1;

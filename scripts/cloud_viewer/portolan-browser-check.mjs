#!/usr/bin/env node
/**
 * Portolan Browser integration check for the five-collection aggregate.
 *
 * Preflight fulfills only exact GitHub Pages files listed in a staged publish
 * plan. Every Source Cooperative object remains a live request. Live mode does
 * not install a route for the Pages origin at all.
 *
 * This script does not upload, publish, edit GitHub, or register a catalog.
 */
import { createHash } from 'node:crypto';
import { readFile, lstat, readdir, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createPortolanFooterGuard, FOOTER_PREFIX_LIMIT, validatePortolanFooterPolicy } from './portolan-footer-policy.mjs';
import { PortolanFooterCdpCapture, CAPTURE_RESOURCE_BYTES, CAPTURE_TOTAL_BYTES } from './portolan-cdp-capture.mjs';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const ROOT = path.resolve(HERE, '../..');
const CRITERIA_PATH = path.join(ROOT, 'research/source-publication-20261106/portolan-browser-criteria-r1.json');
const HEAD_RENDER_CRITERIA_PATH = path.join(ROOT, 'research/source-publication-20261106/pages/three-collections-r1/head-and-render-followup-criteria-r1.json');
const NAVIGATION_FOLLOWUP_CRITERIA_PATH = path.join(ROOT, 'research/source-publication-20261106/pages/four-collections-r1/navigation-followup-criteria-r1.json');
const NAVIGATION_TRACE_CRITERIA_PATH = path.join(ROOT, 'research/source-publication-20261107/pages/five-collections-r2/navigation-trace-criteria-r1.json');
const FROZEN_FOOTER_PROOF_PATH = path.join(ROOT, 'research/source-publication-20261107/grwl-footer-boundary-r1/local-footer-proof.json');
const RIVER_RENDER_DIAGNOSTIC_PATH = path.join(ROOT, 'research/source-publication-20261106/pages/river-render-diagnostic-r1.json');
const RIVER_RENDERER_INSPECTION_PATH = path.join(ROOT, 'research/source-publication-20261106/pages/river-renderer-inspection-r3.json');
const DEFAULT_SOURCE_PLAN = path.join(ROOT, 'research/source-publication-20261106/staging-r2/immutable-upload-plan.json');
const DEFAULT_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PAGE_BASE = 'https://nthh.github.io/data-publications/';
const BROWSER_ORIGIN = 'https://browser.portolan-sdi.org';
const SOURCE_ORIGIN = 'https://data.source.coop';
const DATA_EXTENSIONS = new Set(['.parquet', '.pmtiles', '.tif', '.tiff', '.zarr', '.gpkg']);
const SMALL_METADATA_EXTENSIONS = new Set(['.json', '.md', '.txt', '.png', '.svg']);
const PAGE_FILE_LIMIT = 2 * 1024 * 1024;
const PAGE_TOTAL_LIMIT = 16 * 1024 * 1024;
const REQUIRED_COLLECTIONS = [
  'river-plastic-inputs', 'hydrolakes', 'lakeatlas', 'free-flowing-rivers', 'grwl-raw',
];

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function die(message) {
  throw new Error(message);
}

function externalCollectionBrowserUrl(browserCriteria, collectionUrl) {
  const target = new URL(collectionUrl);
  const placeholder = '{catalog_host_path}';
  if (typeof browserCriteria?.external_catalog_route !== 'string' ||
      browserCriteria.external_catalog_route.split(placeholder).length !== 2 ||
      typeof browserCriteria.origin !== 'string') {
    die('External Browser route template is invalid');
  }
  const route = browserCriteria.external_catalog_route.replace(placeholder, `${target.host}${target.pathname}`);
  return `${browserCriteria.origin.replace(/\/+$/, '')}/${route.replace(/^\/+/, '')}`;
}

function validateCollectionChildLink(link, expectedTitle, expectedUrl) {
  if (!link || link.tag_name !== 'a' || link.visible !== true || link.title_text !== expectedTitle ||
      link.text_content !== expectedTitle || link.href !== expectedUrl) {
    die(`Exact child link does not target the expected collection route: ${JSON.stringify(link)}`);
  }
  return link;
}

function validateNavigationFollowupCriteria(value) {
  if (value?.schema_version !== 1 || value.kind !== 'official_browser_collection_navigation_followup' ||
      value.frozen_before_viewer_run !== true ||
      value.prior_attempt_report !== '.local/portolan-four-verified-preflight-r7/portolan-browser-report.json' ||
      value.prior_attempt_sha256 !== 'a88e7c8f7f6b5b699974e83fff253588b17f7ae510cf76559ee18dc6a54f82a9' ||
      value.scope?.mode !== 'normal_browser_keyboard_navigation_diagnostic' ||
      value.scope?.no_direct_router_or_vue_access !== true ||
      value.navigation_contract?.root_child_selector !== '.catalog-card .stac-link with exactly one descendant .title whose textContent matches the collection title' ||
      value.navigation_contract?.activation !== 'Send Enter to the focused link; do not use a mouse click or manipulate application routing state.' ||
      value.unchanged_gates?.length !== 4 ||
      !value.unchanged_gates.includes('Keep exact per-product Source object allowlists and reject cross-product Source requests.')) {
    die('Navigation follow-up criteria do not match the frozen bounded protocol');
  }
  return value;
}

async function installNavigationTrace(page) {
  await page.evaluate(() => {
    const records = [];
    let truncated = 0;
    const add = record => {
      const entry = { elapsed_ms: Math.round(performance.now()), ...record };
      if (records.length < 50) records.push(entry);
      else {
        truncated += 1;
        if (record.kind === 'catalog_card_mutation') return;
        const mutationIndex = records.findIndex(item => item.kind === 'catalog_card_mutation');
        if (mutationIndex >= 0) records.splice(mutationIndex, 1);
        else records.shift();
        records.push(entry);
      }
    };
    const anchorInfo = element => {
      const anchor = element instanceof Element ? element.closest('a.stac-link') : null;
      return anchor ? { title: anchor.querySelector('.title')?.textContent?.trim() || null,
        raw_href: anchor.getAttribute('href'), href: anchor.href, connected: anchor.isConnected } : null;
    };
    const cards = () => [...document.querySelectorAll('.catalog-card a.stac-link')].slice(0, 10)
      .map(anchor => anchorInfo(anchor));
    for (const type of ['keydown', 'keyup', 'click']) {
      for (const capture of [true, false]) document.addEventListener(type, event => {
        if (type !== 'click' && event.key !== 'Enter') return;
        if (type === 'click' && !anchorInfo(event.target)) return;
        add({ kind: 'dom_event', type, phase: capture ? 'capture' : 'bubble',
          event_phase: event.eventPhase, trusted: event.isTrusted, default_prevented: event.defaultPrevented,
          target_tag: event.target instanceof Element ? event.target.tagName.toLowerCase() : null,
          target_anchor: anchorInfo(event.target), active_anchor: anchorInfo(document.activeElement),
          current_url: location.href });
      }, capture);
    }
    window.addEventListener('hashchange', event => add({ kind: 'hashchange', old_url: event.oldURL,
      new_url: event.newURL, current_url: location.href, active_anchor: anchorInfo(document.activeElement) }));
    const observer = new MutationObserver(mutations => {
      const relevant = mutations.filter(mutation => {
        const element = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
        if (element?.closest('.catalog-card') || element?.querySelector?.('.catalog-card')) return true;
        return [...mutation.addedNodes, ...mutation.removedNodes].some(node =>
          node instanceof Element && (node.matches('.catalog-card') || node.querySelector('.catalog-card')));
      });
      if (relevant.length) add({ kind: 'catalog_card_mutation', count: relevant.length,
        types: [...new Set(relevant.map(mutation => mutation.type))].sort(),
        anchors: cards(), active_anchor: anchorInfo(document.activeElement), current_url: location.href });
    });
    observer.observe(document.querySelector('main') || document.body,
      { subtree: true, childList: true, attributes: true, attributeFilter: ['href'], characterData: true });
    window.__portolanNavigationTrace = { snapshot: () => ({ records: [...records], truncated_records: truncated,
      active_anchor: anchorInfo(document.activeElement), anchors: cards(), current_url: location.href }) };
  });
}

async function readNavigationTrace(page, anchorHandle = null) {
  const trace = await page.evaluate(() => window.__portolanNavigationTrace?.snapshot() || null).catch(error =>
    ({ read_error: error.message }));
  const anchor = anchorHandle ? await anchorHandle.evaluate(element => ({ connected: element.isConnected,
    active: document.activeElement === element,
    title: element.querySelector('.title')?.textContent?.trim() || null,
    raw_href: element.getAttribute('href'), href: element.href })).catch(error => ({ read_error: error.message })) : null;
  return { trace, validated_anchor: anchor };
}

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--self-test') {
      result.selfTest = true;
      continue;
    }
    if (arg === '--diagnose-render') {
      result.diagnoseRender = true;
      continue;
    }
    if (arg === '--inspect-renderer') {
      result.inspectRenderer = true;
      continue;
    }
    if (!arg.startsWith('--') || i + 1 >= argv.length) die(`Unexpected argument: ${arg}`);
    const key = arg.slice(2);
    if (!['mode', 'plan', 'catalog-dir', 'expected-pages-plan-sha256', 'source-plan', 'out', 'chrome', 'dataset',
      'metadata-policy', 'metadata-policy-sha256'].includes(key)) {
      die(`Unknown option: ${arg}`);
    }
    if (key === 'dataset') {
      result.datasets ||= [];
      result.datasets.push(argv[++i]);
    } else {
      if (result[key] !== undefined) die(`Repeated option: ${arg}`);
      result[key] = argv[++i];
    }
  }
  return result;
}

function parseSingleByteRange(value, fileSize) {
  if (typeof value !== 'string') die('GET requires a single byte Range header');
  const match = /^bytes=(\d+)-(\d+)$/.exec(value.trim());
  if (!match) die(`Range must be one explicit bytes=start-end range: ${value}`);
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end < start || end >= fileSize) {
    die(`Range is outside the planned object size: ${value}`);
  }
  return { start, end, length: end - start + 1 };
}

function parseContentRange(value) {
  const match = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(value || '');
  if (!match) die(`Invalid Content-Range: ${value || '(missing)'}`);
  return { start: Number(match[1]), end: Number(match[2]), total: Number(match[3]) };
}

function isExactProductObject(url, objectByUrl, productPrefix) {
  return objectByUrl.has(url) && typeof productPrefix === 'string' && url.startsWith(productPrefix);
}

function sourceDatasetId(entry, productIds) {
  const key = entry.object_key;
  if (typeof key !== 'string' || key.startsWith('/') || key.includes('\\') || key.split('/').some(part => !part || part === '.' || part === '..')) {
    die(`Source plan object has an unsafe object_key: ${key}`);
  }
  const keyDatasetId = key.split('/')[0];
  if (!productIds.has(keyDatasetId)) die(`Source object_key does not begin with a planned product id: ${key}`);
  const source = entry.source || {};
  if (source.kind === 'repository') {
    if (source.dataset_id && source.dataset_id !== keyDatasetId) die(`Repository supplement dataset_id differs from object_key: ${key}`);
    const repositoryPath = source.path;
    if (typeof repositoryPath !== 'string' || repositoryPath.startsWith('/') || repositoryPath.includes('\\') ||
        repositoryPath.split('/').some(part => !part || part === '.' || part === '..') ||
        !repositoryPath.startsWith(`datasets/${keyDatasetId}/`) || repositoryPath.length <= `datasets/${keyDatasetId}/`.length) {
      die(`Repository supplement path does not bind to object_key product ${keyDatasetId}: ${repositoryPath}`);
    }
    if (entry.kind !== 'supplement') die(`Repository source must be classified as a supplement: ${key}`);
    return keyDatasetId;
  }
  if (source.dataset_id !== keyDatasetId) die(`Source dataset_id differs from object_key product: ${key}`);
  return keyDatasetId;
}

function isDataObject(object) {
  const extension = path.posix.extname(new URL(object.url).pathname).toLowerCase();
  const type = (object.content_type || '').split(';')[0].toLowerCase();
  return DATA_EXTENSIONS.has(extension) || type.includes('parquet') || type.includes('pmtiles') ||
    type.startsWith('image/tiff') || type.includes('geopackage');
}

function stylePmtilesUrls(styleJson) {
  const urls = new Set();
  for (const source of Object.values(styleJson?.sources || {})) {
    const candidates = [source?.url, ...(Array.isArray(source?.tiles) ? source.tiles : [])].filter(v => typeof v === 'string');
    for (const candidate of candidates) {
      const normalized = candidate.replace(/^pmtiles:\/\//i, '');
      try {
        const url = new URL(normalized);
        if (url.protocol === 'https:' && url.pathname.toLowerCase().endsWith('.pmtiles')) urls.add(url.href);
      } catch { /* Non-absolute or templated vector sources are not Source PMTiles references. */ }
    }
  }
  return [...urls].sort();
}

function inspectMapRendererState(input) {
  const root = document.body;
  const rootVNode = root?._vnode || null;
  const seenVNodes = new WeakSet();
  const seenComponents = new WeakSet();
  const queue = rootVNode ? [{ kind: 'vnode', value: rootVNode, depth: 0 }] : [];
  const rootPropertyNames = root ? Object.getOwnPropertyNames(root).slice(0, input.max_property_names) : [];
  const rootVNodePropertyNames = rootVNode ? Object.getOwnPropertyNames(rootVNode).slice(0, input.max_property_names) : [];
  let vnodeCount = 0;
  let componentCount = 0;
  let deepestNode = 0;
  let traversalTruncated = !rootVNode;
  let map = null;
  let componentType = null;
  const appendVNode = (value, depth) => {
    if (value && typeof value === 'object' && !seenVNodes.has(value)) {
      if (queue.length >= input.max_queued_nodes) traversalTruncated = true;
      else queue.push({ kind: 'vnode', value, depth });
    }
  };
  const appendComponent = (value, depth) => {
    if (value && typeof value === 'object' && !seenComponents.has(value)) {
      if (queue.length >= input.max_queued_nodes) traversalTruncated = true;
      else queue.push({ kind: 'component', value, depth });
    }
  };
  const appendChildren = (children, depth) => {
    if (!Array.isArray(children)) return;
    for (const child of children) {
      if (queue.length >= input.max_queued_nodes) {
        traversalTruncated = true;
        break;
      }
      appendVNode(child, depth);
    }
  };
  for (let cursor = 0; cursor < queue.length && !map; cursor++) {
    const entry = queue[cursor];
    deepestNode = Math.max(deepestNode, entry.depth);
    if (entry.depth > input.max_depth || vnodeCount >= input.max_vnodes || componentCount >= input.max_components) {
      traversalTruncated = true;
      break;
    }
    if (entry.kind === 'vnode') {
      const vnode = entry.value;
      if (seenVNodes.has(vnode)) continue;
      seenVNodes.add(vnode);
      vnodeCount += 1;
      appendComponent(vnode.component, entry.depth + 1);
      appendChildren(vnode.children, entry.depth + 1);
      appendChildren(vnode.dynamicChildren, entry.depth + 1);
      appendVNode(vnode.ssContent, entry.depth + 1);
      appendVNode(vnode.ssFallback, entry.depth + 1);
      appendVNode(vnode.suspense?.activeBranch, entry.depth + 1);
      appendVNode(vnode.suspense?.pendingBranch, entry.depth + 1);
      continue;
    }
    const component = entry.value;
    if (seenComponents.has(component)) continue;
    seenComponents.add(component);
    componentCount += 1;
    const typeName = component.type?.name || component.type?.__name || null;
    if (typeName === 'MapView') {
      let componentMap;
      try { componentMap = component.proxy?.map; } catch { /* read-only probe of the pinned MapView map property */ }
      if (componentMap && typeof componentMap.getStyle === 'function' && typeof componentMap.querySourceFeatures === 'function') {
        map = componentMap;
        componentType = typeName;
      }
    }
    appendVNode(component.subTree, entry.depth + 1);
    appendVNode(component.vnode, entry.depth + 1);
  }
  if (!map) return { available: false, retrieval: 'document.body._vnode bounded VNode/component/subTree traversal',
    traversal: { vnodes_seen: vnodeCount, components_seen: componentCount, deepest_node: deepestNode,
      max_vnodes: input.max_vnodes, max_components: input.max_components, max_queued_nodes: input.max_queued_nodes,
      max_depth: input.max_depth,
      truncated: traversalTruncated },
    property_names_only: { body: rootPropertyNames, root_vnode: rootVNodePropertyNames,
      vnode_component: rootVNode?.component ? Object.getOwnPropertyNames(rootVNode.component).slice(0, input.max_property_names) : [] },
    error: 'Could not locate MapView.map through the mounted root VNode tree' };

  const style = map.getStyle();
  const targetUrls = new Set(input.target_urls.map(url => {
    const normalized = url.replace(/^pmtiles:\/\//i, '');
    try { return new URL(normalized, input.base_url).href; } catch { return normalized; }
  }));
  const normalizeSourceUrl = value => {
    if (typeof value !== 'string') return null;
    const normalized = value.replace(/^pmtiles:\/\//i, '');
    try { return new URL(normalized, input.base_url).href; } catch { return normalized; }
  };
  const sources = Object.entries(style.sources || {}).map(([id, source]) => {
    const normalizedUrl = normalizeSourceUrl(source?.url);
    const normalizedTiles = Array.isArray(source?.tiles) ? source.tiles.map(normalizeSourceUrl) : [];
    const matchedTargetUrls = [normalizedUrl, ...normalizedTiles].filter(url => targetUrls.has(url));
    return { id, type: source?.type || null, url: source?.url || null, tiles: source?.tiles || null,
      bounds: source?.bounds || null, minzoom: source?.minzoom ?? null, maxzoom: source?.maxzoom ?? null,
      matched_target_urls: [...new Set(matchedTargetUrls)],
      is_source_loaded: (() => { try { return map.isSourceLoaded(id); } catch { return null; } })() };
  });
  const matchedSourceIds = new Set(sources.filter(source => source.matched_target_urls.length).map(source => source.id));
  const layers = (style.layers || []).filter(layer => matchedSourceIds.has(layer.source)).map(layer => {
    let visibility = null;
    try { visibility = map.getLayoutProperty(layer.id, 'visibility') ?? 'visible'; } catch { /* retained as null */ }
    return { id: layer.id, type: layer.type || null, source: layer.source || null,
      source_layer: layer['source-layer'] || null, filter: layer.filter || null,
      minzoom: layer.minzoom ?? null, maxzoom: layer.maxzoom ?? null,
      visibility, paint: layer.paint || null, layout: layer.layout || null };
  });
  const sampleFeature = feature => {
    const properties = feature?.properties || {};
    const typeOf = value => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
    const propertyTypes = {};
    for (const [key, value] of Object.entries(properties).slice(0, 100)) propertyTypes[key] = typeOf(value);
    return { geometry_type: feature?.geometry?.type || null, property_types: propertyTypes,
      selected_properties: { i_mid: properties.i_mid ?? null, source_row: properties.source_row ?? null } };
  };
  const renderedByLayer = [];
  const renderedFeaturesByLayer = new Map();
  for (const layer of layers) {
    try {
      const features = map.queryRenderedFeatures(undefined, { layers: [layer.id] });
      renderedFeaturesByLayer.set(layer.id, features);
      renderedByLayer.push({ layer_id: layer.id, feature_count: features.length,
        sample_features: features.slice(0, input.sample_limit).map(sampleFeature) });
    } catch (error) {
      renderedByLayer.push({ layer_id: layer.id, error: String(error?.message || error) });
    }
  }
  const sourceLayerKeys = new Set(layers.map(layer => `${layer.source}\n${layer.source_layer || ''}`));
  for (const sourceId of matchedSourceIds) {
    if (![...sourceLayerKeys].some(key => key.startsWith(`${sourceId}\n`))) sourceLayerKeys.add(`${sourceId}\n`);
  }
  const sourceFeatures = [];
  for (const key of sourceLayerKeys) {
    const [sourceId, sourceLayer] = key.split('\n');
    try {
      const features = map.querySourceFeatures(sourceId, sourceLayer ? { sourceLayer } : undefined);
      const inspected = features.slice(0, input.max_source_features_for_types);
      const featureTypeCounts = {};
      const propertyTypeCounts = {};
      for (const feature of inspected) {
        const geometryType = feature?.geometry?.type || 'unknown';
        featureTypeCounts[geometryType] = (featureTypeCounts[geometryType] || 0) + 1;
        for (const [name, value] of Object.entries(feature?.properties || {}).slice(0, 100)) {
          const type = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
          propertyTypeCounts[name] ||= {};
          propertyTypeCounts[name][type] = (propertyTypeCounts[name][type] || 0) + 1;
        }
      }
      sourceFeatures.push({ source_id: sourceId, source_layer: sourceLayer || null, feature_count: features.length,
        feature_count_examined_for_types: inspected.length, type_sample_truncated: features.length > inspected.length,
        geometry_type_counts: featureTypeCounts, property_type_counts: propertyTypeCounts,
        sample_features: features.slice(0, input.sample_limit).map(sampleFeature) });
    } catch (error) {
      sourceFeatures.push({ source_id: sourceId, source_layer: sourceLayer || null,
        error: String(error?.message || error) });
    }
  }
  let actualLayerOrder = [];
  let layerStackError = null;
  const layerOrderMethodAvailable = typeof map.getLayersOrder === 'function';
  try {
    if (!layerOrderMethodAvailable) throw new Error('Map#getLayersOrder is unavailable');
    actualLayerOrder = map.getLayersOrder();
  }
  catch (error) { layerStackError = String(error?.message || error); }
  const layerStack = actualLayerOrder.slice(0, input.max_style_layers).map((id, stackIndex) => {
    let layer;
    try { layer = map.getLayer(id); } catch { layer = null; }
    let visibility = null;
    try { visibility = map.getLayoutProperty(id, 'visibility') ?? 'visible'; } catch { /* report null if not readable */ }
    return { stack_index: stackIndex, id, type: layer?.type || null, source: layer?.source || null,
      source_layer: layer?.['source-layer'] || null, visibility,
      minzoom: layer?.minzoom ?? null, maxzoom: layer?.maxzoom ?? null };
  });
  const renderedFeatureDiagnostics = layers.map(layer => {
    const features = renderedFeaturesByLayer.get(layer.id) || [];
    const examined = features.slice(0, input.max_rendered_features_for_samples);
    const points = examined.filter(feature => feature?.geometry?.type === 'Point' &&
      Array.isArray(feature.geometry.coordinates) && feature.geometry.coordinates.length >= 2);
    const orderedPoints = points.map((feature, index) => ({ feature, index, value: feature.properties?.i_mid }))
      .filter(record => typeof record.value === 'number' && Number.isFinite(record.value))
      .sort((a, b) => b.value - a.value || a.index - b.index);
    const chosen = orderedPoints.slice(0, input.max_rendered_feature_samples);
    const samples = chosen.map(record => {
      const feature = record.feature;
      const coordinates = feature.geometry.coordinates;
      let projectedPixel = null;
      try {
        const projected = map.project(coordinates);
        projectedPixel = { x: projected.x, y: projected.y };
      } catch { /* preserve source coordinates when a projection is unavailable */ }
      return { source_coordinates: coordinates, projected_pixel: projectedPixel,
        i_mid: record.value, evaluated_paint: feature.layer?.paint || null,
        evaluated_layout: feature.layer?.layout || null };
    });
    const radii = samples.map(sample => sample.evaluated_paint?.['circle-radius']).filter(value => typeof value === 'number' && Number.isFinite(value));
    const opacities = samples.map(sample => sample.evaluated_paint?.['circle-opacity']).filter(value => typeof value === 'number' && Number.isFinite(value));
    const colors = [...new Set(samples.map(sample => sample.evaluated_paint?.['circle-color']).filter(value => typeof value === 'string'))];
    return { layer_id: layer.id, rendered_feature_count: features.length,
      rendered_features_examined: examined.length, examined_truncated: features.length > examined.length,
      numeric_i_mid_min: orderedPoints.length ? Math.min(...orderedPoints.map(record => record.value)) : null,
      numeric_i_mid_max: orderedPoints.length ? Math.max(...orderedPoints.map(record => record.value)) : null,
      sample_selection: 'highest numeric i_mid values; ties retain original query order', sample_count: samples.length, samples,
      sampled_circle_radius_min: radii.length ? Math.min(...radii) : null,
      sampled_circle_radius_max: radii.length ? Math.max(...radii) : null,
      sampled_circle_opacity_min: opacities.length ? Math.min(...opacities) : null,
      sampled_circle_opacity_max: opacities.length ? Math.max(...opacities) : null,
      sampled_circle_colors: colors };
  });
  let canvasDimensions = null;
  try {
    const canvas = map.getCanvas();
    canvasDimensions = { width: canvas.width, height: canvas.height,
      client_width: canvas.clientWidth, client_height: canvas.clientHeight };
  } catch { /* report unavailable dimensions explicitly */ }
  const center = map.getCenter();
  const bounds = map.getBounds();
  return { available: true, retrieval: 'document.body._vnode bounded VNode/component/subTree traversal', component_type: componentType,
    traversal: { vnodes_seen: vnodeCount, components_seen: componentCount, deepest_node: deepestNode,
      max_vnodes: input.max_vnodes, max_components: input.max_components, max_queued_nodes: input.max_queued_nodes,
      max_depth: input.max_depth,
      truncated: traversalTruncated },
    map_load_state: { style_loaded: map.isStyleLoaded(), tiles_loaded: map.areTilesLoaded(),
      style_source_ids: Object.keys(style.sources || {}) },
    camera: { center: { lng: center.lng, lat: center.lat }, zoom: map.getZoom(), bearing: map.getBearing(),
      pitch: map.getPitch(), bounds: bounds.toArray() },
    sources, matched_planned_source_ids: [...matchedSourceIds], layers,
    rendered_features_by_layer: renderedByLayer,
    actual_style_layer_stack: { method_available: layerOrderMethodAvailable,
      total_layers: actualLayerOrder.length, included_layers: layerStack.length,
      truncated: actualLayerOrder.length > layerStack.length, target_layer_indices: Object.fromEntries(layers.map(layer =>
        [layer.id, actualLayerOrder.indexOf(layer.id)])), layers: layerStack, error: layerStackError },
    canvas_dimensions: canvasDimensions,
    rendered_feature_diagnostics: renderedFeatureDiagnostics,
    source_features_by_layer: sourceFeatures,
    read_only_queries: ['getStyle', 'isSourceLoaded', 'getLayoutProperty', 'queryRenderedFeatures', 'querySourceFeatures',
      'getLayersOrder', 'getLayer', 'project', 'getCanvas', 'getCenter', 'getZoom', 'getBearing', 'getPitch', 'getBounds'] };
}

function browserStyleTitles(styles) {
  const titles = styles.map(style => typeof style.title === 'string' && style.title.length > 0
    ? style.title : String(style.key).replace(/^styles\//, ''));
  if (titles.length < 2) return titles;
  let prefix = titles[0];
  for (let i = 1; i < titles.length; i++) {
    while (prefix && !titles[i].startsWith(prefix)) prefix = prefix.slice(0, -1);
    if (!prefix) return titles;
  }
  const lastSeparator = Math.max(prefix.lastIndexOf(' '), prefix.lastIndexOf('—'), prefix.lastIndexOf('-'), prefix.lastIndexOf(':'));
  prefix = lastSeparator > 0 ? prefix.slice(0, lastSeparator + 1) : '';
  return prefix ? titles.map(title => title.slice(prefix.length)) : titles;
}

function bindStylePickerOptions(styles, options) {
  if (styles.length !== options.length) die(`Style picker has ${options.length} option(s) for ${styles.length} staged style asset(s)`);
  const seenValues = new Set();
  const seenLabels = new Set();
  const seenUrls = new Set();
  const byValue = new Map();
  const expectedTitles = browserStyleTitles(styles);
  for (const option of options) {
    const value = String(option.value ?? '').trim();
    const text = String(option.text ?? option.label ?? '').trim();
    if (!value || !text) die('Style picker option has an empty value or label');
    if (seenValues.has(value)) die(`Duplicate style picker option value: ${value}`);
    const normalizedLabel = text.toLocaleLowerCase();
    if (seenLabels.has(normalizedLabel)) die(`Duplicate style picker option label: ${text}`);
    seenValues.add(value);
    seenLabels.add(normalizedLabel);
    byValue.set(value, { value, text });
  }
  const bound = styles.map((style, index) => {
    const value = String(index);
    const option = byValue.get(value);
    if (!option) die(`Style picker value ${value} does not bind to staged style ${style.key}`);
    if (seenUrls.has(style.url)) die(`Duplicate staged style URL: ${style.url}`);
    seenUrls.add(style.url);
    const expectedTitle = expectedTitles[index];
    if (option.text !== expectedTitle) {
      die(`Style picker label "${option.text}" does not match Browser-normalized title "${expectedTitle}" for ${style.key} (${style.url})`);
    }
    const sourceTitle = typeof style.title === 'string' && style.title.length > 0 ? 'asset.title' : 'asset-key';
    return { ...style, ui_option_value: option.value, ui_option_text: option.text,
      ui_expected_title: expectedTitle, ui_label_basis: expectedTitles[index] === style.title ? sourceTitle : 'browser-common-prefix' };
  });
  if (byValue.size !== styles.length) die('Style picker contains unexpected option values');
  return bound;
}

async function waitUntil(page, predicate, message, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await page.waitForTimeout(200);
  }
  die(message);
}

async function waitForSourceQuiet(page, state, quietMs = 1000, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (state.inFlight.size === 0 && Date.now() - state.lastActivity >= quietMs) return;
    await page.waitForTimeout(100);
  }
  die(`Source requests did not settle within ${timeoutMs} ms; active=${state.inFlight.size}`);
}

async function settleDiagnosticView(page, sourceActivity, pending) {
  await waitForSourceQuiet(page, sourceActivity);
  while (pending.size) await Promise.all([...pending]);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForTimeout(500);
}

function selfTest(criteria, rendererInspectionCriteria, navigationFollowupCriteria) {
  validateRendererInspectionCriteria(rendererInspectionCriteria);
  const badRendererCriteria = JSON.parse(JSON.stringify(rendererInspectionCriteria));
  badRendererCriteria.render_inspection_limits.max_style_layers_reported = 511;
  let wrongRendererCapRefused = false;
  try { validateRendererInspectionCriteria(badRendererCriteria); } catch { wrongRendererCapRefused = true; }
  if (!wrongRendererCapRefused) die('Renderer criteria wrong-cap self-test failed');
  validateNavigationFollowupCriteria(navigationFollowupCriteria);
  const expectedRiverRoute = externalCollectionBrowserUrl(criteria.browser,
    'https://nthh.github.io/data-publications/river-plastic-inputs/collection.json');
  if (expectedRiverRoute !== 'https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/river-plastic-inputs/collection.json') {
    die('External collection route self-test failed');
  }
  validateCollectionChildLink({ tag_name: 'a', title_text: 'River', text_content: 'River',
    href: expectedRiverRoute, visible: true }, 'River', expectedRiverRoute);
  let wrongChildRouteRefused = false;
  try {
    validateCollectionChildLink({ tag_name: 'a', title_text: 'River', text_content: 'River',
      href: expectedRiverRoute.replace('/river-plastic-inputs/', '/free-flowing-rivers/'), visible: true },
      'River', expectedRiverRoute);
  } catch { wrongChildRouteRefused = true; }
  if (!wrongChildRouteRefused) die('Collection child route binding self-test failed');
  const badNavigationCriteria = JSON.parse(JSON.stringify(navigationFollowupCriteria));
  badNavigationCriteria.scope.no_direct_router_or_vue_access = false;
  let badNavigationRefused = false;
  try { validateNavigationFollowupCriteria(badNavigationCriteria); } catch { badNavigationRefused = true; }
  if (!badNavigationRefused) die('Navigation follow-up criteria self-test failed');
  const ranged = parseSingleByteRange('bytes=0-15', 100);
  if (ranged.start !== 0 || ranged.end !== 15 || ranged.length !== 16) die('Range self-test failed');
  const suffix = parseContentRange('bytes 8-15/100');
  if (suffix.start !== 8 || suffix.end !== 15 || suffix.total !== 100) die('Content-Range self-test failed');
  let rejected = 0;
  for (const value of [undefined, 'bytes=0-15,32-47', 'bytes=0-', 'bytes=90-100']) {
    try { parseSingleByteRange(value, 100); } catch { rejected++; }
  }
  if (rejected !== 4) die('Invalid/multipart range self-test failed');
  const data = { url: 'https://data.source.coop/nthh/x/assets/a.pmtiles', content_type: 'application/vnd.pmtiles' };
  const metadata = { url: 'https://data.source.coop/nthh/x/README.md', content_type: 'text/markdown' };
  if (!isDataObject(data) || isDataObject(metadata)) die('Object classification self-test failed');
  const objectMap = new Map([[data.url, data]]);
  const prefix = 'https://data.source.coop/nthh/x/';
  if (!isExactProductObject(data.url, objectMap, prefix) ||
      isExactProductObject(`${data.url}?download=1`, objectMap, prefix) ||
      isExactProductObject('https://data.source.coop/nthh/x-other/assets/a.pmtiles', objectMap, prefix)) {
    die('Exact object/product-prefix allowlist self-test failed');
  }
  const knownProducts = new Set(['lakeatlas', 'hydrolakes']);
  const repositorySupplement = { kind: 'supplement', object_key: 'lakeatlas/metadata/semantics/README.md',
    source: { kind: 'repository', path: 'datasets/lakeatlas/metadata-enhancements/v1/README.md' } };
  if (sourceDatasetId(repositorySupplement, knownProducts) !== 'lakeatlas') {
    die('Repository supplement ownership self-test failed');
  }
  for (const invalid of [
    { ...repositorySupplement, source: { kind: 'repository', path: 'datasets/hydrolakes/metadata/README.md' } },
    { kind: 'display_asset', object_key: 'lakeatlas/display/style.json', source: { kind: 'display_package', dataset_id: 'hydrolakes' } },
  ]) {
    let refused = false;
    try { sourceDatasetId(invalid, knownProducts); } catch { refused = true; }
    if (!refused) die('Cross-product Source plan ownership self-test failed');
  }
  const headObject = { url: data.url, size_bytes: 100, content_type: 'application/vnd.pmtiles' };
  const headRequest = { url: () => data.url };
  const headHeaders = { 'content-length': '100', 'content-type': 'application/vnd.pmtiles',
    'accept-ranges': 'bytes', 'access-control-allow-origin': '*' };
  const headResponse = { status: () => 200, headers: () => headHeaders };
  validateHeadMetadata(headRequest, headResponse, headObject);
  let badHeadRefused = false;
  try { validateHeadMetadata(headRequest, { status: () => 200, headers: () => ({ ...headHeaders, 'content-length': '99' }) }, headObject); }
  catch { badHeadRefused = true; }
  const verifiedHeadRecord = { method: 'HEAD', status: 200, head_metadata_verified: true };
  if (!badHeadRefused || !classifyHeadAbortAfterVerifiedHeaders(verifiedHeadRecord, 'net::ERR_ABORTED') ||
      verifiedHeadRecord.status_check !== 'passed_head_metadata_cancelled_after_headers' ||
      classifyHeadAbortAfterVerifiedHeaders({ method: 'HEAD', status: 200, head_metadata_verified: true }, 'net::ERR_FAILED') ||
      classifyHeadAbortAfterVerifiedHeaders({ method: 'GET', status: 200, head_metadata_verified: true }, 'net::ERR_ABORTED')) {
    die('Narrow verified-HEAD cancellation self-test failed');
  }
  const tileBytes = Buffer.alloc(128);
  tileBytes.write('PMTiles', 0, 'ascii');
  tileBytes.writeUInt8(3, 7);
  tileBytes.writeBigUInt64LE(128n, 56);
  tileBytes.writeBigUInt64LE(64n, 64);
  const tileRegion = parsePmtilesV3TileDataRegion(tileBytes, 192);
  const tileRequestRecords = [
    { url: data.url, method: 'GET', status_check: 'passed', request_range: 'bytes=0-127', planned_size_bytes: 192, pmtiles_v3_header: tileRegion },
    { url: data.url, method: 'GET', status_check: 'passed', request_range: 'bytes=128-143', planned_size_bytes: 192 },
  ];
  if (!pmtilesTileDataRangeEvidence(data.url, tileRequestRecords).passed ||
      pmtilesTileDataRangeEvidence(data.url, tileRequestRecords.slice(0, 1)).passed) {
    die('PMTiles v3 tile-data range evidence self-test failed');
  }
  const lakeStyles = [
    { key: 'display_style_lakeatlas-1', title: 'Lakeatlas Polygons display style', style_json_name: 'lakeatlas-polygons', url: 'https://example.test/polygons.json', is_default: true },
    { key: 'display_style_lakeatlas-2', title: 'Lakeatlas Pour Points display style', style_json_name: 'lakeatlas-pour-points', url: 'https://example.test/points.json', is_default: false },
  ];
  const boundLakeStyles = bindStylePickerOptions(lakeStyles, [
    { value: '0', text: 'Polygons display style' },
    { value: '1', text: 'Pour Points display style' },
  ]);
  if (boundLakeStyles[1].url !== lakeStyles[1].url || boundLakeStyles[0].ui_label_basis !== 'browser-common-prefix' ||
      boundLakeStyles[0].ui_expected_title !== 'Polygons display style') {
    die('Style picker common-prefix label binding self-test failed');
  }
  let unnormalizedTitleRefused = false;
  try {
    bindStylePickerOptions(lakeStyles, [
      { value: '0', text: 'Lakeatlas Polygons display style' },
      { value: '1', text: 'Lakeatlas Pour Points display style' },
    ]);
  } catch { unnormalizedTitleRefused = true; }
  if (!unnormalizedTitleRefused) die('Style picker must require exact Browser common-prefix normalization');
  const unprefixedStyles = [
    { key: 'styles/alpha', title: 'Alpha' }, { key: 'styles/beta', title: 'Beta' },
  ];
  if (browserStyleTitles(unprefixedStyles).join('|') !== 'Alpha|Beta') die('Style picker non-prefix title self-test failed');
  for (const duplicateOptions of [
    [{ value: '0', text: 'Lakeatlas' }, { value: '0', text: 'Lakeatlas points' }],
    [{ value: '0', text: 'Lakeatlas' }, { value: '1', text: 'Lakeatlas' }],
  ]) {
    let duplicateRefused = false;
    try { bindStylePickerOptions(lakeStyles, duplicateOptions); } catch { duplicateRefused = true; }
    if (!duplicateRefused) die('Duplicate style picker option self-test failed');
  }
  const fakeUrl = 'https://data.source.coop/nthh/river-plastic-inputs/display/river.pmtiles';
  const fakeFeature = { geometry: { type: 'Point', coordinates: [20, 0] },
    properties: { i_mid: 3.25, source_row: 17 },
    layer: { paint: { 'circle-radius': 4, 'circle-opacity': 0.8, 'circle-color': '#4da6c8' },
      layout: { visibility: 'visible' } } };
  const fakeRenderedFeatures = [9, 9, 7, 5, 4, 3.25, 2].map((i_mid, index) => ({ ...fakeFeature,
    properties: { i_mid, source_row: index } }));
  const fakeMap = {
    getStyle: () => ({ sources: { 'stac-tile-0': { type: 'vector', url: `pmtiles://${fakeUrl}` } },
      layers: [{ id: 'river-inputs', type: 'circle', source: 'stac-tile-0', 'source-layer': 'river_inputs',
        minzoom: 0, maxzoom: 8, paint: { 'circle-radius': 4 } }] }),
    isSourceLoaded: () => true, isStyleLoaded: () => true, areTilesLoaded: () => true,
    getLayoutProperty: () => 'visible', queryRenderedFeatures: () => fakeRenderedFeatures,
    getLayersOrder: () => ['basemap-land', 'river-inputs', ...Array.from({ length: 512 }, (_, i) => `layer-${i}`)],
    getLayer: id => id === 'river-inputs' ? { id, type: 'circle', source: 'stac-tile-0', 'source-layer': 'river_inputs' }
      : { id, type: 'fill', source: 'protomaps' },
    project: coordinates => ({ x: coordinates[0] * 10, y: coordinates[1] * 10 }),
    getCanvas: () => ({ width: 1440, height: 1000, clientWidth: 1440, clientHeight: 1000 }),
    querySourceFeatures: () => [fakeFeature], getCenter: () => ({ lng: 20, lat: 0 }), getZoom: () => 3,
    getBearing: () => 0, getPitch: () => 0, getBounds: () => ({ toArray: () => [[0, -10], [40, 10]] }),
  };
  const priorDocument = globalThis.document;
  const rendererLimits = { sample_limit: 5, max_source_features_for_types: 5000, max_vnodes: 5000,
    max_components: 2000, max_queued_nodes: 7000, max_depth: 64, max_property_names: 80,
    max_style_layers: 512, max_rendered_features_for_samples: 5000, max_rendered_feature_samples: 5 };
  globalThis.document = { body: { _vnode: { type: { name: 'StacBrowser' },
    component: { type: { name: 'StacBrowser' }, subTree: { type: { name: 'MapView' },
      component: { type: { name: 'MapView' }, proxy: { map: fakeMap }, subTree: { type: 'div' } } } } } } };
  let rendererSelfTest;
  try {
    rendererSelfTest = inspectMapRendererState({ target_urls: [fakeUrl], base_url: 'https://browser.example/', ...rendererLimits });
  } finally {
    if (priorDocument === undefined) delete globalThis.document;
    else globalThis.document = priorDocument;
  }
  if (!rendererSelfTest?.available || rendererSelfTest.matched_planned_source_ids.join(',') !== 'stac-tile-0' ||
      rendererSelfTest.layers[0]?.type !== 'circle' ||
      rendererSelfTest.source_features_by_layer[0]?.feature_count !== 1 ||
      rendererSelfTest.source_features_by_layer[0]?.sample_features[0]?.property_types?.i_mid !== 'number' ||
      rendererSelfTest.actual_style_layer_stack?.included_layers !== 512 ||
      rendererSelfTest.actual_style_layer_stack?.truncated !== true ||
      rendererSelfTest.actual_style_layer_stack?.target_layer_indices?.['river-inputs'] !== 1 ||
      rendererSelfTest.canvas_dimensions?.client_width !== 1440 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.rendered_feature_count !== 7 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.numeric_i_mid_min !== 2 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.numeric_i_mid_max !== 9 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.length !== 5 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.[0]?.i_mid !== 9 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.[1]?.i_mid !== 9 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.[1]?.source_coordinates?.[0] !== 20 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.[0]?.projected_pixel?.x !== 200 ||
      rendererSelfTest.rendered_feature_diagnostics?.[0]?.samples?.[0]?.evaluated_paint?.['circle-radius'] !== 4) {
    die('Read-only renderer-state inspection self-test failed');
  }
  const savedDocument = globalThis.document;
  globalThis.document = { body: { _vnode: { children: Array.from({ length: 100 }, () => ({ type: 'child' })), secret: 'must-not-escape' } } };
  let unavailableRenderer;
  try {
    unavailableRenderer = inspectMapRendererState({ target_urls: [fakeUrl], base_url: 'https://browser.example/',
      ...rendererLimits, max_vnodes: 10, max_components: 2, max_queued_nodes: 4, max_depth: 8 });
  } finally {
    if (savedDocument === undefined) delete globalThis.document;
    else globalThis.document = savedDocument;
  }
  if (unavailableRenderer.available || !unavailableRenderer.traversal?.truncated ||
      unavailableRenderer.traversal.vnodes_seen > 10 || unavailableRenderer.traversal.components_seen > 2 ||
      unavailableRenderer.property_names_only?.root_vnode?.includes('secret') !== true ||
      JSON.stringify(unavailableRenderer).includes('must-not-escape')) {
    die('Bounded property-names-only unavailable renderer self-test failed');
  }
  const route = `${BROWSER_ORIGIN}/${criteria.browser.external_catalog_route.replace('{catalog_host_path}', 'nthh.github.io/data-publications/catalog.json')}`;
  if (route !== 'https://browser.portolan-sdi.org/#/external/nthh.github.io/data-publications/catalog.json') {
    die(`External catalog route construction self-test failed: ${route}`);
  }
  console.log('offline predicates passed: bounded ranges, Source product binding, verified HEAD classification, PMTiles tile-data proof, exact Browser style-title normalization, read-only renderer inspection, and external route construction');
}

function cleanHttpsUrl(value, field) {
  let url;
  try { url = new URL(value); } catch { die(`${field} is not an absolute URL`); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
    die(`${field} must be a clean absolute HTTPS URL`);
  }
  return url;
}

async function readJson(file, field) {
  let bytes;
  try { bytes = await readFile(file); } catch (error) { die(`Cannot read ${field}: ${error.message}`); }
  let value;
  try { value = JSON.parse(bytes.toString('utf8')); } catch (error) { die(`Invalid JSON in ${field}: ${error.message}`); }
  return { bytes, value };
}

function validateRendererInspectionCriteria(value) {
  const expectedSampleSelection = 'Among the bounded examined point features with finite numeric i_mid, select up to five highest values; ties retain original query order. These samples locate the most visible expected symbols and are diagnostic, not representative validation. Report the full rendered count, examined count/truncation, and numeric i_mid min/max over the examined set.';
  if (value?.kind !== 'read_only_browser_renderer_diagnostic' ||
      value.dataset_id !== 'river-plastic-inputs' ||
      value.frozen_before_viewer_run !== true ||
      value.scope?.mode !== 'developer_diagnostic_not_acceptance' ||
      value.observations?.features?.maximum_source_features_examined_for_type_counts !== 5000 ||
      value.vue_traversal_limits?.root_mount_target !== 'body' ||
      value.vue_traversal_limits?.root_vnode_property !== '_vnode' ||
      value.vue_traversal_limits?.max_vnodes !== 5000 ||
      value.vue_traversal_limits?.max_components !== 2000 ||
      value.vue_traversal_limits?.max_queued_nodes !== 7000 ||
      value.vue_traversal_limits?.max_depth !== 64 ||
      value.vue_traversal_limits?.max_property_names_on_unavailable !== 80 ||
      value.render_inspection_limits?.max_style_layers_reported !== 512 ||
      value.render_inspection_limits?.max_rendered_features_examined_for_sample_selection !== 5000 ||
      value.render_inspection_limits?.max_rendered_feature_samples !== 5 ||
      value.render_inspection_limits?.sample_selection !== expectedSampleSelection) {
    die('River renderer inspection criteria do not match the frozen read-only protocol');
  }
  return value;
}

async function assertSafeFile(root, relative, expectedSize, expectedSha, field) {
  if (typeof relative !== 'string' || relative.includes('\\') || relative.startsWith('/') ||
      relative.split('/').some(part => part === '..' || part === '' || part === '.')) {
    die(`${field} has an unsafe path: ${relative}`);
  }
  const file = path.resolve(root, ...relative.split('/'));
  if (file !== root && !file.startsWith(root + path.sep)) die(`${field} escapes its root`);
  let stat;
  try { stat = await lstat(file); } catch { die(`${field} is missing: ${relative}`); }
  if (stat.isSymbolicLink() || !stat.isFile()) die(`${field} is not a regular non-symlink file: ${relative}`);
  const bytes = await readFile(file);
  if (bytes.length !== expectedSize) die(`${field} size mismatch for ${relative}: ${bytes.length} != ${expectedSize}`);
  if (sha256(bytes) !== expectedSha) die(`${field} SHA-256 mismatch for ${relative}`);
  return { file, bytes };
}

async function listRegularFiles(root, relative = '') {
  const files = [];
  for (const item of await readdir(path.join(root, relative), { withFileTypes: true })) {
    const child = relative ? `${relative}/${item.name}` : item.name;
    const full = path.join(root, child);
    const info = await lstat(full);
    if (info.isSymbolicLink()) die(`Symlink in staged catalog: ${child}`);
    if (info.isDirectory()) files.push(...await listRegularFiles(root, child));
    else if (info.isFile()) files.push(child);
    else die(`Unsupported filesystem entry in staged catalog: ${child}`);
  }
  return files;
}

function pageContentType(relative) {
  const extension = path.posix.extname(relative).toLowerCase();
  return ({ '.json': 'application/json', '.md': 'text/markdown', '.txt': 'text/plain',
    '.png': 'image/png', '.svg': 'image/svg+xml' })[extension] || 'application/octet-stream';
}

async function loadInputs(args, criteria) {
  if (!['preflight', 'live'].includes(args.mode)) die('Choose --mode preflight or --mode live');
  if (!args.plan || !args['expected-pages-plan-sha256'] || !args.out) {
    die('Usage: portolan-browser-check.mjs --mode preflight|live --plan PATH --expected-pages-plan-sha256 SHA256 --out NEW_DIR [--catalog-dir DIR] [--dataset ID ...]');
  }
  if (!/^[0-9a-f]{64}$/.test(args['expected-pages-plan-sha256'])) die('Expected Pages plan SHA-256 must be 64 lowercase hex characters');
  const { bytes: planBytes, value: plan } = await readJson(path.resolve(args.plan), 'Pages publish plan');
  const actualPlanSha = sha256(planBytes);
  if (actualPlanSha !== args['expected-pages-plan-sha256']) die('Pages publish plan differs from its pre-run SHA-256 pin');
  if (plan.schema_version !== 1 || plan.destination !== criteria.aggregate.destination || plan.region !== null) {
    die('Pages plan destination, schema, or region differs from frozen criteria');
  }
  const catalogDir = path.resolve(args['catalog-dir'] || path.join(path.dirname(path.resolve(args.plan)), 'catalog'));
  const pageFiles = new Map();
  let pageBytesTotal = 0;
  for (const entry of plan.files || []) {
    if (!entry.path?.startsWith('catalog/') || !entry.target_url || !Number.isSafeInteger(entry.size_bytes) ||
        !/^[0-9a-f]{64}$/.test(entry.sha256)) die('Malformed or non-catalog file in Pages plan');
    const relative = entry.path.slice('catalog/'.length);
    const extension = path.posix.extname(relative).toLowerCase();
    if (DATA_EXTENSIONS.has(extension) || /\.(zip|tar|gz|7z|rar|icechunk)$/i.test(relative)) {
      die(`Bulk data must not be in the Pages artifact: ${entry.path}`);
    }
    if (!SMALL_METADATA_EXTENSIONS.has(extension)) die(`Unsupported Pages metadata file type: ${entry.path}`);
    if (entry.size_bytes > PAGE_FILE_LIMIT) die(`Pages metadata file exceeds ${PAGE_FILE_LIMIT} bytes: ${entry.path}`);
    pageBytesTotal += entry.size_bytes;
    const target = cleanHttpsUrl(entry.target_url, `target URL for ${entry.path}`);
    const expectedUrl = new URL(relative, PAGE_BASE).href;
    if (target.href !== expectedUrl) die(`Target URL is not the exact Pages path for ${entry.path}`);
    if (pageFiles.has(target.href)) die(`Duplicate Pages target URL: ${target.href}`);
    const local = await assertSafeFile(catalogDir, relative, entry.size_bytes, entry.sha256, 'staged Pages file');
    pageFiles.set(target.href, { url: target.href, path: entry.path, localPath: local.file,
      bytes: local.bytes, size_bytes: entry.size_bytes, sha256: entry.sha256,
      content_type: pageContentType(relative) });
  }
  if (pageFiles.size === 0 || pageBytesTotal > PAGE_TOTAL_LIMIT) die('Pages plan is empty or exceeds the metadata size ceiling');
  const actualFiles = (await listRegularFiles(catalogDir)).sort();
  const plannedFiles = [...pageFiles.values()].map(item => item.path.slice('catalog/'.length)).sort();
  if (JSON.stringify(actualFiles) !== JSON.stringify(plannedFiles)) die('Staged catalog file inventory differs from the Pages publish plan');
  const pageRootUrl = new URL('catalog.json', PAGE_BASE).href;
  const rootPage = pageFiles.get(pageRootUrl);
  if (!rootPage) die('Pages plan does not contain the aggregate catalog root');
  const rootJson = JSON.parse(rootPage.bytes.toString('utf8'));
  const rootChildren = (rootJson.links || []).filter(link => link.rel === 'child');
  const collections = new Map();
  for (const link of rootChildren) {
    if (typeof link.href !== 'string') die('Catalog child link lacks href');
    const url = new URL(link.href, pageRootUrl).href;
    const file = pageFiles.get(url);
    if (!file) die(`Child collection URL is not a file in the Pages plan: ${url}`);
    const collection = JSON.parse(file.bytes.toString('utf8'));
    if (collection.type !== 'Collection' || !REQUIRED_COLLECTIONS.includes(collection.id)) die(`Unexpected collection in aggregate root: ${collection.id}`);
    if (collections.has(collection.id)) die(`Duplicate collection id: ${collection.id}`);
    const assets = collection.assets || {};
    const pmtiles = [];
    const styles = [];
    for (const [key, asset] of Object.entries(assets)) {
      const href = typeof asset.href === 'string' ? new URL(asset.href, url).href : null;
      const assetType = (asset.type || '').toLowerCase();
      const assetPath = href ? new URL(href).pathname.toLowerCase() : '';
      if (assetType.includes('pmtiles') || assetPath.endsWith('.pmtiles')) {
        if (!href) die(`PMTiles asset ${collection.id}/${key} has no HTTPS href`);
        pmtiles.push({ key, title: asset.title || key, url: href, file_size: asset['file:size'] ?? null,
          roles: Array.isArray(asset.roles) ? asset.roles : [] });
      }
      if ((asset.roles || []).includes('style')) {
        if (!href || !pageFiles.has(href)) die(`Style asset ${collection.id}/${key} is not in the exact Pages plan`);
        styles.push({ key, title: asset.title || key, url: href, is_default: (asset.roles || []).includes('default') });
      }
    }
    collections.set(collection.id, { id: collection.id, title: collection.title, url, pagePath: file.path,
      pmtiles, styles, rootLinkTitle: link.title || null });
  }
  for (const collection of collections.values()) {
    if (collection.styles.length && collection.styles.filter(style => style.is_default).length !== 1) {
      die(`Collection ${collection.id} must have exactly one default style`);
    }
  }
  const sourcePlanPath = path.resolve(args['source-plan'] || DEFAULT_SOURCE_PLAN);
  const { bytes: sourcePlanBytes, value: sourcePlan } = await readJson(sourcePlanPath, 'immutable Source plan');
  const sourcePlanSha = sha256(sourcePlanBytes);
  if (sourcePlanSha !== criteria.source_objects.plan_sha256) die('Immutable Source plan differs from its frozen SHA-256');
  if (sourcePlan.plan_type !== 'source_coop_immutable_exact_file_plan' || sourcePlan.products?.length !== 5) {
    die('Immutable Source plan does not contain the five approved products');
  }
  const sourceObjects = new Map();
  const prefixes = new Map();
  const productIds = new Set();
  for (const product of sourcePlan.products) {
    if (product.owner !== 'nthh' || product.bucket !== 'nthh') die(`Unexpected Source product owner: ${product.product_id}`);
    if (!REQUIRED_COLLECTIONS.includes(product.dataset_id) || product.dataset_id !== product.product_id || productIds.has(product.product_id)) {
      die(`Unexpected, mismatched, or duplicate Source product identity: ${product.product_id}`);
    }
    productIds.add(product.product_id);
    const prefix = `${SOURCE_ORIGIN}/nthh/${product.product_id}/`;
    prefixes.set(product.dataset_id, prefix);
  }
  if (productIds.size !== REQUIRED_COLLECTIONS.length || REQUIRED_COLLECTIONS.some(id => !productIds.has(id))) {
    die('Immutable Source plan product inventory differs from frozen criteria');
  }
  for (const entry of sourcePlan.files || []) {
    const url = entry.raw_url_proposed;
    if (typeof url !== 'string') die('Source plan object lacks raw_url_proposed');
    const parsed = cleanHttpsUrl(url, 'Source object URL');
    if (parsed.origin !== SOURCE_ORIGIN || !parsed.pathname.startsWith('/nthh/')) die(`Unexpected Source object origin or owner: ${url}`);
    const productId = sourceDatasetId(entry, productIds);
    const productPrefix = prefixes.get(productId);
    if (parsed.pathname !== `/nthh/${entry.object_key}`) die(`Source URL path differs from exact planned object_key: ${url}`);
    if (!productPrefix || !url.startsWith(productPrefix)) die(`Source object is outside its dataset product prefix: ${url}`);
    if (!/^[0-9a-f]{64}$/.test(entry.sha256) || !Number.isSafeInteger(entry.size_bytes)) die(`Malformed Source object identity: ${url}`);
    if (sourceObjects.has(url)) die(`Duplicate Source object URL: ${url}`);
    sourceObjects.set(url, { url, size_bytes: entry.size_bytes, sha256: entry.sha256,
      content_type: (entry.content_type || 'application/octet-stream').split(';')[0],
      dataset_id: productId, kind: entry.kind || null });
  }
  for (const collection of collections.values()) {
    for (const layer of collection.pmtiles) {
      const obj = sourceObjects.get(layer.url);
      if (!obj) die(`PMTiles URL is absent from the immutable Source plan: ${layer.url}`);
      if (obj.dataset_id !== collection.id) die(`PMTiles URL belongs to a different Source product: ${layer.url}`);
      if (layer.file_size !== null && layer.file_size !== obj.size_bytes) die(`PMTiles file:size differs from Source plan: ${layer.url}`);
      layer.size_bytes = obj.size_bytes;
      layer.sha256 = obj.sha256;
    }
    const referencedPmtiles = new Set();
    for (const style of collection.styles) {
      let styleJson;
      try { styleJson = JSON.parse(pageFiles.get(style.url).bytes.toString('utf8')); }
      catch (error) { die(`Invalid staged style JSON for ${collection.id}/${style.key}: ${error.message}`); }
      style.style_json_name = typeof styleJson.name === 'string' ? styleJson.name : null;
      style.pmtiles_urls = stylePmtilesUrls(styleJson);
      for (const url of style.pmtiles_urls) {
        if (!collection.pmtiles.some(layer => layer.url === url)) die(`Style ${collection.id}/${style.key} references an unlisted PMTiles asset: ${url}`);
        referencedPmtiles.add(url);
      }
      if (!style.pmtiles_urls.length) die(`Style ${collection.id}/${style.key} does not reference a PMTiles asset`);
    }
    const uncoveredPmtiles = collection.pmtiles.filter(layer => !referencedPmtiles.has(layer.url));
    if (uncoveredPmtiles.length) die(`Collection ${collection.id} styles do not cover PMTiles assets: ${uncoveredPmtiles.map(layer => layer.key).join(', ')}`);
  }
  const presentIds = [...collections.keys()].sort();
  const missingIds = REQUIRED_COLLECTIONS.filter(id => !collections.has(id));
  const duplicateSelected = new Set(args.datasets || []);
  if (duplicateSelected.size !== (args.datasets || []).length) die('Duplicate --dataset selection');
  const selectedIds = args.datasets?.length ? [...args.datasets] : [...presentIds];
  for (const id of selectedIds) {
    if (!REQUIRED_COLLECTIONS.includes(id)) die(`Unknown --dataset id: ${id}`);
    if (!collections.has(id)) die(`Selected collection is not present in this staged catalog: ${id}`);
  }
  const partial = missingIds.length > 0 || selectedIds.length !== REQUIRED_COLLECTIONS.length;
  if (!partial && collections.size !== criteria.aggregate.expected_collection_count) die('Aggregate collection count differs from criteria');
  if (!partial && [...collections.values()].reduce((sum, c) => sum + c.pmtiles.length, 0) !== criteria.aggregate.expected_pmtiles_count) {
    die('Aggregate PMTiles count differs from criteria');
  }
  for (const id of selectedIds) {
    const expected = criteria.aggregate.expected_pmtiles_by_collection[id];
    if (collections.get(id).pmtiles.length !== expected) die(`PMTiles count differs for ${id}`);
  }
  const out = path.resolve(args.out);
  try { await lstat(out); die('Output directory already exists'); } catch (error) { if (error.message === 'Output directory already exists') throw error; }
  await mkdir(out, { recursive: false });
  return { mode: args.mode, plan, planSha: actualPlanSha, catalogDir, pageFiles, pageRootUrl,
    collections, presentIds, missingIds, selectedIds, partial, sourcePlan, sourcePlanSha, sourceObjects,
    prefixes, out, stageReady: !partial };
}

function sourceResponseRecord(request, response, object, receivedBody) {
  const headers = response.headers();
  const method = request.method();
  const rangeText = request.headers()['range'] || null;
  const common = { url: request.url(), dataset_id: object.dataset_id, method, status: response.status(),
    planned_size_bytes: object.size_bytes, planned_sha256: object.sha256,
    response_content_type: headers['content-type'] || null,
    response_content_length: headers['content-length'] === undefined ? null : Number(headers['content-length']),
    accept_ranges: headers['accept-ranges'] || null,
    content_range: headers['content-range'] || null,
    access_control_allow_origin: headers['access-control-allow-origin'] || null,
    access_control_expose_headers: headers['access-control-expose-headers'] || null };
  if (method === 'OPTIONS') {
    const allowOrigin = headers['access-control-allow-origin'];
    const allowedMethods = (headers['access-control-allow-methods'] || '').toLowerCase().split(',').map(v => v.trim());
    const requestedHeaders = (request.headers()['access-control-request-headers'] || '').toLowerCase()
      .split(',').map(v => v.trim()).filter(Boolean);
    const allowedHeaders = (headers['access-control-allow-headers'] || '').toLowerCase().split(',').map(v => v.trim());
    const requestedMethod = (request.headers()['access-control-request-method'] || '').toLowerCase();
    if (response.status() < 200 || response.status() >= 300) die(`Source CORS preflight returned ${response.status()}: ${request.url()}`);
    if (allowOrigin !== '*' && allowOrigin !== BROWSER_ORIGIN) die(`Source preflight does not allow Browser origin: ${request.url()}`);
    if (requestedMethod !== 'get') die(`Unexpected Source preflight method ${requestedMethod || '(missing)'}: ${request.url()}`);
    if (!allowedMethods.includes('*') && !allowedMethods.includes(requestedMethod)) die(`Source preflight does not allow GET: ${request.url()}`);
    if (requestedHeaders.some(name => !allowedHeaders.includes('*') && !allowedHeaders.includes(name))) {
      die(`Source preflight does not allow requested headers ${requestedHeaders.join(', ')}: ${request.url()}`);
    }
    return { ...common, request_range: rangeText, preflight_requested_method: requestedMethod, preflight_requested_headers: requestedHeaders,
      allow_methods: allowedMethods, allow_headers: allowedHeaders, response_body_bytes: receivedBody.length,
      status_check: 'passed_preflight' };
  }
  if (method === 'HEAD') {
    validateHeadMetadata(request, response, object);
    return { ...common, request_range: null, response_body_bytes: 0, head_metadata_verified: true,
      status_check: 'passed_head_metadata' };
  }
  if (method !== 'GET') return { ...common, request_range: rangeText, response_body_bytes: receivedBody.length,
    status_check: 'observed_only' };
  if (rangeText) {
    const requested = parseSingleByteRange(rangeText, object.size_bytes);
    const actual = parseContentRange(headers['content-range']);
    if (response.status() !== 206) die(`Ranged Source GET returned ${response.status()}: ${request.url()}`);
    if (actual.start !== requested.start || actual.end !== requested.end || actual.total !== object.size_bytes) {
      die(`Content-Range differs from the exact request/plan: ${request.url()}`);
    }
    if (receivedBody.length !== requested.length) die(`Received body length differs from range: ${request.url()}`);
    if (headers['accept-ranges']?.toLowerCase() !== 'bytes') die(`Source response lacks Accept-Ranges: bytes: ${request.url()}`);
    const expose = (headers['access-control-expose-headers'] || '').toLowerCase().split(',').map(v => v.trim());
    if (!expose.includes('*') && !expose.includes('content-range')) die(`Source CORS does not expose Content-Range: ${request.url()}`);
    const allowedOrigin = headers['access-control-allow-origin'];
    if (allowedOrigin !== '*' && allowedOrigin !== BROWSER_ORIGIN) die(`Source CORS does not allow Browser origin: ${request.url()}`);
    const expectedMime = object.content_type.toLowerCase();
    if (expectedMime && !(headers['content-type'] || '').split(';')[0].toLowerCase().startsWith(expectedMime)) {
      die(`Source MIME differs from plan: ${request.url()}`);
    }
    return { ...common, request_range: rangeText, content_range: headers['content-range'],
      response_body_bytes: receivedBody.length, response_body_sha256: sha256(receivedBody), status_check: 'passed' };
  }
  if (isDataObject(object)) die(`Full GET of analytical/PMTiles object is forbidden: ${request.url()}`);
  const extension = path.posix.extname(new URL(request.url()).pathname).toLowerCase();
  if (!SMALL_METADATA_EXTENSIONS.has(extension) || object.size_bytes > 524288) {
    die(`Full GET is permitted only for small planned metadata: ${request.url()}`);
  }
  if (response.status() !== 200) die(`Full metadata GET returned ${response.status()}: ${request.url()}`);
  if (receivedBody.length !== object.size_bytes || sha256(receivedBody) !== object.sha256) {
    die(`Full metadata response differs from the immutable Source plan: ${request.url()}`);
  }
  const allowedOrigin = headers['access-control-allow-origin'];
  if (allowedOrigin !== '*' && allowedOrigin !== BROWSER_ORIGIN) die(`Metadata CORS does not allow Browser origin: ${request.url()}`);
  return { ...common, request_range: null, response_body_bytes: receivedBody.length,
    response_body_sha256: sha256(receivedBody), status_check: 'passed_full_metadata' };
}

function validateHeadMetadata(request, response, object) {
  const headers = response.headers();
  const contentLength = Number(headers['content-length']);
  const contentType = (headers['content-type'] || '').split(';')[0].toLowerCase();
  const allowedOrigin = headers['access-control-allow-origin'];
  if (response.status() !== 200) die(`HEAD metadata probe returned ${response.status()}: ${request.url()}`);
  if (!Number.isSafeInteger(contentLength) || contentLength !== object.size_bytes) {
    die(`HEAD Content-Length differs from the immutable plan for ${request.url()}`);
  }
  if (contentType !== object.content_type.toLowerCase()) die(`HEAD Content-Type differs from plan: ${request.url()}`);
  if (headers['accept-ranges']?.toLowerCase() !== 'bytes') die(`HEAD response lacks Accept-Ranges: bytes: ${request.url()}`);
  if (allowedOrigin !== '*' && allowedOrigin !== BROWSER_ORIGIN) die(`HEAD CORS does not allow Browser origin: ${request.url()}`);
}

function classifyHeadAbortAfterVerifiedHeaders(record, failure) {
  if (record.method !== 'HEAD' || record.status !== 200 || !record.head_metadata_verified || failure !== 'net::ERR_ABORTED') {
    return false;
  }
  record.status_check = 'passed_head_metadata_cancelled_after_headers';
  record.cancellation_detail = 'net::ERR_ABORTED after HTTP 200 HEAD metadata headers passed exact plan checks; cancellation cause unknown; HEAD has no expected response body';
  return true;
}

function parsePmtilesV3TileDataRegion(bytes, plannedSize) {
  if (bytes.length < 80 || bytes.subarray(0, 7).toString('ascii') !== 'PMTiles' || bytes.readUInt8(7) !== 3) {
    die('Initial bounded PMTiles response does not contain a valid v3 header');
  }
  const offsetBig = bytes.readBigUInt64LE(56);
  const lengthBig = bytes.readBigUInt64LE(64);
  if (offsetBig > BigInt(Number.MAX_SAFE_INTEGER) || lengthBig > BigInt(Number.MAX_SAFE_INTEGER)) {
    die('PMTiles v3 tile data region exceeds safe integer bounds');
  }
  const offset = Number(offsetBig);
  const length = Number(lengthBig);
  if (length <= 0 || offset + length > plannedSize) die('PMTiles v3 tile data region is empty or outside planned object size');
  return { tile_data_offset: offset, tile_data_length: length, tile_data_end_exclusive: offset + length };
}

function pmtilesTileDataRangeEvidence(url, requests) {
  const headers = requests.filter(request => request.url === url && request.pmtiles_v3_header && request.status_check === 'passed');
  const header = headers[0]?.pmtiles_v3_header;
  if (!header) return { passed: false, reason: 'verified v3 header range unavailable' };
  const dataRanges = requests.filter(request => {
    if (request.url !== url || request.method !== 'GET' || request.status_check !== 'passed' || !request.request_range) return false;
    const range = parseSingleByteRange(request.request_range, request.planned_size_bytes);
    return range.start < header.tile_data_end_exclusive && range.end + 1 > header.tile_data_offset;
  });
  return { passed: dataRanges.length > 0, header, tile_data_range_requests: dataRanges.map(request => request.request_range) };
}

function validateSourceResponseBeforeBody(request, response, object, footerException = null) {
  if (request.method() === 'HEAD') {
    validateHeadMetadata(request, response, object);
    return;
  }
  if (request.method() !== 'GET') return;
  const headers = response.headers();
  const rangeText = request.headers()['range'] || null;
  const contentLengthText = headers['content-length'];
  const contentLength = contentLengthText === undefined ? null : Number(contentLengthText);
  if (contentLength === null || !Number.isSafeInteger(contentLength) || contentLength < 0) {
    die(`Source response lacks a bounded valid Content-Length: ${request.url()}`);
  }
  if (rangeText) {
    const requested = parseSingleByteRange(rangeText, object.size_bytes);
    if (requested.length > (footerException ? FOOTER_PREFIX_LIMIT : criteriaSourceRangeMax)) {
      die(`Response range exceeds the frozen maximum: ${request.url()}`);
    }
    if (response.status() !== 206) die(`Ranged Source GET returned ${response.status()}; body was not read: ${request.url()}`);
    const actual = parseContentRange(headers['content-range']);
    if (actual.start !== requested.start || actual.end !== requested.end || actual.total !== object.size_bytes || contentLength !== requested.length) {
      die(`Source range headers do not match the bounded request; body was not read: ${request.url()}`);
    }
    return;
  }
  if (isDataObject(object)) die(`Full GET of analytical/PMTiles object is forbidden; body was not read: ${request.url()}`);
  if (response.status() !== 200 || contentLength > 524288 || object.size_bytes > 524288) {
    die(`Full Source metadata response exceeds the bounded allowlist; body was not read: ${request.url()}`);
  }
}

async function browserIdentity() {
  const response = await fetch(BROWSER_ORIGIN, { redirect: 'error' });
  if (!response.ok) die(`Portolan Browser entry returned HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const html = bytes.toString('utf8');
  const indexSha = sha256(bytes);
  if (criteriaBrowserIndexSha && indexSha !== criteriaBrowserIndexSha) {
    die(`Portolan Browser index.html differs from frozen SHA-256: ${indexSha}`);
  }
  const match = /<script[^>]+type="module"[^>]+src="([^"]+)"/.exec(html);
  if (!match) die('Could not identify the Portolan Browser module entry from index.html');
  const entry = new URL(match[1], BROWSER_ORIGIN).href;
  const expected = new URL(criteriaEntryScript, BROWSER_ORIGIN).href;
  if (entry !== expected) die(`Portolan Browser entry script changed; expected ${expected}, received ${entry}`);
  const scriptResponse = await fetch(entry, { redirect: 'error' });
  if (!scriptResponse.ok) die(`Portolan Browser entry script returned HTTP ${scriptResponse.status}`);
  const scriptBytes = Buffer.from(await scriptResponse.arrayBuffer());
  if (scriptBytes.length > 10 * 1024 * 1024) die('Portolan Browser entry script exceeds 10 MiB');
  return { index_url: BROWSER_ORIGIN + '/', index_sha256: indexSha, index_bytes: bytes.length,
    entry_script_url: entry, entry_script_bytes: scriptBytes.length, entry_script_sha256: sha256(scriptBytes),
    expected_source_commit: criteriaSourceCommit };
}

let criteriaEntryScript;
let criteriaSourceCommit;
let criteriaBrowserIndexSha;
let criteriaSourceRangeMax;

async function run(args, criteria, criteriaSha) {
  criteriaEntryScript = criteria.browser.expected_entry_script;
  criteriaSourceCommit = criteria.browser.source_commit;
  criteriaBrowserIndexSha = criteria.browser.expected_index_html_sha256;
  criteriaSourceRangeMax = criteria.source_objects.maximum_range_bytes;
  if (Boolean(args['metadata-policy']) !== Boolean(args['metadata-policy-sha256'])) {
    die('Footer metadata policy requires both --metadata-policy and --metadata-policy-sha256');
  }
  const input = await loadInputs(args, criteria);
  let footerPolicy = null;
  let footerPolicyPath = null;
  let footerPolicySha = null;
  if (args['metadata-policy']) {
    if (!/^[0-9a-f]{64}$/.test(args['metadata-policy-sha256'])) die('Footer metadata policy SHA-256 must be lowercase hex');
    footerPolicyPath = path.resolve(args['metadata-policy']);
    const loaded = await readJson(footerPolicyPath, 'official Browser footer metadata policy');
    footerPolicySha = sha256(loaded.bytes);
    if (footerPolicySha !== args['metadata-policy-sha256']) die('Footer metadata policy differs from its explicit SHA-256 pin');
    const proof = await readJson(FROZEN_FOOTER_PROOF_PATH, 'independent local Parquet footer proof');
    footerPolicy = validatePortolanFooterPolicy(loaded.value, {
      criteriaSha, sourcePlanSha: input.sourcePlanSha, pagesPlanSha: input.planSha,
      objects: input.sourceObjects, footerProof: proof.value, footerProofSha: sha256(proof.bytes),
      ordinaryRangeMax: criteriaSourceRangeMax,
    });
  }
  const footerGuard = createPortolanFooterGuard(footerPolicy, criteriaSourceRangeMax);
  const followupCriteria = await readJson(HEAD_RENDER_CRITERIA_PATH, 'HEAD/render follow-up criteria');
  if (followupCriteria.value.kind !== 'official_browser_protocol_followup') die('HEAD/render follow-up criteria kind is unexpected');
  const navigationFollowupCriteria = await readJson(NAVIGATION_FOLLOWUP_CRITERIA_PATH, 'collection navigation follow-up criteria');
  validateNavigationFollowupCriteria(navigationFollowupCriteria.value);
  const navigationTraceCriteria = input.selectedIds.includes('lakeatlas')
    ? await readJson(NAVIGATION_TRACE_CRITERIA_PATH, 'LakeATLAS navigation trace criteria') : null;
  if (navigationTraceCriteria && (navigationTraceCriteria.value.schema_version !== 1 ||
      navigationTraceCriteria.value.required_trace?.length !== 3 ||
      !/^[0-9a-f]{64}$/.test(navigationTraceCriteria.value.failed_report_sha256 || ''))) {
    die('LakeATLAS navigation trace criteria do not match the frozen logging scope');
  }
  const cardReadinessPath = path.join(ROOT, 'research/source-publication-20261107/pages/five-collections-r2/card-readiness-criteria-r2.json');
  const cardReadiness = await readJson(cardReadinessPath, 'card readiness criteria');
  if (cardReadiness.value.fixed_readiness?.unchanged_card_title_href_signature_ms !== 500 ||
      cardReadiness.value.fixed_readiness?.maximum_wait_ms !== 30000) die('Card readiness criteria differ');
  let renderDiagnosticCriteria = null;
  if (args.diagnoseRender) {
    if (JSON.stringify(args.datasets || []) !== JSON.stringify(['river-plastic-inputs']) ||
        JSON.stringify(input.selectedIds) !== JSON.stringify(['river-plastic-inputs'])) {
      die('--diagnose-render requires exactly --dataset river-plastic-inputs');
    }
    renderDiagnosticCriteria = await readJson(RIVER_RENDER_DIAGNOSTIC_PATH, 'River render diagnostic criteria');
    if (renderDiagnosticCriteria.value.kind !== 'river_map_render_diagnostic' ||
        renderDiagnosticCriteria.value.dataset_id !== 'river-plastic-inputs' ||
        renderDiagnosticCriteria.value.zoom_in_clicks !== 3 ||
        renderDiagnosticCriteria.value.overlay_title !== 'River input display tiles' ||
        renderDiagnosticCriteria.value.frozen_before_viewer_run !== true) {
      die('River render diagnostic criteria do not match the frozen bounded protocol');
    }
  }
  let rendererInspectionCriteria = null;
  if (args.inspectRenderer) {
    if (args.diagnoseRender || JSON.stringify(args.datasets || []) !== JSON.stringify(['river-plastic-inputs']) ||
        JSON.stringify(input.selectedIds) !== JSON.stringify(['river-plastic-inputs'])) {
      die('--inspect-renderer requires exactly --dataset river-plastic-inputs and cannot be combined with --diagnose-render');
    }
    rendererInspectionCriteria = await readJson(RIVER_RENDERER_INSPECTION_PATH, 'River renderer inspection criteria');
    validateRendererInspectionCriteria(rendererInspectionCriteria.value);
  }
  const report = {
    schema_version: 1,
    status: input.partial ? 'partial' : 'running',
    checked_at: new Date().toISOString(),
    mode: input.mode,
    scope: args.inspectRenderer ? 'Read-only developer renderer diagnostic only; NOT publication acceptance' :
      input.mode === 'preflight' ? 'Official remote Browser + local staged Pages metadata + live Source objects' : 'Official remote Browser + live deployed Pages metadata + live Source objects',
    preflight_metadata_interception_is_hosting_evidence: false,
    pages_plan_sha256: input.planSha,
    source_plan_sha256: input.sourcePlanSha,
    metadata_range_policy: footerPolicy ? { path: path.relative(ROOT, footerPolicyPath), sha256: footerPolicySha,
      collection_id: footerPolicy.collection_id, object_url: footerPolicy.object_url,
      range: footerPolicy.range, range_sha256: footerPolicy.range_sha256,
      capture_configuration: { protocol: 'Chrome DevTools Network', max_resource_buffer_bytes: CAPTURE_RESOURCE_BYTES,
        max_total_buffer_bytes: CAPTURE_TOTAL_BYTES },
      approved_exception_requests: 0, verified_exception_responses: 0 } : null,
    head_render_followup_criteria: { path: path.relative(ROOT, HEAD_RENDER_CRITERIA_PATH), sha256: sha256(followupCriteria.bytes) },
    navigation_followup_criteria: { path: path.relative(ROOT, NAVIGATION_FOLLOWUP_CRITERIA_PATH),
      sha256: sha256(navigationFollowupCriteria.bytes), status: 'frozen_protocol_applied' },
    card_readiness_criteria: { path: path.relative(ROOT, cardReadinessPath), sha256: sha256(cardReadiness.bytes) },
    navigation_trace_criteria: navigationTraceCriteria ? { path: path.relative(ROOT, NAVIGATION_TRACE_CRITERIA_PATH),
      sha256: sha256(navigationTraceCriteria.bytes), status: 'logging_only' } : null,
    render_diagnostic: renderDiagnosticCriteria ? { path: path.relative(ROOT, RIVER_RENDER_DIAGNOSTIC_PATH),
      sha256: sha256(renderDiagnosticCriteria.bytes), status: 'pending' } : null,
    renderer_diagnostic: rendererInspectionCriteria ? { path: path.relative(ROOT, RIVER_RENDERER_INSPECTION_PATH),
      sha256: sha256(rendererInspectionCriteria.bytes), mode: rendererInspectionCriteria.value.scope.mode,
      acceptance_gate: 'not_evaluated', status: 'pending' } : null,
    browser: null,
    aggregate: { expected_ids: REQUIRED_COLLECTIONS, staged_ids: input.presentIds,
      missing_ids: input.missingIds, selected_ids: input.selectedIds,
      expected_pmtiles_count: criteria.aggregate.expected_pmtiles_count,
      observed_pmtiles_count: [...input.collections.values()].reduce((sum, c) => sum + c.pmtiles.length, 0) },
    pages_metadata: { source: input.mode === 'preflight' ? 'locally fulfilled from exact publish-plan files' : 'live GitHub Pages GETs; no interception',
      expected_urls: [], observed: [], intercepted: [] },
    source_requests: [],
    collections: [],
    limits: { max_range_bytes: criteria.source_objects.maximum_range_bytes,
      max_bytes_per_collection: criteria.source_objects.maximum_transferred_bytes_per_collection,
      max_bytes_full_run: criteria.source_objects.maximum_transferred_bytes_full_run },
    manual_visual_review_required: true,
    notes: [
      'Preflight synthetic metadata is not GitHub Pages reachability, deployment, or real Pages CORS evidence.',
      'Source range-body SHA-256 values identify only those bounded response bytes, not a full-object checksum.',
      'A map canvas and screenshot require manual visual review before claiming rendered layer acceptance.',
      ...(args.inspectRenderer ? ['Renderer introspection is read-only developer evidence; acceptance status is explicitly not evaluated.'] : [])
    ],
    errors: []
  };
  if (input.partial && !args.datasets?.length) {
    report.status = 'not_ready';
    report.errors.push(`Staged catalog is missing required collections: ${input.missingIds.join(', ')}`);
    await writeFile(path.join(input.out, 'portolan-browser-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(`not_ready: staged catalog lacks required collections; report ${path.join(input.out, 'portolan-browser-report.json')}`);
    return 2;
  }
  try {
    report.browser = await browserIdentity();
  } catch (error) {
    report.status = 'failed';
    report.errors.push(error.message);
    await writeFile(path.join(input.out, 'portolan-browser-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(`failed: ${path.join(input.out, 'portolan-browser-report.json')}`);
    return 1;
  }

  const pageResponses = new Map();
  const requiredPageUrls = new Set([input.pageRootUrl]);
  for (const id of input.selectedIds) {
    const collection = input.collections.get(id);
    requiredPageUrls.add(collection.url);
    for (const style of collection.styles) requiredPageUrls.add(style.url);
  }
  report.pages_metadata.expected_urls = [...requiredPageUrls].sort();

  const objectByUrl = input.sourceObjects;
  const transferredFullRun = { value: 0 };
  const reservedFullRun = { value: 0 };
  const pending = new Set();
  let browser;
  try {
    const { chromium } = await import('playwright-core');
    browser = await chromium.launch({ executablePath: args.chrome || DEFAULT_CHROME, headless: true,
      args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--disable-background-networking', '--no-first-run'] });
  } catch (error) {
    report.status = 'failed';
    report.errors.push(error.message);
    await writeFile(path.join(input.out, 'portolan-browser-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(`failed: ${path.join(input.out, 'portolan-browser-report.json')}`);
    return 1;
  }
  try {
    for (const datasetId of input.selectedIds) {
      const collection = input.collections.get(datasetId);
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
      const page = await context.newPage();
      let footerCapture = null;
      if (footerPolicy && datasetId === footerPolicy.collection_id) {
        const cdpSession = await context.newCDPSession(page);
        footerCapture = new PortolanFooterCdpCapture(cdpSession, footerPolicy);
        await footerCapture.start();
      }
      const caseReport = { id: datasetId, collection_title: collection.title, collection_page: collection.url,
        collection_page_path: collection.pagePath, status: 'running', pmtiles_layers: collection.pmtiles,
        navigation: null,
        style_titles: collection.styles.map(s => s.title), style_picker_options: [], style_picker_options_observed: [], map_ready: false,
        map_selector: '.map-container .map', canvas_selector: '.maplibregl-canvas',
        layer_control_text: null, layer_control: null, console_messages: [], console_messages_truncated: 0,
        renderer_state: null, screenshots: [], transferred_bytes: 0, source_request_indexes: [], errors: [] };
      report.collections.push(caseReport);
      const localReserved = { value: 0 };
      const localTransferred = { value: 0 };
      let caseFatal = false;
      const sourceRequestRecords = new WeakMap();
      const rangeExceptions = new WeakMap();
      const casePageRequests = new Set();
      const casePageResponses = new Set();
      const sourceActivity = { inFlight: new Set(), lastActivity: Date.now() };
      const failCase = async error => {
        if (!caseFatal) {
          caseFatal = true;
          caseReport.errors.push(error.message);
          report.errors.push(`${datasetId}: ${error.message}`);
        }
        await context.close().catch(() => {});
      };
      const pageExpected = new Map([...input.pageFiles.values()].map(item => [item.url, item]));

      if (input.mode === 'preflight') {
        await context.route(url => {
          try { return new URL(String(url)).origin === new URL(PAGE_BASE).origin; } catch { return false; }
        }, async route => {
          const url = route.request().url();
          const allowed = pageExpected.get(url);
          if (!allowed) {
            const message = `Preflight attempted an unapproved Pages URL: ${url}`;
            caseReport.errors.push(message); report.errors.push(message);
            await route.abort('blockedbyclient');
            return;
          }
          if (route.request().method() !== 'GET') {
            const message = `Preflight Pages request must be GET: ${route.request().method()} ${url}`;
            caseReport.errors.push(message); report.errors.push(message);
            await route.abort('blockedbyclient');
            return;
          }
          report.pages_metadata.intercepted.push({ url, plan_path: allowed.path,
            expected_size_bytes: allowed.size_bytes, expected_sha256: allowed.sha256,
            fulfilled_size_bytes: allowed.bytes.length, fulfilled_sha256: sha256(allowed.bytes) });
          await route.fulfill({ status: 200, body: allowed.bytes,
            headers: { 'content-type': allowed.content_type, 'access-control-allow-origin': '*',
              'cache-control': 'no-store', 'content-length': String(allowed.size_bytes) } });
        });
      }

      await context.route(url => {
        try { return new URL(String(url)).origin === SOURCE_ORIGIN; } catch { return false; }
      }, async route => {
        const request = route.request();
        const url = request.url();
        const object = objectByUrl.get(url);
        if (!object) {
          const message = `Off-plan Source Cooperative request: ${request.method()} ${url}`;
          caseReport.errors.push(message); report.errors.push(message);
          await route.abort('blockedbyclient');
          return;
        }
        const productPrefix = input.prefixes.get(object.dataset_id);
        if (object.dataset_id !== datasetId || !isExactProductObject(url, objectByUrl, productPrefix)) {
          const message = `Cross-product Source request: ${url}`;
          caseReport.errors.push(message); report.errors.push(message);
          await route.abort('blockedbyclient');
          return;
        }
        if (request.method() === 'OPTIONS' || request.method() === 'HEAD') return route.continue();
        if (request.method() !== 'GET') {
          const message = `Unexpected Source method: ${request.method()} ${url}`;
          caseReport.errors.push(message); report.errors.push(message);
          await route.abort('blockedbyclient');
          return;
        }
        const rangeText = request.headers()['range'] || null;
        let reserved;
        try {
          if (rangeText) {
            const authorization = footerGuard.authorize({ collectionId: datasetId, url, range: rangeText, object });
            reserved = authorization.length;
            if (authorization.exception) {
              rangeExceptions.set(request, authorization.exception);
              report.metadata_range_policy.approved_exception_requests = footerGuard.counts().requested;
            }
          } else {
            if (isDataObject(object)) die(`Full GET of analytical/PMTiles object is forbidden: ${url}`);
            const extension = path.posix.extname(new URL(url).pathname).toLowerCase();
            if (!SMALL_METADATA_EXTENSIONS.has(extension) || object.size_bytes > criteria.source_objects.maximum_full_get_bytes_for_planned_metadata_only) {
              die(`Full GET is permitted only for small planned metadata: ${url}`);
            }
            reserved = object.size_bytes;
          }
          if (localReserved.value + reserved > criteria.source_objects.maximum_transferred_bytes_per_collection ||
              reservedFullRun.value + reserved > criteria.source_objects.maximum_transferred_bytes_full_run) {
            die(`Pre-request Source transfer budget exceeded for ${datasetId}`);
          }
          localReserved.value += reserved;
          reservedFullRun.value += reserved;
        } catch (error) {
          const message = error.message;
          caseReport.errors.push(message); report.errors.push(message);
          await route.abort('blockedbyclient');
          return;
        }
        await route.continue();
      });

      page.on('pageerror', error => {
        caseReport.errors.push(error.message); report.errors.push(`${datasetId}: ${error.message}`);
      });
      page.on('console', message => {
        if (caseReport.console_messages.length < 200) {
          caseReport.console_messages.push({ type: message.type(), text: message.text() });
        } else {
          caseReport.console_messages_truncated += 1;
        }
        if (message.type() === 'error') {
          const failure = `console.error: ${message.text()}`;
          caseReport.errors.push(failure); report.errors.push(`${datasetId}: ${failure}`);
        }
      });
      page.on('requestfailed', request => {
        const failure = `${request.method()} ${request.url()}: ${request.failure()?.errorText || 'unknown'}`;
        if (new URL(request.url()).origin === SOURCE_ORIGIN) {
          sourceActivity.inFlight.delete(request);
          sourceActivity.lastActivity = Date.now();
          const record = sourceRequestRecords.get(request);
          if (record) {
            const reason = request.failure()?.errorText || 'unknown';
            record.failure = reason;
            if (request.method() === 'HEAD' && reason === 'net::ERR_ABORTED') {
              if (!classifyHeadAbortAfterVerifiedHeaders(record, reason)) {
                if (record.head_metadata_verified) {
                  caseReport.errors.push(failure); report.errors.push(`${datasetId}: ${failure}`);
                  record.status_check = 'request_failed';
                } else {
                  record.status_check = 'head_abort_pending_header_validation';
                }
              }
            } else {
              record.status_check = 'request_failed';
              caseReport.errors.push(failure); report.errors.push(`${datasetId}: ${failure}`);
            }
          } else {
            caseReport.errors.push(failure); report.errors.push(`${datasetId}: ${failure}`);
          }
        } else if (new URL(request.url()).origin === new URL(PAGE_BASE).origin) {
          caseReport.errors.push(failure); report.errors.push(`${datasetId}: ${failure}`);
        }
      });
      page.on('request', request => {
        if (request.url().startsWith(PAGE_BASE)) casePageRequests.add(request.url());
        if (new URL(request.url()).origin !== SOURCE_ORIGIN) return;
        sourceActivity.inFlight.add(request);
        sourceActivity.lastActivity = Date.now();
        const object = objectByUrl.get(request.url());
        const record = { url: request.url(), dataset_id: object?.dataset_id || null, method: request.method(),
          status: null, request_range: request.headers()['range'] || null, planned_size_bytes: object?.size_bytes ?? null,
          planned_sha256: object?.sha256 ?? null, response_body_bytes: 0, status_check: 'pending' };
        const index = report.source_requests.push(record) - 1;
        sourceRequestRecords.set(request, record);
        caseReport.source_request_indexes.push(index);
      });
      page.on('requestfinished', request => {
        if (new URL(request.url()).origin !== SOURCE_ORIGIN) return;
        sourceActivity.inFlight.delete(request);
        sourceActivity.lastActivity = Date.now();
      });
      page.on('response', response => {
        const task = (async () => {
          const request = response.request();
          const url = response.url();
          if (url.startsWith(PAGE_BASE)) {
            const item = pageExpected.get(url);
            if (!item) die(`Observed off-plan Pages response: ${url}`);
            const pageLength = Number(response.headers()['content-length']);
            if (!Number.isSafeInteger(pageLength) || pageLength < 0 || pageLength > PAGE_FILE_LIMIT) {
              die(`Pages metadata response lacks a bounded Content-Length; body was not read: ${url}`);
            }
            const body = await response.body();
            const record = { url, plan_path: item.path, method: request.method(), status: response.status(),
              body_bytes: body.length, expected_sha256: item.sha256, observed_sha256: sha256(body),
              source: input.mode === 'preflight' ? 'locally_fulfilled' : 'live_pages' };
            if (record.status !== 200 || body.length !== item.size_bytes || record.observed_sha256 !== item.sha256) {
              die(`Pages metadata response differs from staged plan: ${url}`);
            }
            pageResponses.set(url, record);
            casePageResponses.add(url);
            report.pages_metadata.observed.push(record);
            return;
          }
          if (new URL(url).origin === SOURCE_ORIGIN) {
            const object = objectByUrl.get(request.url());
            if (!object) die(`Response from off-plan Source object: ${request.url()}`);
            if (url !== request.url()) die(`Source redirect changed object URL: ${request.url()} -> ${url}`);
            const requestRecord = sourceRequestRecords.get(request);
            if (!requestRecord) die(`Source response has no matching request record: ${request.url()}`);
            const responseHeaders = response.headers();
            Object.assign(requestRecord, { status: response.status(),
              response_content_type: responseHeaders['content-type'] || null,
              response_content_length: responseHeaders['content-length'] === undefined ? null : Number(responseHeaders['content-length']),
              accept_ranges: responseHeaders['accept-ranges'] || null,
              content_range: responseHeaders['content-range'] || null,
              access_control_allow_origin: responseHeaders['access-control-allow-origin'] || null,
              access_control_expose_headers: responseHeaders['access-control-expose-headers'] || null });
            const footerException = rangeExceptions.get(request) || null;
            validateSourceResponseBeforeBody(request, response, object, footerException);
            const captured = footerException ? await footerCapture.bodyFor({ collectionId: datasetId,
              url: request.url(), range: request.headers()['range'] }) : null;
            const body = request.method() === 'GET' ? captured?.body || await response.body() : Buffer.alloc(0);
            const record = sourceResponseRecord(request, response, object, body);
            if (footerException) {
              record.metadata_range_capture = captured.evidence;
              record.metadata_range_exception = footerGuard.verify({ collectionId: datasetId,
                url: request.url(), range: request.headers()['range'], object, body, exception: footerException });
              report.metadata_range_policy.verified_exception_responses = footerGuard.counts().verified;
            }
            Object.assign(requestRecord, record);
            if (request.method() === 'HEAD' && requestRecord.failure) {
              if (!classifyHeadAbortAfterVerifiedHeaders(requestRecord, requestRecord.failure)) {
                die(`HEAD cancellation occurred before planned metadata was verified: ${request.url()}`);
              }
            }
            if (path.posix.extname(new URL(request.url()).pathname).toLowerCase() === '.pmtiles' && request.method() === 'GET') {
              const range = requestRecord.request_range ? parseSingleByteRange(requestRecord.request_range, object.size_bytes) : null;
              if (range?.start === 0) requestRecord.pmtiles_v3_header = parsePmtilesV3TileDataRegion(body, object.size_bytes);
            }
            localTransferred.value += body.length;
            transferredFullRun.value += body.length;
            caseReport.transferred_bytes = localTransferred.value;
            report.source_transferred_bytes = transferredFullRun.value;
            if (localTransferred.value > criteria.source_objects.maximum_transferred_bytes_per_collection ||
                transferredFullRun.value > criteria.source_objects.maximum_transferred_bytes_full_run) {
              die('Observed Source body bytes exceeded frozen transfer budget');
            }
          }
        })().catch(error => {
          if (new URL(response.url()).origin === SOURCE_ORIGIN) {
            const requestRecord = sourceRequestRecords.get(response.request());
            if (requestRecord) {
              requestRecord.status = response.status();
              requestRecord.status_check = 'failed_validation';
              requestRecord.validation_error = error.message;
              requestRecord.response_body_bytes = 0;
            }
          }
          return failCase(error);
        });
        pending.add(task);
        task.finally(() => pending.delete(task));
      });

      const rootBrowserUrl = externalCollectionBrowserUrl(criteria.browser, input.pageRootUrl);
      const expectedCollectionBrowserUrl = externalCollectionBrowserUrl(criteria.browser, collection.url);
      caseReport.browser_route = rootBrowserUrl;
      caseReport.navigation = { expected_catalog_route: rootBrowserUrl, catalog_route_matched: false,
        expected_collection_route: expectedCollectionBrowserUrl,
        before_activation_url: null, selected_link: null, focused: false, activation: null,
        after_activation_url: null, route_matched: false, title_visible: false, failure: null };
      try {
        await page.goto(rootBrowserUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForURL(url => url.href === rootBrowserUrl, { timeout: 30000 });
      } catch (error) {
        caseReport.navigation.after_activation_url = (() => { try { return page.url(); } catch { return null; } })();
        caseReport.navigation.failure = error.message;
        throw error;
      }
      caseReport.navigation.catalog_route_matched = true;
      if (datasetId === 'lakeatlas') {
        await installNavigationTrace(page);
        caseReport.navigation.trace = { records: [], truncated_records: 0 };
      }
      await page.locator('.loading').waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
      await page.locator('main, .browse, .catalog').first().waitFor({ state: 'visible', timeout: 30000 });
      const rootLinks = page.locator('.catalog-card .stac-link');
      const rootChild = rootLinks.filter({ has: page.getByText(collection.title, { exact: true }) });
      let validatedAnchorHandle = null;
      try {
        await rootChild.waitFor({ state: 'visible', timeout: 30000 });
        await rootChild.evaluate(element => element.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
        // Visible cards load metadata lazily. Wait for the target and any queued
        // child responses, then a settled card list, before taking a node handle.
        const readinessStarted = Date.now();
        let signature = null, signatureSince = Date.now(), ready = false;
        let readinessSnapshot = null;
        while (Date.now() - readinessStarted < 30000) {
          const cards = await rootLinks.evaluateAll(elements => elements.map(element => ({
            title: element.querySelector('.title')?.textContent?.trim() || null,
            href: element.href,
          })));
          const currentSignature = JSON.stringify(cards);
          const children = REQUIRED_COLLECTIONS.map(id => ({ id, url: input.collections.get(id).url,
            requested: casePageRequests.has(input.collections.get(id).url),
            completed: casePageResponses.has(input.collections.get(id).url) }));
          const pending = children.filter(child => child.requested && !child.completed);
          if (signature !== currentSignature || pending.length || !casePageResponses.has(collection.url)) {
            signature = currentSignature; signatureSince = Date.now();
          }
          readinessSnapshot = { target_metadata_verified: casePageResponses.has(collection.url),
            children, pending_count: pending.length, stable_for_ms: Date.now() - signatureSince,
            elapsed_ms: Date.now() - readinessStarted };
          if (readinessSnapshot.target_metadata_verified && !pending.length && readinessSnapshot.stable_for_ms >= 500) {
            ready = true; break;
          }
          await page.waitForTimeout(50);
        }
        caseReport.navigation.card_readiness = readinessSnapshot;
        if (!ready) die('Target card metadata and link list did not settle before activation');
        const activationAnchor = await rootChild.elementHandle();
        if (!activationAnchor) die('Ready collection anchor is missing');
        await activationAnchor.waitForElementState('stable', { timeout: 30000 });
        const exactTitleLinkCount = await rootChild.count();
        const rootLinkRecords = await rootLinks.evaluateAll(elements => elements.map(element => ({
          tag_name: element.tagName.toLowerCase(),
          title_text: element.querySelector('.title')?.textContent?.trim() || null,
          text_content: element.textContent?.trim() || null,
          raw_href: element.getAttribute('href'), href: element.href,
          visible: Boolean(element.getClientRects().length),
        })));
        caseReport.navigation.visible_title_links = rootLinkRecords.filter(link => link.visible);
        const titleMatches = rootLinkRecords.filter(link => link.title_text === collection.title);
        if (exactTitleLinkCount !== 1 || titleMatches.length !== 1) {
          die(`Expected one exact collection title link; locator=${exactTitleLinkCount}, DOM=${titleMatches.length}`);
        }
        const selectedLink = await activationAnchor.evaluate(element => ({
          tag_name: element.tagName.toLowerCase(),
          title_text: element.querySelector('.title')?.textContent?.trim() || null,
          text_content: element.textContent?.trim() || null,
          raw_href: element.getAttribute('href'), href: element.href,
          visible: Boolean(element.getClientRects().length),
        }));
        caseReport.navigation.selected_link = selectedLink;
        validateCollectionChildLink(selectedLink, collection.title, expectedCollectionBrowserUrl);
        if (datasetId === 'lakeatlas') {
          validatedAnchorHandle = activationAnchor;
          const beforeFocus = await readNavigationTrace(page, validatedAnchorHandle);
          caseReport.navigation.validated_anchor_before_focus = beforeFocus.validated_anchor;
          caseReport.navigation.trace = beforeFocus.trace;
        }
        caseReport.navigation.before_activation_url = page.url();
        await activationAnchor.focus();
        caseReport.navigation.focused = await activationAnchor.evaluate(element => element.isConnected && document.activeElement === element);
        if (!caseReport.navigation.focused) die('Exact child link did not receive keyboard focus');
        if (datasetId === 'lakeatlas') {
          const beforePress = await readNavigationTrace(page, validatedAnchorHandle);
          caseReport.navigation.validated_anchor_before_press = beforePress.validated_anchor;
          caseReport.navigation.trace = beforePress.trace;
          const children = REQUIRED_COLLECTIONS.map(id => ({ id, url: input.collections.get(id).url,
            requested: casePageRequests.has(input.collections.get(id).url),
            completed: casePageResponses.has(input.collections.get(id).url) }));
          caseReport.navigation.child_metadata_before_activation = {
            children, completed_count: children.filter(child => child.completed).length,
            pending_count: children.filter(child => child.requested && !child.completed).length };
        }
        const activationHref = await activationAnchor.evaluate(element => element.isConnected ? element.href : null);
        if (activationHref !== expectedCollectionBrowserUrl) die('Validated activation node changed or detached');
        caseReport.navigation.activation = 'Enter';
        await activationAnchor.press('Enter');
        if (datasetId === 'lakeatlas') {
          const afterPress = await readNavigationTrace(page, validatedAnchorHandle);
          caseReport.navigation.validated_anchor_after_press = afterPress.validated_anchor;
          caseReport.navigation.trace = afterPress.trace;
        }
        await page.waitForURL(url => url.href === expectedCollectionBrowserUrl, { timeout: 30000 });
        caseReport.navigation.after_activation_url = page.url();
        caseReport.navigation.route_matched = true;
        if (datasetId === 'lakeatlas') {
          const finalTrace = await readNavigationTrace(page, validatedAnchorHandle);
          caseReport.navigation.validated_anchor_final = finalTrace.validated_anchor;
          caseReport.navigation.trace = finalTrace.trace;
        }
      } catch (error) {
        if (datasetId === 'lakeatlas') {
          const finalTrace = await readNavigationTrace(page, validatedAnchorHandle);
          caseReport.navigation.validated_anchor_final = finalTrace.validated_anchor;
          if (finalTrace.trace && !finalTrace.trace.read_error) caseReport.navigation.trace = finalTrace.trace;
        }
        caseReport.navigation.after_activation_url = (() => { try { return page.url(); } catch { return null; } })();
        caseReport.navigation.failure = error.message;
        if (!caseReport.navigation.visible_title_links) {
          caseReport.navigation.visible_title_links = await page.locator('.catalog-card .stac-link').evaluateAll(elements => elements
            .filter(element => element.getClientRects().length).slice(0, 10).map(element => ({
              tag_name: element.tagName.toLowerCase(), title_text: element.querySelector('.title')?.textContent?.trim() || null,
              text_content: element.textContent?.trim() || null, raw_href: element.getAttribute('href'), href: element.href,
            }))).catch(() => []);
        }
        caseReport.navigation.visible_headings = await page.locator('h1, h2, h3, [role="heading"]').evaluateAll(elements => elements
          .filter(element => element.getClientRects().length).slice(0, 10).map(element => element.textContent?.trim() || null))
          .catch(() => []);
        throw error;
      }
      await page.locator('.loading').waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
      await page.getByText(collection.title, { exact: true }).first().waitFor({ state: 'visible', timeout: 30000 });
      caseReport.navigation.title_visible = true;
      const map = page.locator('.map-container .map');
      await map.waitFor({ state: 'visible', timeout: 30000 });
      await map.locator('.maplibregl-canvas').waitFor({ state: 'visible', timeout: 30000 });
      await map.locator('.maplibregl-ctrl-zoom-in').waitFor({ state: 'visible', timeout: 30000 });
      caseReport.map_ready = true;

      const layerButton = page.locator(criteria.ui.layer_control_button);
      await layerButton.waitFor({ state: 'visible', timeout: 10000 });
      await layerButton.click();
      const layerPanel = page.locator(criteria.ui.layer_control_panel);
      await layerPanel.waitFor({ state: 'visible', timeout: 10000 });
      caseReport.layer_control_text = await layerPanel.innerText();
      caseReport.layer_control = await layerPanel.locator('input[type="checkbox"], [role="checkbox"]').evaluateAll(elements =>
        elements.map(element => ({
          tag: element.tagName.toLowerCase(),
          role: element.getAttribute('role'),
          label: element.getAttribute('aria-label') || element.labels?.[0]?.textContent?.trim() ||
            element.closest('label')?.textContent?.trim() || null,
          checked: element instanceof HTMLInputElement ? element.checked : element.getAttribute('aria-checked'),
          disabled: element instanceof HTMLInputElement ? element.disabled : element.getAttribute('aria-disabled'),
        })));
      await layerButton.click();
      const styleOrder = [...collection.styles].sort((a, b) => Number(b.is_default) - Number(a.is_default));
      const picker = map.locator(criteria.ui.style_picker);
      let selectableStyles = styleOrder.map(style => ({ ...style, ui_option_value: null, ui_option_text: null, ui_label_basis: null }));
      if (collection.styles.length > 1) {
        await picker.waitFor({ state: 'visible', timeout: 10000 });
        const optionRecords = await picker.locator('option').evaluateAll(options => options.map(option => ({
          value: option.value,
          text: (option.textContent || '').trim(),
        })));
        caseReport.style_picker_options_observed = optionRecords;
        selectableStyles = bindStylePickerOptions(styleOrder, optionRecords);
        caseReport.style_picker_options = selectableStyles.map(style => ({ style_key: style.key, style_url: style.url,
          style_asset_title: style.title, style_json_name: style.style_json_name,
          expected_ui_title: style.ui_expected_title, option_value: style.ui_option_value,
          option_text: style.ui_option_text, label_match_basis: style.ui_label_basis }));
      }
      for (const [styleIndex, style] of selectableStyles.entries()) {
        if (styleIndex > 0 || !style.is_default) {
          if (collection.styles.length > 1) await picker.selectOption({ value: style.ui_option_value });
        }
        await map.locator('.maplibregl-canvas').waitFor({ state: 'visible', timeout: 30000 });
        await waitUntil(page, () => pageResponses.has(style.url), `Browser did not load style ${style.url}`);
        for (const url of style.pmtiles_urls) {
          await waitUntil(page,
            () => report.source_requests.some(item => item.url === url && item.status_check === 'passed' && item.request_range),
            `No verified bounded PMTiles range request observed for ${datasetId}/${style.key}: ${url}`);
          await waitUntil(page,
            () => pmtilesTileDataRangeEvidence(url, report.source_requests).passed,
            `No verified PMTiles v3 tile-data range observed for ${datasetId}/${style.key}: ${url}`);
        }
        await waitForSourceQuiet(page, sourceActivity);
        while (pending.size) await Promise.all([...pending]);
        for (const index of caseReport.source_request_indexes) {
          const request = report.source_requests[index];
          if (request.method === 'HEAD' && request.status_check === 'head_abort_pending_header_validation') {
            die(`HEAD request failed before planned metadata headers were validated: ${request.url}`);
          }
        }
        const tileDataEvidence = style.pmtiles_urls.map(url => ({ url, ...pmtilesTileDataRangeEvidence(url, report.source_requests) }));
        caseReport.style_render_evidence ||= [];
        caseReport.style_render_evidence.push({ style_key: style.key, tile_data: tileDataEvidence });
        if (args.inspectRenderer && datasetId === 'river-plastic-inputs') {
          caseReport.renderer_state = await page.evaluate(inspectMapRendererState, {
            target_urls: collection.pmtiles.map(layer => layer.url),
            base_url: page.url(),
            sample_limit: rendererInspectionCriteria.value.render_inspection_limits.max_rendered_feature_samples,
            max_source_features_for_types: rendererInspectionCriteria.value.observations.features.maximum_source_features_examined_for_type_counts,
            ...rendererInspectionCriteria.value.vue_traversal_limits,
            max_property_names: rendererInspectionCriteria.value.vue_traversal_limits.max_property_names_on_unavailable,
            max_style_layers: rendererInspectionCriteria.value.render_inspection_limits.max_style_layers_reported,
            max_rendered_features_for_samples: rendererInspectionCriteria.value.render_inspection_limits.max_rendered_features_examined_for_sample_selection,
            max_rendered_feature_samples: rendererInspectionCriteria.value.render_inspection_limits.max_rendered_feature_samples,
          });
          report.renderer_diagnostic.status = caseReport.renderer_state.available
            ? 'state_captured_pending_root_cause_review' : 'map_instance_unavailable';
        }
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        await page.waitForTimeout(500);
        const safeStyleKey = style.key.replace(/[^A-Za-z0-9._-]+/g, '-');
        const screenshotPath = path.join(input.out, `${datasetId}--${safeStyleKey}.png`);
        await page.screenshot({ path: screenshotPath, fullPage: false, animations: 'disabled' });
        caseReport.screenshots.push({ style_key: style.key, style_title: style.title,
          pmtiles_urls: style.pmtiles_urls, path: path.relative(input.out, screenshotPath) });
      }
      caseReport.screenshot = caseReport.screenshots[0]?.path || null;
      if (args.diagnoseRender && datasetId === 'river-plastic-inputs') {
        const diagnostic = { status: 'running', criteria_sha256: sha256(renderDiagnosticCriteria.bytes),
          preserved_default_screenshot: caseReport.screenshot, zoom_in_clicks: 0,
          overlay_title: renderDiagnosticCriteria.value.overlay_title, overlay_states: [], screenshots: [] };
        caseReport.render_diagnostic = diagnostic;
        const zoomIn = map.locator('.maplibregl-ctrl-zoom-in');
        for (let click = 0; click < renderDiagnosticCriteria.value.zoom_in_clicks; click++) {
          await zoomIn.click();
          diagnostic.zoom_in_clicks += 1;
          await page.waitForTimeout(250);
        }
        await settleDiagnosticView(page, sourceActivity, pending);
        const zoomPath = path.join(input.out, 'river-plastic-inputs--diagnostic-zoomed.png');
        await page.screenshot({ path: zoomPath, fullPage: false, animations: 'disabled' });
        diagnostic.screenshots.push({ view: 'zoomed_overlay_initial_state', path: path.relative(input.out, zoomPath) });

        const openLayerControl = async () => {
          await layerButton.click();
          await layerPanel.waitFor({ state: 'visible', timeout: 10000 });
        };
        const closeLayerControl = async () => {
          await layerButton.click();
          await layerPanel.waitFor({ state: 'hidden', timeout: 10000 });
        };
        const overlayCheckbox = () => page.getByRole('checkbox', {
          name: renderDiagnosticCriteria.value.overlay_title, exact: true,
        });
        await openLayerControl();
        let checkbox = overlayCheckbox();
        await checkbox.waitFor({ state: 'visible', timeout: 10000 });
        const initiallyChecked = await checkbox.isChecked();
        diagnostic.overlay_states.push({ action: 'initial_after_zoom', checked: initiallyChecked });
        if (!initiallyChecked) {
          await checkbox.check();
          diagnostic.overlay_states.push({ action: 'checked_before_toggle', checked: await checkbox.isChecked() });
        }
        await checkbox.uncheck();
        diagnostic.overlay_states.push({ action: 'unchecked', checked: await checkbox.isChecked() });
        await closeLayerControl();
        await settleDiagnosticView(page, sourceActivity, pending);
        const offPath = path.join(input.out, 'river-plastic-inputs--diagnostic-overlay-off.png');
        await page.screenshot({ path: offPath, fullPage: false, animations: 'disabled' });
        diagnostic.screenshots.push({ view: 'overlay_unchecked', path: path.relative(input.out, offPath) });

        await openLayerControl();
        checkbox = overlayCheckbox();
        await checkbox.waitFor({ state: 'visible', timeout: 10000 });
        await checkbox.check();
        diagnostic.overlay_states.push({ action: 'rechecked', checked: await checkbox.isChecked() });
        await closeLayerControl();
        await settleDiagnosticView(page, sourceActivity, pending);
        const onPath = path.join(input.out, 'river-plastic-inputs--diagnostic-overlay-on.png');
        await page.screenshot({ path: onPath, fullPage: false, animations: 'disabled' });
        diagnostic.screenshots.push({ view: 'overlay_rechecked', path: path.relative(input.out, onPath) });
        diagnostic.status = 'completed_pending_manual_visual_review';
        report.render_diagnostic.status = diagnostic.status;
      }
      while (pending.size) await Promise.all([...pending]);
      const observedPmtiles = new Set(report.source_requests.filter(item =>
        collection.pmtiles.some(layer => layer.url === item.url) && item.status_check === 'passed' && item.request_range).map(item => item.url));
      if (observedPmtiles.size !== collection.pmtiles.length) die(`Not every PMTiles layer was read for ${datasetId}`);
      if (caseReport.errors.length) die(`Browser errors occurred for ${datasetId}`);
      caseReport.status = args.inspectRenderer && datasetId === 'river-plastic-inputs'
        ? 'developer_diagnostic_captured_not_acceptance' : 'rendered_pending_manual_review';
      await context.close();
    }
  } catch (error) {
    report.errors.push(error.message);
    report.status = 'failed';
  } finally {
    while (pending.size) await Promise.allSettled([...pending]);
    await browser.close();
  }
  const missingRequiredPages = report.pages_metadata.expected_urls.filter(url => !pageResponses.has(url));
  if (missingRequiredPages.length && report.status !== 'failed') {
    report.status = 'failed';
    report.errors.push(`Required Pages metadata was not observed: ${missingRequiredPages.join(', ')}`);
  }
  if (footerGuard.counts().requested !== footerGuard.counts().verified) {
    report.errors.push('Approved GRWL footer-prefix request lacks an independently verified response body');
  }
  if (report.errors.length) {
    report.status = 'failed';
  } else if (report.status !== 'failed') {
    report.status = args.inspectRenderer ? 'developer_diagnostic_not_acceptance'
      : input.partial ? 'partial' : 'rendered_pending_manual_review';
  }
  if (args.inspectRenderer && report.status !== 'failed' &&
      report.renderer_diagnostic.status !== 'state_captured_pending_root_cause_review') {
    report.status = 'developer_diagnostic_incomplete';
  }
  report.pages_metadata.observed.sort((a, b) => a.url.localeCompare(b.url));
  report.pages_metadata.intercepted.sort((a, b) => a.url.localeCompare(b.url));
  await writeFile(path.join(input.out, 'portolan-browser-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`${report.status}: ${path.join(input.out, 'portolan-browser-report.json')}`);
  return ['failed', 'developer_diagnostic_incomplete'].includes(report.status) ? 1 : 0;
}

const criteriaLoaded = await readJson(CRITERIA_PATH, 'frozen Portolan Browser criteria');
const criteria = criteriaLoaded.value;
if (criteria.schema_version !== 1 || !criteria.frozen_before_viewer_run) die('Browser criteria must be frozen before execution');
const args = parseArgs(process.argv.slice(2));
if (args.selfTest) {
  const rendererCriteriaLoaded = await readJson(RIVER_RENDERER_INSPECTION_PATH, 'River renderer inspection criteria');
  const navigationCriteriaLoaded = await readJson(NAVIGATION_FOLLOWUP_CRITERIA_PATH, 'collection navigation follow-up criteria');
  selfTest(criteria, rendererCriteriaLoaded.value, navigationCriteriaLoaded.value);
} else {
  process.exitCode = await run(args, criteria, sha256(criteriaLoaded.bytes));
}


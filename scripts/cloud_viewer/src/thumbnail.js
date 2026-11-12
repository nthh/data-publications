import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {Protocol, PMTiles} from 'pmtiles';
import {VectorTile} from '@mapbox/vector-tile';
import {PbfReader} from 'pbf';
maplibregl.setWorkerUrl('/worker.mjs');

window.thumbnailReady = (async () => {
  const params = new URLSearchParams(location.search);
  const card = JSON.parse(params.get('card'));
  const plan = JSON.parse(params.get('map'));
  if (card.bounds) plan.bounds = card.bounds;
  document.querySelector('#title').textContent = card.title;
  document.querySelector('#subtitle').textContent = card.subtitle;
  document.querySelector('#attribution').textContent = card.attribution;
  if (card.legend) {
    const legend = document.querySelector('#legend');
    legend.hidden = false;
    legend.textContent = card.legend.label;
    const stops = document.createElement('div'); stops.className = 'legend-stops';
    for (const [label, color] of card.legend.stops) {
      const stop = document.createElement('span'); stop.className = 'legend-stop';
      const swatch = document.createElement('i'); swatch.style.background = color;
      stop.append(swatch, document.createTextNode(label)); stops.append(stop);
    }
    legend.append(stops);
  }
  const sourceLayer = card.style.layers.find(layer => layer.source === 'data' && layer['source-layer'])?.['source-layer'];
  if (!sourceLayer) throw new Error('Catalog style has no data source layer');
  const archive = new PMTiles(card.pmtiles.url);
  const protocol = new Protocol();
  protocol.add(archive);
  maplibregl.addProtocol('pmtiles', protocol.tile);
  const tileMetadata = await archive.getMetadata();
  const getFields = expression => {
    if (!Array.isArray(expression)) return [];
    return expression[0] === 'get' ? [expression[1]] : expression.flatMap(getFields);
  };
  for (const layer of card.style.layers.filter(layer => layer.source === 'data')) {
    const fields = tileMetadata.vector_layers?.find(item => item.id === layer['source-layer'])?.fields;
    if (!fields) throw new Error('Style layer absent from PMTiles metadata');
    for (const property of Object.values(layer.paint || {}).flatMap(getFields)) {
      if (!(property in fields)) throw new Error(`Style field absent from PMTiles: ${property}`);
    }
  }
  const style = structuredClone(card.style);
  let decodedTileCount = 0, decodedFeatures = 0;
  if (card.source_tile_zoom != null) {
    // A source's minzoom hides data below that zoom. Instead, decode the fixed
    // display tiles to a transient GeoJSON layer so the world camera stays fixed.
    // These are clipped/generalized display fragments, not analytical records.
    const z = card.source_tile_zoom, n = 2 ** z, features = [];
    const [[west, south], [east, north]] = plan.bounds;
    const tileX = lon => Math.max(0, Math.min(n - 1, Math.floor((lon + 180) / 360 * n)));
    const tileY = lat => Math.max(0, Math.min(n - 1, Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n)));
    // fitBounds expands the requested window to the viewport aspect. Fetch the
    // full expanded camera, including padding, so preview tile edges never masquerade as coverage edges.
    const mercY = lat => (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2;
    const cx = (west + east + 360) / 720, cy = (mercY(north) + mercY(south)) / 2;
    const spanX = (east - west) / 360, spanY = mercY(south) - mercY(north);
    const aspect = 1200 / 576;
    const dx = Math.max(spanX, spanY * aspect) * 1.12 / 2;
    const dy = Math.max(spanY, spanX / aspect) * 1.12 / 2;
    const clamp = value => Math.max(0, Math.min(n - 1, Math.floor(value * n)));
    const x0 = clamp(cx - dx), x1 = clamp(cx + dx), y0 = clamp(cy - dy), y1 = clamp(cy + dy);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 256) throw new Error('Preview exceeds 256 source tiles');
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x += 4) {
        const batches = await Promise.all(Array.from({length: Math.min(4, x1 - x + 1)}, async (_, offset) => {
          const tile = await archive.getZxy(z, x + offset, y);
          if (!tile) return [];
          decodedTileCount++;
          const layer = new VectorTile(new PbfReader(tile.data)).layers[sourceLayer];
          if (!layer) throw new Error('Decoded tile lacks expected source layer');
          return Array.from({length: layer.length}, (_, i) => {
            const feature = layer.feature(i).toGeoJSON(x + offset, y, z);
            // The decoder uses a null-prototype dictionary; MapLibre's worker
            // serializer expects an ordinary object. Preserve every property.
            return {...feature, properties: {...feature.properties}};
          });
        }));
        for (const batch of batches) features.push(...batch);
      }
    }
    decodedFeatures = features.length;
    style.sources.data = {type: 'geojson', data: {type: 'FeatureCollection', features}, tolerance: 0};
    for (const layer of style.layers) if (layer.source === 'data') delete layer['source-layer'];
  } else {
    style.sources.data.url = `pmtiles://${card.pmtiles.url}`;
  }
  style.sources.land = {type: 'geojson', data: '/land.geojson'};
  style.layers = [
    {id: 'ocean', type: 'background', paint: {'background-color': '#e9f1f2'}},
    {id: 'land-fill', type: 'fill', source: 'land', paint: {'fill-color': '#f7f6f0'}},
    {id: 'land-outline', type: 'line', source: 'land', paint: {'line-color': '#d5ddda', 'line-width': 0.55}},
    ...style.layers,
  ];
  const map = new maplibregl.Map({
    container: 'map', style, attributionControl: false, interactive: false,
    renderWorldCopies: false, maxPitch: 0,
    // Permit ocean margins instead of zooming in and cropping southern regions.
    transformConstrain: (center, zoom) => ({center, zoom}),
  });
  map.fitBounds(plan.bounds, {padding: 12, duration: 0});
  window.map = map;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Map did not become idle')), 55000);
    map.once('error', event => { clearTimeout(timer); reject(event.error || new Error('Map error')); });
    map.once('idle', () => {
      clearTimeout(timer);
      if (!map.isStyleLoaded() || !map.areTilesLoaded()) { reject(new Error('Map style or tiles are not fully loaded')); return; }
      const layers = card.style.layers.filter(layer => layer.source === 'data').map(layer => layer.id);
      const features = map.queryRenderedFeatures({layers});
      const bounds = map.getBounds(), [[west, south], [east, north]] = plan.bounds;
      if (bounds.getWest() > west + 1e-6 || bounds.getEast() < east - 1e-6 ||
          bounds.getSouth() > south + 1e-6 || bounds.getNorth() < north - 1e-6) {
        reject(new Error('Rendered camera crops the planned geographic bounds')); return;
      }
      resolve({feature_count: features.length, source_layer: sourceLayer,
        decoded_tile_count: decodedTileCount, decoded_features: decodedFeatures,
        camera: {center: map.getCenter().toArray(), zoom: map.getZoom(), bounds: bounds.toArray()},
      });
    });
  });
})();

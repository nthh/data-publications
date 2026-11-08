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
  document.querySelector('#title').textContent = card.title;
  document.querySelector('#subtitle').textContent = card.subtitle;
  document.querySelector('#attribution').textContent = card.attribution;
  const sourceLayer = card.style.layers.find(layer => layer.source === 'data' && layer['source-layer'])?.['source-layer'];
  if (!sourceLayer) throw new Error('Catalog style has no data source layer');
  const archive = new PMTiles(card.pmtiles.url);
  const protocol = new Protocol();
  protocol.add(archive);
  maplibregl.addProtocol('pmtiles', protocol.tile);
  const style = structuredClone(card.style);
  let decodedTileCount = 0, decodedFeatures = 0;
  if (card.source_tile_zoom != null) {
    // A source's minzoom hides data below that zoom. Instead, decode the fixed
    // display tiles to a transient GeoJSON layer so the world camera stays fixed.
    // These are clipped/generalized display fragments, not analytical records.
    const z = card.source_tile_zoom, n = 2 ** z, features = [];
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x += 4) {
        const batches = await Promise.all(Array.from({length: Math.min(4, n - x)}, async (_, offset) => {
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

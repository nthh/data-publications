#!/usr/bin/env python3
"""Capture bounded public ArcGIS Online item search metadata (no feature queries)."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://www.arcgis.com/sharing/rest/search"
MAX_REQUESTS = 120
MAX_BYTES = 30_000_000
MAX_RESULTS = 2_000
PAGE_SIZE = 50
MAX_PAGES_PER_QUERY = 2
USER_AGENT = "folia-global-candidates-research/1.0 (metadata-only; public ArcGIS REST)"
QUERIES = [
    ('living_atlas_global_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND global'),
    ('living_atlas_world_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND world'),
    ('living_atlas_boundaries_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND boundaries'),
    ('living_atlas_transport_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND transportation'),
    ('living_atlas_water_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND water'),
    ('living_atlas_environment_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND environment'),
    ('living_atlas_landcover_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND land cover'),
    ('living_atlas_population_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND population'),
    ('living_atlas_energy_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND energy'),
    ('living_atlas_human_settlements_feature', 'type:"Feature Service" AND tags:"Living Atlas" AND settlement'),
    ('living_atlas_global_imagery', 'type:"Image Service" AND tags:"Living Atlas" AND global'),
    ('living_atlas_world_imagery', 'type:"Image Service" AND tags:"Living Atlas" AND world'),
    ('living_atlas_global_raster', 'type:"Image Service" AND tags:"Living Atlas" AND global raster'),
    ('living_atlas_world_map_image', 'type:"Map Service" AND tags:"Living Atlas" AND world'),
    ('living_atlas_global_vector_tile', 'type:"Vector Tile Service" AND tags:"Living Atlas" AND global'),
    ('target_world_countries', 'title:"World Countries" AND type:"Feature Service"'),
    ('target_world_administrative_divisions', 'title:"World Administrative Divisions" AND type:"Feature Service"'),
    ('target_world_cities', 'title:"World Cities" AND type:"Feature Service"'),
    ('target_world_urban_areas', 'title:"World Urban Areas" AND type:"Feature Service"'),
    ('target_global_human_settlement_urban_centres', 'title:"Global Human Settlement Urban Centres" AND type:"Feature Service"'),
    ('target_global_power_plants', 'title:"Global Power Plants" AND type:"Feature Service"'),
    ('target_global_ports', 'title:"Global Ports" AND type:"Feature Service"'),
    ('target_global_airports', 'title:"Global Airports" AND type:"Feature Service"'),
    ('target_global_rivers', 'title:"Global Rivers Atlas" AND type:"Feature Service"'),
    ('target_world_rivers', 'title:"World Rivers" AND type:"Feature Service"'),
    ('target_biodiversity_hotspots', 'title:"Biodiversity Hotspots" AND type:"Feature Service"'),
    ('target_global_roads', 'title:"Global Roads" AND type:"Feature Service"'),
    ('target_ghsl', 'title:"Global Human Settlement Layer" AND type:"Feature Service"'),
    ('esri_dm_global_feature', 'owner:"esri_dm" AND type:"Feature Service" AND global'),
    ('target_resolve_ecoregions', 'title:"RESOLVE Ecoregions and Biomes" AND type:"Feature Service"'),
    ('target_global_monthly_temperature_anomaly', 'title:"Global Monthly Temperature Anomaly" AND type:"Feature Service"'),
    ('target_world_ecological_land_units', 'title:"World Ecological Land Units" AND type:"Image Service"'),
    ('target_protected_planet', 'title:"Protected Planet" AND type:"Feature Service"'),
    ('target_world_ecoregions', 'title:"Terrestrial Ecoregions of the World" AND type:"Feature Service"'),
    ('target_world_ecological_land_units_unfiltered', 'title:"World Ecological Land Units"'),
    ('target_world_populated_places', 'title:"World Populated Places" AND type:"Feature Service"'),
    ('target_wfp_global_ports', 'title:"Global Ports" AND owner:"vamsi.yarramaasu_UNWFP"'),
]
FIELDS = ('id','title','type','typeKeywords','description','snippet','access','licenseInfo','license','owner','ownerFolder','url','tags','categories','modified','created','numViews','size','extent','spatialReference','culture','accessInformation','credits','properties')

class CaptureError(Exception): pass

class Client:
    def __init__(self): self.requests = 0; self.bytes = 0
    def get_json(self, query, start):
        if self.requests >= MAX_REQUESTS: raise CaptureError('request cap reached before request')
        params = {'q': query, 'num': PAGE_SIZE, 'start': start, 'f': 'json'}
        url = ENDPOINT + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        self.requests += 1
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(MAX_BYTES - self.bytes + 1)
            if len(raw) > MAX_BYTES - self.bytes: raise CaptureError('byte cap would be exceeded')
            self.bytes += len(raw)
            final_url = response.geturl()
        return json.loads(raw), final_url, hashlib.sha256(raw).hexdigest(), len(raw)

def fetch_snapshot(out):
    client = Client(); pages = []; items = {}; errors = []; total_fetched = 0
    stop_reason = None
    for qid, query in QUERIES:
        start = 1; query_page_count = 0
        while start > 0 and query_page_count < MAX_PAGES_PER_QUERY:
            if total_fetched >= MAX_RESULTS:
                stop_reason = 'max_search_results'; break
            try:
                data, url, digest, nbytes = client.get_json(query, start)
                if 'error' in data: raise CaptureError(json.dumps(data['error'], sort_keys=True))
                results = data.get('results') or []
                accepted = results[:MAX_RESULTS-total_fetched]
                query_page_count += 1
                next_start = data.get('nextStart', -1)
                pages.append({'query_id': qid, 'query': query, 'page_start': start,
                              'page_size_requested': PAGE_SIZE, 'total_reported': data.get('total'),
                              'returned_count': len(results), 'captured_count': len(accepted),
                              'results_truncated_for_query_cap': bool(
                                  isinstance(next_start, int) and next_start > 0
                                  and query_page_count >= MAX_PAGES_PER_QUERY),
                              'nextStart': next_start, 'response_url': url,
                              'response_bytes': nbytes, 'response_sha256': digest})
                total_fetched += len(accepted)
                for raw in accepted:
                    ident = raw.get('id')
                    if not ident: continue
                    item = {k: raw.get(k) for k in FIELDS if k in raw}
                    found = items.setdefault(ident, {'item': item, 'discovered_by': []})
                    found['discovered_by'].append({'query_id': qid, 'page_start': start, 'query': query})
                if not results or not isinstance(next_start, int) or next_start < 1 or next_start == start:
                    break
                start = next_start
                time.sleep(0.15)
            except Exception as e:
                errors.append({'query_id': qid, 'query': query, 'page_start': start,
                               'error_type': type(e).__name__, 'error': str(e)[:500]})
                stop_reason = 'capture_error'
                break
        if stop_reason: break
    snapshot = {
        'schema_version': 1,
        'capture': {'captured_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'endpoint': ENDPOINT, 'method': 'GET', 'authentication': 'none',
                    'request_count': client.requests, 'response_bytes': client.bytes,
                    'max_requests': MAX_REQUESTS, 'max_bytes': MAX_BYTES,
                    'max_search_results': MAX_RESULTS, 'search_results_fetched_including_duplicates': total_fetched,
                    'unique_items': len(items),
                    'truncated_query_pages': sum(1 for p in pages if p['results_truncated_for_query_cap']),
                    'page_size': PAGE_SIZE, 'max_pages_per_query': MAX_PAGES_PER_QUERY,
                    'stop_reason': stop_reason or 'query_pages_exhausted', 'errors': errors},
        'pages': pages,
        'items': [items[k] for k in sorted(items)],
    }
    # Exclusive creation is a second guard against overwriting retained evidence.
    with out.open('x', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps(snapshot['capture'], indent=2, sort_keys=True))
    print(f'wrote {out}')
    return 2 if errors else 0

def check_snapshot(snapshot_path, reviewed_path):
    errors = []
    def require(condition, message):
        if not condition: errors.append(message)
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        reviewed = json.loads(reviewed_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'check failed: {type(e).__name__}: {e}', file=sys.stderr)
        return 2
    capture = snapshot.get('capture', {})
    pages = snapshot.get('pages', [])
    items = snapshot.get('items', [])
    require(snapshot.get('schema_version') == 1, 'unexpected snapshot schema_version')
    require(reviewed.get('schema_version') == 1, 'unexpected review schema_version')
    require(isinstance(pages, list) and isinstance(items, list), 'pages/items must be lists')
    page_count = len(pages)
    require(capture.get('request_count') == page_count,
            f"request_count {capture.get('request_count')} != page count {page_count}")
    summed_bytes = sum(p.get('response_bytes', 0) for p in pages)
    require(capture.get('response_bytes') == summed_bytes,
            f"response_bytes {capture.get('response_bytes')} != page byte sum {summed_bytes}")
    summed_rows = sum(p.get('captured_count', 0) for p in pages)
    require(capture.get('search_results_fetched_including_duplicates') == summed_rows,
            f"captured rows {capture.get('search_results_fetched_including_duplicates')} != page row sum {summed_rows}")
    ids = [w.get('item', {}).get('id') for w in items]
    require(all(isinstance(i, str) and i for i in ids), 'every retained item must have an id')
    unique_ids = set(ids)
    require(len(unique_ids) == len(ids), 'duplicate item IDs in normalized inventory')
    require(capture.get('unique_items') == len(items),
            f"unique_items {capture.get('unique_items')} != retained item count {len(items)}")
    require(capture.get('request_count', MAX_REQUESTS + 1) <= MAX_REQUESTS, 'request budget exceeded')
    require(capture.get('response_bytes', MAX_BYTES + 1) <= MAX_BYTES, 'byte budget exceeded')
    require(capture.get('search_results_fetched_including_duplicates', MAX_RESULTS + 1) <= MAX_RESULTS,
            'search-result budget exceeded')
    require(not capture.get('errors'), 'capture has recorded request errors')
    require(capture.get('stop_reason') == 'query_pages_exhausted',
            f"unexpected stop_reason {capture.get('stop_reason')!r}")

    max_pages = capture.get('max_pages_per_query')
    observed_truncated = 0
    seen_query_pages = {}
    for p in pages:
        qid = p.get('query_id')
        seen_query_pages[qid] = seen_query_pages.get(qid, 0) + 1
        occurrence = seen_query_pages[qid]
        next_start = p.get('nextStart')
        should_truncate = bool(isinstance(next_start, int) and next_start > 0
                               and isinstance(max_pages, int) and occurrence >= max_pages)
        observed_truncated += int(bool(p.get('results_truncated_for_query_cap')))
        require(bool(p.get('results_truncated_for_query_cap')) == should_truncate,
                f"truncation flag inconsistent for {qid} page {p.get('page_start')}")
        require(p.get('captured_count', 0) <= p.get('returned_count', 0),
                f"captured count exceeds returned count for {qid}")
        require(p.get('captured_count', 0) <= p.get('page_size_requested', 0),
                f"captured count exceeds page size for {qid}")
    require(capture.get('truncated_query_pages') == observed_truncated,
            f"truncated_query_pages {capture.get('truncated_query_pages')} != flags {observed_truncated}")

    candidates = reviewed.get('candidates', [])
    suggested_ids = [c.get('suggested_id') for c in candidates]
    require(len(suggested_ids) == len(set(suggested_ids)), 'duplicate suggested_id values')
    checked_item_ids = set()
    for candidate in candidates:
        for source in candidate.get('sources', []):
            url = urllib.parse.urlparse(source.get('url', ''))
            if url.hostname not in {'arcgis.com', 'www.arcgis.com'} or url.path.rstrip('/') != '/home/item.html':
                continue
            item_id = urllib.parse.parse_qs(url.query).get('id', [None])[0]
            if item_id:
                checked_item_ids.add(item_id)
                require(item_id in unique_ids,
                        f"reviewed ArcGIS item {item_id} ({candidate.get('suggested_id')}) absent from retained capture")
                entry_id = source.get('entry_id')
                if isinstance(entry_id, str) and len(entry_id) == 32 and all(c in '0123456789abcdefABCDEF' for c in entry_id):
                    require(entry_id == item_id,
                            f"reviewed ArcGIS item URL/entry_id mismatch for {candidate.get('suggested_id')}: {item_id}")
    require(bool(checked_item_ids), 'no reviewed ArcGIS item-page IDs were checked')

    if errors:
        print('offline check failed:', file=sys.stderr)
        for error in errors: print(f'- {error}', file=sys.stderr)
        return 2
    print(json.dumps({'status': 'ok', 'snapshot': str(snapshot_path),
                      'reviewed': str(reviewed_path), 'pages': page_count,
                      'items': len(items), 'unique_ids': len(unique_ids),
                      'rows': summed_rows, 'bytes': summed_bytes,
                      'truncated_pages': observed_truncated,
                      'reviewed_candidates': len(candidates),
                      'reviewed_arcgis_item_ids_checked': len(checked_item_ids)},
                     indent=2, sort_keys=True))
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fetch', action='store_true', help='make bounded public search requests')
    mode.add_argument('--check', action='store_true', help='validate retained normalized capture offline')
    parser.add_argument('--output', type=Path,
                        help='required new, nonexistent path for --fetch; never overwrite')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'search-inventory.json',
                        help='capture JSON to check (default: retained search-inventory.json)')
    parser.add_argument('--reviewed', type=Path, default=ROOT / 'reviewed.json',
                        help='review JSON to check (default: reviewed.json)')
    args = parser.parse_args(argv)
    if args.fetch:
        if args.output is None:
            parser.error('--fetch requires --output NEW_PATH')
        out = args.output.expanduser()
        if out.exists():
            parser.error(f'refusing to overwrite existing output: {out}')
        if not out.parent.is_dir():
            parser.error(f'output parent directory must already exist: {out.parent}')
        return fetch_snapshot(out)
    if args.output is not None:
        parser.error('--output is only valid with --fetch')
    # No arguments intentionally means an offline integrity check.
    return check_snapshot(args.snapshot, args.reviewed)

if __name__ == '__main__': sys.exit(main())

#!/usr/bin/env python3
"""Replay a local GEE capture against a frozen local sample, entirely offline."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

try:
    from pyproj import CRS, Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
except ImportError:  # Helpful error for users invoking the system Python.
    CRS = Transformer = shape = transform = None


ROOT = Path(__file__).resolve().parents[2]
DATASETS = {'hydrolakes', 'lakeatlas-polygons', 'lakeatlas-points', 'free-flowing-rivers', 'grwl-raw'}
EXCLUDED = {
    'derived': 'local derived field excluded by frozen criteria',
    'source_fid': 'source file geodatabase identifier is not GEE identity',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def fail(message):
    raise ValueError(message)


def field_aliases(name, meta):
    explicit = meta.get('gee_aliases', [])
    if not isinstance(explicit, list) or any(not isinstance(x, str) for x in explicit):
        fail(f'Invalid gee_aliases for {name}')
    return [name, *explicit]


def resolve_field(name, meta, properties):
    """Exact name first, then one unique case-folded match; never fuzzy-match."""
    aliases = field_aliases(name, meta)
    for alias in aliases:
        if alias in properties:
            return alias
    folded = defaultdict(set)
    for key in properties:
        folded[str(key).casefold()].add(key)
    matches = set()
    for alias in aliases:
        matches.update(folded.get(alias.casefold(), set()))
    return next(iter(matches)) if len(matches) == 1 else None


def ulp(value):
    return math.ulp(value) if math.isfinite(value) else math.inf


def number(value):
    # JSON booleans are Python integers, but are never numeric values here.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def type_kind(type_name):
    t = type_name.lower().replace(' ', '')
    if 'decimal' in t:
        return 'decimal'
    if t in {'float', 'float32', 'halffloat'} or t.startswith('float32'):
        return 'float32'
    if t in {'double', 'float64'} or t.startswith('double') or t.startswith('float64'):
        return 'float64'
    if t.startswith(('int', 'uint')) or t in {'bool', 'boolean'}:
        return 'integer'
    if t.startswith(('string', 'large_string')):
        return 'string'
    return 'other'


def source_decimal(value):
    try:
        d = Decimal(str(value))
        f = float(d)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def compare_value(local, gee, type_name):
    """Return (equal, match_kind, detail); no string/number coercion on GEE."""
    if local is None:
        return (gee is None, 'exact' if gee is None else 'mismatch', 'null')
    if gee is None:
        return False, 'mismatch', 'nonnull_missing_or_null'
    kind = type_kind(type_name)
    if kind == 'integer':
        if type_name.lower() in {'bool', 'boolean'}:
            equal = isinstance(local, bool) and isinstance(gee, bool) and local is gee
            return equal, 'exact' if equal else 'mismatch', 'boolean'
        n = number(gee)
        if n is None or not math.isfinite(float(n)) or int(n) != n:
            return False, 'mismatch', 'expected_integral_json_number'
        try:
            equal = int(local) == int(n)
        except (TypeError, ValueError, OverflowError):
            equal = False
        return equal, 'exact' if equal else 'mismatch', 'integer'
    if kind in {'float64', 'float32', 'decimal'}:
        n = number(gee)
        if n is None or not math.isfinite(float(n)):
            return False, 'mismatch', 'expected_finite_json_number'
        try:
            local_number = source_decimal(local) if kind == 'decimal' else float(local)
            gee_number = float(n)
        except (TypeError, ValueError, OverflowError):
            local_number = None
        if local_number is None or not math.isfinite(local_number):
            return False, 'mismatch', 'invalid_local_number'
        if kind == 'float32':
            try:
                f32 = struct.unpack('!f', struct.pack('!f', local_number))[0]
                gee_f32 = struct.unpack('!f', struct.pack('!f', gee_number))[0]
            except OverflowError:
                return False, 'mismatch', 'local_outside_float32'
            equal = gee_f32 == f32
            return equal, ('exact' if gee_number == local_number else 'representational' if equal else 'mismatch'), 'float32_roundtrip'
        tol = max(0.5e-18, 2 * max(ulp(local_number), ulp(gee_number))) if kind == 'decimal' else 2 * max(ulp(local_number), ulp(gee_number))
        equal = abs(local_number - gee_number) <= tol
        return equal, ('exact' if local_number == gee_number else 'representational' if equal else 'mismatch'), kind
    if kind == 'string':
        equal = isinstance(gee, str) and isinstance(local, str) and local == gee
        return equal, 'exact' if equal else 'mismatch', 'unicode_exact'
    # Geometry/source binary values are not silently coerced into attributes.
    equal = type(local) is type(gee) and local == gee
    return equal, 'exact' if equal else 'mismatch', 'strict_value'


def promote_singleton(g):
    if g is None:
        return None
    typ = g.get('type')
    coords = g.get('coordinates')
    if typ == 'Point':
        return {'type': 'MultiPoint', 'coordinates': [coords]}
    if typ == 'LineString':
        return {'type': 'MultiLineString', 'coordinates': [coords]}
    if typ == 'Polygon':
        return {'type': 'MultiPolygon', 'coordinates': [coords]}
    return g


def normalized_geom(g):
    if not isinstance(g, dict) or not g.get('type') or not g.get('coordinates'):
        raise ValueError('missing_or_empty_geometry')
    pg = promote_singleton(g)
    geom = shape(pg)
    if geom.is_empty:
        raise ValueError('missing_or_empty_geometry')
    if not all(math.isfinite(x) for x in geom.bounds):
        raise ValueError('nonfinite_geometry')
    # Shapely normalize sorts components, starts rings canonically and fixes ring direction.
    return geom.normalize()


def geom_coords(g):
    """Flatten normalized GeoJSON coordinate arrays into aligned lon/lat sequences."""
    pg = promote_singleton(g)
    try:
        pg = normalized_geom(pg).__geo_interface__
    except Exception:
        pass
    out = []
    def walk(x):
        if isinstance(x, (list, tuple)):
            if len(x) >= 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in x):
                if not all(math.isfinite(float(v)) for v in x):
                    raise ValueError('nonfinite_geometry')
                out.append(tuple(float(v) for v in x))
            else:
                for y in x:
                    walk(y)
    walk(pg.get('coordinates'))
    return out


def geometry_result(local, gee):
    result = {'strict': False, 'diagnostic': 'incomplete', 'reason': None, 'max_vertex_displacement_m': None, 'hausdorff_m': None}
    try:
        a, b = normalized_geom(local), normalized_geom(gee)
        norm_local, norm_gee = a.__geo_interface__, b.__geo_interface__
        def coord_structure(value):
            if isinstance(value, (list, tuple)):
                if value and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
                    return ('coord', len(value))
                return tuple(coord_structure(x) for x in value)
            return type(value).__name__
        same_structure = norm_local.get('type') == norm_gee.get('type') and coord_structure(norm_local.get('coordinates')) == coord_structure(norm_gee.get('coordinates'))
        local_dims = {len(c) for c in geom_coords(norm_local)}
        gee_dims = {len(c) for c in geom_coords(norm_gee)}
        same_dimensions = local_dims == gee_dims
        result['geometry_type_changed'] = local.get('type') != gee.get('type')
        if a.geom_type == b.geom_type and same_structure and same_dimensions and a.equals_exact(b, 1e-8, normalize=True):
            # GEOS topological equality may ignore Z; preserve every additional ordinate strictly.
            local_coords = geom_coords(norm_local)
            gee_coords = geom_coords(norm_gee)
            extra_equal = all(x[2:] == y[2:] for x, y in zip(local_coords, gee_coords))
        else:
            extra_equal = False
        if a.geom_type == b.geom_type and same_structure and same_dimensions and a.equals_exact(b, 1e-8, normalize=True) and extra_equal:
            result.update(strict=True, diagnostic='aligned_vertices', reason=None)
        else:
            result['reason'] = 'strict_structure_or_coordinate_mismatch'
        ac, bc = geom_coords(local), geom_coords(gee)
        if same_structure and same_dimensions and len(ac) == len(bc) and len(ac) > 0:
            from pyproj import Geod
            geod = Geod(ellps='WGS84')
            ds = [geod.inv(x1[0], x1[1], x2[0], x2[1])[2] for x1, x2 in zip(ac, bc)]
            result['max_vertex_displacement_m'] = max(ds)
            result['diagnostic'] = 'aligned_vertices'
            result['diagnostic_pass'] = max(ds) <= 1.0
        elif max(len(ac), len(bc)) <= 5000:
            # Only a diagnostic; project both locally around their combined centroid.
            from pyproj import Geod
            pts = ac + bc
            if pts:
                geod = Geod(ellps='WGS84')
                lon0 = sum(p[0] for p in pts) / len(pts)
                lat0 = sum(p[1] for p in pts) / len(pts)
                local_crs = CRS.from_proj4(f'+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs')
                project = Transformer.from_crs('EPSG:4326', local_crs, always_xy=True).transform
                ah, bh = transform(project, a), transform(project, b)
                result['hausdorff_m'] = float(ah.hausdorff_distance(bh))
                result['diagnostic'] = 'local_aeqd_hausdorff'
                result['diagnostic_pass'] = result['hausdorff_m'] <= 1.0
            else:
                result['reason'] = 'empty_coordinate_sequence'
        else:
            result.update(diagnostic='incomplete_large_structure_difference', reason='vertex_limit_exceeded')
    except Exception as e:
        result.update(reason=str(e), diagnostic='incomplete')
    return result


def request_id_list(dataset, plan):
    ids = [r.get('id') for r in plan.get('requests', [])]
    return ids


def verify_capture(sample_path, sample, capture_dir, plan_path, plan, criteria_path, criteria):
    issues = []
    receipt_path = capture_dir / 'capture.json'
    if not receipt_path.is_file():
        return ['capture.json is missing'], {}, {}
    receipt = read_json(receipt_path)
    if receipt.get('status') != 'complete':
        issues.append('capture receipt status is not complete')
    if receipt.get('plan_sha256') != sha(plan_path):
        issues.append('capture plan SHA-256 does not bind supplied plan')
    if plan.get('sample_sha256') != sha(sample_path):
        issues.append('plan sample SHA-256 does not bind supplied sample')
    if plan.get('criteria_sha256') != sha(criteria_path):
        issues.append('plan criteria SHA-256 does not bind supplied criteria')
    if sample.get('criteria_sha256') != sha(criteria_path):
        issues.append('sample criteria SHA-256 does not bind supplied criteria')
    if sample.get('dataset_id') != plan.get('dataset_id'):
        issues.append('sample and plan dataset_id differ')
    if plan.get('dataset_id') not in DATASETS:
        issues.append('unsupported dataset_id')
    reqs = plan.get('requests', [])
    req_by_id = {r.get('id'): r for r in reqs if isinstance(r, dict)}
    if len(req_by_id) != len(reqs):
        issues.append('plan request IDs are missing or duplicated')
    if len(receipt.get('queries', [])) != len({q.get('id') for q in receipt.get('queries', []) if isinstance(q, dict)}):
        issues.append('receipt query IDs are duplicated')
    rec_by_id = {q.get('id'): q for q in receipt.get('queries', []) if isinstance(q, dict)}
    if set(rec_by_id) != set(req_by_id):
        issues.append('receipt query IDs do not exactly match plan request IDs')
    files = defaultdict(list)
    seen_request = set()
    for r in receipt.get('requests', []):
        qid, rel = r.get('query'), r.get('response_path')
        if qid not in req_by_id:
            issues.append(f'receipt contains unplanned query {qid!r}')
            continue
        if not isinstance(rel, str) or Path(rel).name != rel or rel in {'', '.', '..'}:
            issues.append(f'invalid response path for {qid}')
            continue
        files[qid].append((r, capture_dir / rel))
        if r.get('http_status') != 200:
            issues.append(f'non-200 response for {qid}')
        if r.get('resource') != req_by_id[qid].get('resource'):
            issues.append(f'resource mismatch for {qid}')
        paged = req_by_id[qid].get('paginate') is True or qid.startswith(f"{plan.get('dataset_id')}-features-")
        if not paged and r.get('params', {}) != req_by_id[qid].get('params', {}):
            issues.append(f'query parameters mismatch for {qid}')
        expected_method = 'POST' if req_by_id[qid].get('operation') == 'count' else 'GET'
        if r.get('method') != expected_method:
            issues.append(f'method mismatch for {qid}')
        expected_endpoint = f"projects/{plan.get('quota_project')}/value:compute" if expected_method == 'POST' else None
        if r.get('endpoint_resource') != expected_endpoint:
            if expected_endpoint is not None or 'endpoint_resource' in r:
                issues.append(f'compute endpoint mismatch for {qid}')
        if expected_method == 'POST':
            expected_body = {'expression': {'result': '0', 'values': {'0': {'functionInvocationValue': {'functionName': 'Collection.size', 'arguments': {'collection': {'functionInvocationValue': {'functionName': 'Collection.loadTable', 'arguments': {'tableId': {'constantValue': req_by_id[qid].get('resource')}}}}}}}}}}
            if r.get('body') != expected_body:
                issues.append(f'count expression mismatch for {qid}')
        if r.get('response_path') in seen_request:
            issues.append(f'duplicate response path {rel}')
        seen_request.add(r.get('response_path'))
    payloads = {}
    for qid, entries in files.items():
        payloads[qid] = []
        for item, path in entries:
            if not path.is_file():
                issues.append(f'response file missing for {qid}: {path.name}')
                continue
            raw = path.read_bytes()
            if len(raw) != item.get('response_bytes') or hashlib.sha256(raw).hexdigest() != item.get('response_sha256'):
                issues.append(f'response hash/size mismatch for {qid}: {path.name}')
                continue
            try:
                payloads[qid].append((item, json.loads(raw)))
            except Exception:
                issues.append(f'invalid JSON response for {qid}: {path.name}')
    for qid, req in req_by_id.items():
        query = rec_by_id.get(qid, {})
        paged = req.get('paginate') is True or qid.startswith(f"{plan.get('dataset_id')}-features-")
        if paged and (query.get('pagination_terminated') is not True or query.get('complete_enumeration') is not True):
            issues.append(f'paginated query {qid} is not completely terminated')
        if not files.get(qid):
            issues.append(f'planned query has no response: {qid}')
        if paged and files.get(qid):
            ordered = payloads.get(qid, [])
            if len(ordered) != len(files[qid]):
                issues.append(f'one or more page payloads are unavailable for {qid}')
            tokens_seen = set()
            for idx, (item, payload) in enumerate(ordered):
                token = payload.get('nextPageToken')
                if token:
                    if token in tokens_seen:
                        issues.append(f'repeated pagination token for {qid}')
                    tokens_seen.add(token)
                expected_params = req.get('params', {}).copy()
                if idx:
                    expected_token = ordered[idx - 1][1].get('nextPageToken')
                    if not expected_token:
                        issues.append(f'page follows terminal response for {qid}')
                    expected_params['pageToken'] = expected_token
                if item.get('params', {}) != expected_params:
                    issues.append(f'page parameters/token chain mismatch for {qid}')
                if idx == len(ordered) - 1 and payload.get('nextPageToken'):
                    issues.append(f'last captured page has an unconsumed token for {qid}')
    return issues, payloads, rec_by_id


def build_report(sample_path, sample, capture_dir, plan_path, plan, criteria_path, criteria):
    issues, payloads, receipt_queries = verify_capture(sample_path, sample, capture_dir, plan_path, plan, criteria_path, criteria)
    comparison_issues = []
    dataset = sample.get('dataset_id')
    if dataset not in DATASETS:
        fail(f'Unsupported dataset_id: {dataset!r}')
    features = sample.get('features')
    fields = sample.get('fields')
    if not isinstance(features, list) or not isinstance(fields, dict):
        fail('Sample must contain features array and fields mapping')
    reqs = {r['id']: r for r in plan.get('requests', [])}
    before = f'{dataset}-before'
    after = f'{dataset}-after'
    if before not in reqs or after not in reqs:
        issues.append('before/after metadata requests are required')
    def first_json(qid):
        vals = payloads.get(qid, [])
        return vals[0][1] if vals else None
    if first_json(before) is None or first_json(after) is None:
        issues.append('before/after metadata response missing')
        stable_metadata = False
    else:
        first_before = payloads[before][0][1]
        first_after = payloads[after][0][1]
        # The frozen provenance criterion is byte identity, not JSON semantic equality.
        stable_metadata = payloads[before][0][0].get('response_sha256') == payloads[after][0][0].get('response_sha256')
        if not stable_metadata:
            issues.append('before/after metadata response content changed')
    count_id = f'{dataset}-count'
    count_payload = first_json(count_id)
    gee_count = count_payload.get('result') if isinstance(count_payload, dict) else None
    local_count = sample.get('source', {}).get('row_count')
    frozen_count = criteria.get('global_counts', {}).get(dataset)
    count_ok = isinstance(gee_count, int) and not isinstance(gee_count, bool) and gee_count == local_count and (frozen_count is None or gee_count == frozen_count)
    if not count_ok:
        issues.append('synchronous collection count does not equal immutable local row_count')

    excluded = {name: EXCLUDED.get(meta.get('role'), 'non-source field excluded') for name, meta in fields.items() if meta.get('role') in EXCLUDED}
    active_fields = {name: meta for name, meta in fields.items() if meta.get('role') in {'source', 'geometry_derived'}}
    field_coverage = {n: {'role': m.get('role'), 'matched_name': None, 'coverage': 0, 'missing': 0, 'exact': 0, 'representational': 0, 'mismatch': 0} for n, m in active_fields.items()}
    samples_by_id = {str(f.get('local_id')): f for f in features}
    if len(samples_by_id) != len(features):
        issues.append('sample local_id values are duplicated')
    all_gee = []
    gee_origin = {}
    feature_ids_seen = {}
    conflicting_ids = []
    repeated_identical = 0
    for qid in reqs:
        if not qid.startswith(f'{dataset}-features-'):
            continue
        for _, payload in payloads.get(qid, []):
            for feat in payload.get('features', []):
                if not isinstance(feat, dict):
                    issues.append(f'malformed feature in {qid}')
                    continue
                fid = feat.get('id')
                if fid is not None:
                    key = str(fid)
                    content = canonical(feat)
                    if key in feature_ids_seen:
                        previous_content, previous_query = feature_ids_seen[key]
                        allowed_overlap = dataset == 'grwl-raw' and previous_query != qid and bool(reqs.get(previous_query, {}).get('selected_local_ids')) and bool(reqs.get(qid, {}).get('selected_local_ids'))
                        if allowed_overlap and previous_content == content:
                            # Keep its query context; targets are matched only inside their assigned query.
                            repeated_identical += 1
                        else:
                            conflicting_ids.append(key)
                            issues.append(f'conflicting duplicate GEE feature id {key}' if previous_content != content else f'duplicate GEE feature id {key} outside permitted overlapping spatial queries')
                            continue
                    feature_ids_seen[key] = (content, qid)
                all_gee.append(feat)
                gee_origin[id(feat)] = qid

    # Match target samples by stable Hylak_id / GOID. Raw observations are multiset-matched.
    properties = [f.get('properties', {}) for f in all_gee]
    target_matches = defaultdict(list)
    extras = 0
    if dataset == 'grwl-raw':
        key_fields = sample.get('key_fields', [])
        if key_fields != ['lon', 'lat', 'segmentID', 'segmentInd']:
            issues.append('raw key_fields must be lon,lat,segmentID,segmentInd in frozen order')
        def compound(obj):
            vals = obj.get('properties', obj)
            names = []
            for k in key_fields:
                actual = k if k in vals else next((x for x in vals if isinstance(x, str) and x.casefold() == k.casefold()), None)
                if actual is None:
                    return None
                value = vals[actual]
                names.append(float(value) if k in {'lon', 'lat'} else value)
            return canonical(names)
        local_by_id = {str(f.get('local_id')): f for f in features}
        request_targets = {}
        for qid, req in reqs.items():
            if qid.startswith(f'{dataset}-features-'):
                selected = req.get('selected_local_ids')
                if not isinstance(selected, list) or not selected:
                    issues.append(f'raw request {qid} lacks explicit selected_local_ids')
                    continue
                request_targets[qid] = [local_by_id[str(x)] for x in selected if str(x) in local_by_id]
                unknown = [str(x) for x in selected if str(x) not in local_by_id]
                if unknown:
                    issues.append(f'raw request {qid} selects unknown local IDs: {unknown[:5]}')
        assignments = Counter(str(x) for req in reqs.values() if req.get('id', '').startswith(f'{dataset}-features-') for x in req.get('selected_local_ids', []))
        for local in features:
            lid = str(local.get('local_id'))
            if assignments[lid] != 1:
                issues.append(f'raw local sample {lid} assigned to {assignments[lid]} spatial requests; expected exactly one')
        got = defaultdict(list)
        targeted_keys_by_query = {qid: {compound(f) for f in rows} for qid, rows in request_targets.items()}
        for f in all_gee:
            qid = gee_origin[id(f)]
            k = compound(f)
            if k is None:
                continue
            if k in targeted_keys_by_query.get(qid, set()):
                got[k].append(f)
            elif any(k in keys for keys in targeted_keys_by_query.values()):
                issues.append(f'raw target-key feature appeared in an unassigned spatial query {qid}; anonymous overlap cannot be deduplicated')
            else:
                extras += 1
        wanted = Counter(compound(f) for f in features)
        for k, n in wanted.items():
            for f in got.get(k, [])[:n]:
                target_matches[k].append(f)
            if len(got.get(k, [])) > n:
                extras += len(got[k]) - n
        # Multiplicity is checked; individual identity for coincident keys is forbidden.
        for k, n in wanted.items():
            if len(got.get(k, [])) != n:
                comparison_issues.append(f'raw compound-key multiplicity mismatch {k}: wanted {n}, got {len(got.get(k, []))}')
    else:
        ident = 'Hylak_id' if dataset in {'hydrolakes', 'lakeatlas-polygons', 'lakeatlas-points'} else 'GOID'
        id_values = defaultdict(list)
        for f in all_gee:
            p = f.get('properties', {})
            actual = ident if ident in p else next((x for x in p if x.casefold() == ident.casefold()), None)
            if actual is not None:
                id_values[str(p[actual])].append(f)
        wanted = set(samples_by_id)
        for local_id in wanted:
            fs = id_values.get(local_id, [])
            if len(fs) == 0:
                issues.append(f'missing selected {ident} {local_id}')
            elif len(fs) > 1:
                issues.append(f'duplicate selected {ident} {local_id}: {len(fs)} matches')
            else:
                target_matches[local_id].extend(fs)
        extras = sum(1 for k, v in id_values.items() if k not in wanted for _ in v)

    cells = Counter()
    geom_results = []
    records = []
    raw_pairing = {}
    raw_groups = []
    if dataset == 'grwl-raw':
        local_groups = defaultdict(list)
        for local in features:
            local_groups[canonical([float(local.get('properties', {}).get(k)) if k in {'lon', 'lat'} else local.get('properties', {}).get(k) for k in sample['key_fields']])].append(local)
        def pair_compatible(local, gee):
            props = gee.get('properties', {})
            for name, meta in active_fields.items():
                if meta.get('role') != 'source':
                    continue
                actual = resolve_field(name, meta, props)
                if actual is None:
                    if local.get('properties', {}).get(name) is not None:
                        return False
                    continue
                if not compare_value(local.get('properties', {}).get(name), props.get(actual), meta.get('type', ''))[0]:
                    return False
            return bool(local.get('geometry') is not None and gee.get('geometry') is not None and geometry_result(local['geometry'], gee['geometry'])['strict'])
        for key, locals_group in local_groups.items():
            gees_group = target_matches.get(key, [])
            edges = [[j for j, gee in enumerate(gees_group) if pair_compatible(local, gee)] for local in locals_group]
            chosen = {}
            def assign(i, used):
                if i == len(locals_group):
                    return True
                for j in edges[i]:
                    if j not in used and assign(i + 1, used | {j}):
                        chosen[i] = j
                        return True
                return False
            equal_multiset = len(locals_group) == len(gees_group) and assign(0, set())
            if equal_multiset:
                for i, j in chosen.items():
                    raw_pairing[id(locals_group[i])] = gees_group[j]
            raw_groups.append({'key': key, 'local_multiplicity': len(locals_group), 'gee_multiplicity': len(gees_group), 'complete_attribute_geometry_multiset_equal': bool(equal_multiset), 'individual_identity_asserted': False})
            if not equal_multiset:
                comparison_issues.append(f'raw complete attribute/geometry multiset mismatch for compound key {key}')
    for local in features:
        local_id = str(local.get('local_id'))
        if dataset == 'grwl-raw':
            k = compound(local)
            matches = target_matches.get(k, [])
            gee = raw_pairing.get(id(local), matches[0] if matches else None)
        else:
            matches = target_matches.get(local_id, [])
            gee = matches[0] if matches else None
        p = gee.get('properties', {}) if gee else {}
        row = {'local_id': local.get('local_id'), 'attribute_mismatches': [], 'geometry': None}
        for name, meta in active_fields.items():
            if meta.get('role') == 'geometry_derived' and (not p or resolve_field(name, meta, p) is None):
                field_coverage[name]['missing'] += 1
                continue
            actual = resolve_field(name, meta, p) if p else None
            if actual is None:
                field_coverage[name]['missing'] += 1
                if local.get('properties', {}).get(name) is not None and meta.get('role') == 'source':
                    row['attribute_mismatches'].append({'field': name, 'gee_field': None, 'local': local.get('properties', {}).get(name), 'gee': None, 'reason': 'required_nonnull_field_missing'})
                continue
            field_coverage[name]['matched_name'] = actual
            field_coverage[name]['coverage'] += 1
            local_value = local.get('properties', {}).get(name)
            gee_value = p.get(actual)
            ok, kind, detail = compare_value(local_value, gee_value, meta.get('type', ''))
            field_coverage[name][kind] += 1
            cells[kind] += 1
            if not ok:
                row['attribute_mismatches'].append({'field': name, 'gee_field': actual, 'local': local_value, 'gee': gee_value, 'reason': detail})
        if local.get('geometry') is None or gee is None:
            gr = {'strict': False, 'diagnostic': 'incomplete', 'reason': 'missing_feature_or_geometry'}
        else:
            gr = geometry_result(local.get('geometry'), gee.get('geometry'))
        row['geometry'] = gr
        geom_results.append(gr)
        if dataset == 'grwl-raw':
            row['individual_identity_asserted'] = False
        records.append(row)
    if dataset == 'grwl-raw':
        missing_selected = sum(max(0, n - len(target_matches.get(k, []))) for k, n in wanted.items())
    else:
        matched_local_ids = set(target_matches)
        missing_selected = sum(str(f.get('local_id')) not in matched_local_ids for f in features)
    attribute_failures = sum(len(r.get('attribute_mismatches', [])) for r in records)
    strict_geom_pass = sum(bool(g.get('strict')) for g in geom_results)
    strict_geom_fail = len(geom_results) - strict_geom_pass
    # Missing required source attributes are failures; absent optional geometry-derived properties are coverage gaps.
    missing_required = sum(1 for row in records for mm in row.get('attribute_mismatches', []) if mm.get('reason') == 'required_nonnull_field_missing')
    attr_pass = missing_required == 0 and attribute_failures == 0 and missing_selected == 0
    overall = count_ok and stable_metadata and not issues and not comparison_issues and attr_pass and strict_geom_fail == 0
    status = 'sampled_pass' if overall else 'sampled_fail'
    if not count_ok or not stable_metadata or any('binding' in x or 'hash/size' in x or 'pagination' in x for x in issues):
        status = 'invalid_capture_or_binding'
    capture_receipt = read_json(capture_dir / 'capture.json') if (capture_dir / 'capture.json').is_file() else {}
    def sample_values(name):
        wanted = name.casefold()
        vals = set()
        for f in features:
            props = f.get('properties', {})
            key = next((k for k in props if k.casefold() == wanted), None)
            if key is not None and props[key] is not None:
                vals.add(str(props[key]))
        return sorted(vals)
    coords = []
    for f in features:
        try:
            coords.extend(geom_coords(f.get('geometry')))
        except Exception:
            pass
    context = {'countries': sample_values('Country'), 'continents': sample_values('Continent'), 'source_tiles': sample_values('source_tile'), 'coordinate_bounds_wgs84': None}
    if coords:
        context['coordinate_bounds_wgs84'] = {'west': min(x[0] for x in coords), 'south': min(x[1] for x in coords), 'east': max(x[0] for x in coords), 'north': max(x[1] for x in coords)}
    return {
        'schema_version': 1, 'dataset_id': dataset, 'status': status,
        'claim': 'systematic global coverage sample; not statistical random sampling, exhaustive feature parity, or independent scientific accuracy',
        'provenance': {'sample_sha256': sha(sample_path), 'sample_parquet_sha256': sample.get('source', {}).get('parquet_sha256'), 'sample_manifest_sha256': sample.get('source', {}).get('manifest_sha256'), 'plan_sha256': sha(plan_path), 'criteria_sha256': sha(criteria_path), 'capture_plan_sha256': capture_receipt.get('plan_sha256'), 'capture_status': capture_receipt.get('status'), 'capture_script_sha256': capture_receipt.get('script_sha256'), 'capture_lock_sha256': capture_receipt.get('lock_sha256'), 'capture_git_commit': capture_receipt.get('git_commit'), 'capture_environment': capture_receipt.get('environment'), 'stable_before_after_metadata': stable_metadata, 'manifest_asset_pin_check': 'sample declarations reported; comparator does not independently reopen the manifest', 'historical_script_lock_check': 'recorded hashes reported; comparator does not verify Git blobs'},
        'count': {'local_row_count': local_count, 'frozen_expected_count': frozen_count, 'gee_synchronous_count': gee_count, 'pass': count_ok},
        'sample_context': context, 'absent_local_extra_ids': sample.get('absent_local_extra_ids', []),
        'identity': {'matching': 'raw compound-key multiset; no per-row identity asserted' if dataset == 'grwl-raw' else ('Hylak_id' if dataset.startswith(('hydrolakes', 'lakeatlas')) else 'GOID'), 'requested_sample_count': len(features), 'matched_sample_count': len(features) - missing_selected, 'missing_sample_count': missing_selected, 'repeated_identical_ids_across_raw_queries': repeated_identical, 'conflicting_duplicate_gee_feature_ids': len(set(conflicting_ids)), 'extra_gee_records': extras},
        'fields': {'source': {n: v for n, v in field_coverage.items() if active_fields[n].get('role') == 'source'}, 'geometry_derived': {n: v for n, v in field_coverage.items() if active_fields[n].get('role') == 'geometry_derived'}, 'excluded': excluded, 'gee_extra_property_names': sorted({k for p in properties for k in p if not any(resolve_field(n, m, {k: None}) == k for n, m in active_fields.items())})},
        'attributes': {'pass': attr_pass, 'cells': dict(cells), 'missing_required_cells': missing_required, 'mismatch_count': attribute_failures},
        'geometry': {'strict_pass': strict_geom_pass, 'strict_fail': strict_geom_fail, 'strict_passed': strict_geom_fail == 0, 'diagnostic_pass': sum(g.get('diagnostic_pass') is True for g in geom_results), 'diagnostic_fail': sum(g.get('diagnostic_pass') is False for g in geom_results), 'diagnostic_incomplete': sum('diagnostic_pass' not in g for g in geom_results), 'results': geom_results, 'raw_compound_key_groups': raw_groups if dataset == 'grwl-raw' else []},
        'capture_validation': {'pass': not issues, 'issues': issues}, 'comparison_failures': comparison_issues,
        'examples': [r for r in records if r.get('attribute_mismatches') or (r.get('geometry') and not r['geometry'].get('strict'))][:50],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['sample', 'capture', 'plan', 'criteria', 'report']:
        ap.add_argument('--' + name, required=True, type=Path)
    a = ap.parse_args(argv)
    if a.report.exists():
        ap.error(f'refusing to overwrite existing report: {a.report}')
    if shape is None:
        ap.error('shapely and pyproj are required; use scripts/gee_validation/.venv/bin/python')
    sample, plan, criteria = read_json(a.sample), read_json(a.plan), read_json(a.criteria)
    from provenance import verify_provenance
    independent = verify_provenance(a.sample, a.capture, a.plan)
    report = build_report(a.sample, sample, a.capture, a.plan, plan, a.criteria, criteria)
    report['provenance']['independent_verification'] = independent
    report['provenance']['manifest_asset_pin_check'] = independent['status']
    report['provenance']['historical_script_lock_check'] = independent['status']
    if independent['status'] != 'passed':
        report['status'] = 'invalid_capture_or_binding'
        report['capture_validation']['pass'] = False
        report['capture_validation']['issues'].append('independent source/historical provenance verification failed')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(a.report), 'capture_validation': report['capture_validation']['pass']}))
    return 0 if report['status'] == 'sampled_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Capture bounded public STAC metadata for the SWOT PLD scientific collection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


HOST = 'hydroweb.next.theia-land.fr'
COLLECTION_URL = f'https://{HOST}/api/catalog/stac/collections/SWOT_PRIOR_LAKE_DATABASE'
ITEMS_URL = COLLECTION_URL + '/items?limit=10'
MAX_RESPONSE_BYTES = 10_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_PAGES = 32
RANGE_PROBE_LIMIT = 32
USER_AGENT = 'data-publications-metadata-review/1.0'


def _safe_url(url):
    """Return an HTTPS URL with auth-like query fields removed."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != HOST or parsed.username or parsed.password:
        return None, True
    safe_query = []
    redacted = False
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower().replace('-', '_')
        if any(marker in lowered for marker in ('token', 'signature', 'credential', 'authorization', 'api_key', 'apikey', 'secret', 'expires')) or lowered.startswith('x_amz_'):
            redacted = True
        else:
            safe_query.append((key, value))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                                    urllib.parse.urlencode(safe_query), '')), redacted


def _safe_page_url(url):
    safe, redacted = _safe_url(url)
    if safe is None or redacted:
        raise ValueError('next link was not a credential-free same-host HTTPS URL')
    return safe


def _open_request(opener, url, *, method='GET', headers=None, timeout=25):
    req_headers = {'Accept-Encoding': 'identity', 'User-Agent': USER_AGENT}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method=method)
    return opener(request, timeout=timeout)


def _fetch_collection(opener, total_bytes=0):
    """Fetch the small collection document so edition and license are pinned."""
    safe_url = _safe_page_url(COLLECTION_URL)
    page = {'url': safe_url, 'http_status': None, 'response_bytes': 0,
            'response_sha256': None}
    remaining = MAX_TOTAL_BYTES - total_bytes
    if remaining <= 0:
        return None, page, total_bytes, [{'type': 'total_byte_cap',
                                         'message': 'metadata byte cap reached before collection document'}]
    read_limit = min(MAX_RESPONSE_BYTES, remaining)
    try:
        with _open_request(opener, safe_url, headers={'Accept': 'application/json'}) as response:
            page['http_status'] = response.status
            content_length = response.headers.get('Content-Length')
            if content_length is not None and int(content_length) > read_limit:
                page['content_length_bytes'] = int(content_length)
                return None, page, total_bytes, [{'type': 'response_byte_cap',
                                                  'message': 'collection Content-Length exceeds metadata budget'}]
            body = response.read(read_limit)
            page['response_bytes'] = len(body)
            page['response_sha256'] = hashlib.sha256(body).hexdigest()
            total_bytes += len(body)
            if len(body) == read_limit and (content_length is None or int(content_length) != len(body)):
                return None, page, total_bytes, [{'type': 'response_byte_cap',
                                                  'message': 'collection reached byte limit before bounded JSON completion'}]
            document = json.loads(body)
            summaries = document.get('summaries') or {}
            providers = document.get('providers') or []
            projection = {
                'id': document.get('id'),
                'title': document.get('title'),
                'license': document.get('license'),
                'providers': [{'name': provider.get('name'), 'roles': provider.get('roles')}
                              for provider in providers],
                'release': summaries.get('release'),
                'total_items': summaries.get('total_items'),
                'collection_type': summaries.get('collection_type'),
                'file_format': summaries.get('dcs:data_file_format'),
                'data_type': summaries.get('hydro:data_type'),
                'layers': [{'name': layer.get('name'), 'asset_key': layer.get('asset_key')}
                           for variable in summaries.get('hydro:variables', [])
                           for layer in variable.get('layers', [])],
            }
            return projection, page, total_bytes, []
    except urllib.error.HTTPError as error:
        page['http_status'] = error.code
        return None, page, total_bytes, [{'type': 'http_error', 'status': error.code,
                                         'message': 'collection metadata request failed'}]
    except Exception as error:
        return None, page, total_bytes, [{'type': type(error).__name__,
                                         'message': 'collection metadata request or parsing failed'}]


def fetch_pages(opener=urllib.request.urlopen, first_url=ITEMS_URL):
    """Read only JSON item metadata, enforcing per-page and aggregate byte caps."""
    features = []
    pages = []
    failures = []
    next_url = _safe_page_url(first_url)
    total_bytes = 0
    seen_pages = set()
    expected_matched = None
    collection, collection_page, total_bytes, collection_failures = _fetch_collection(opener, total_bytes)
    pages.append(collection_page)
    failures.extend(collection_failures)

    while next_url:
        if len(pages) >= MAX_PAGES:
            failures.append({'type': 'page_cap', 'message': f'more than {MAX_PAGES} pages'})
            break
        if next_url in seen_pages:
            failures.append({'type': 'pagination_loop', 'message': 'repeated page URL'})
            break
        seen_pages.add(next_url)
        remaining = MAX_TOTAL_BYTES - total_bytes
        if remaining <= 0:
            failures.append({'type': 'total_byte_cap', 'message': 'metadata byte cap reached'})
            break
        read_limit = min(MAX_RESPONSE_BYTES, remaining)
        page = {'url': next_url, 'http_status': None, 'response_bytes': 0,
                'response_sha256': None}
        try:
            with _open_request(opener, next_url, headers={'Accept': 'application/geo+json'}) as response:
                page['http_status'] = response.status
                content_length = response.headers.get('Content-Length')
                if content_length is not None and int(content_length) > read_limit:
                    page['content_length_bytes'] = int(content_length)
                    failures.append({'type': 'response_byte_cap', 'message': 'page Content-Length exceeds remaining metadata budget'})
                    pages.append(page)
                    break
                body = response.read(read_limit)
                page['response_bytes'] = len(body)
                page['response_sha256'] = hashlib.sha256(body).hexdigest()
                total_bytes += len(body)
                if len(body) == read_limit and (content_length is None or int(content_length) != len(body)):
                    failures.append({'type': 'response_byte_cap', 'message': 'page reached byte limit before bounded JSON completion'})
                    pages.append(page)
                    break
                document = json.loads(body)
                new_features = document.get('features')
                if not isinstance(new_features, list):
                    raise ValueError('STAC page did not contain a features list')
                features.extend(new_features)
                context = document.get('context') or {}
                matched = context.get('matched', document.get('numberMatched'))
                if matched is not None:
                    if expected_matched is not None and matched != expected_matched:
                        failures.append({'type': 'count_mismatch', 'message': 'numberMatched changed between pages'})
                    expected_matched = matched
                pages.append(page)
                link = next((entry for entry in document.get('links', [])
                             if entry.get('rel') == 'next'), None)
                next_url = _safe_page_url(link.get('href')) if link else None
        except urllib.error.HTTPError as error:
            page['http_status'] = error.code
            failures.append({'type': 'http_error', 'status': error.code,
                             'message': 'metadata page request failed'})
            pages.append(page)
            break
        except Exception as error:
            failures.append({'type': type(error).__name__,
                             'message': 'metadata page request or parsing failed'})
            pages.append(page)
            break

    return {'features': features, 'pages': pages, 'failures': failures,
            'metadata_response_bytes': total_bytes, 'collection': collection,
            'number_matched': expected_matched}


def _edition(feature, asset):
    name = asset.get('title') or ''
    item_id = feature.get('id') or ''
    editions = set()
    for version in ('203', '202'):
        if name.endswith(f'_v{version}.sqlite') or f'_v{version}@' in item_id:
            editions.add('v' + version)
    if len(editions) > 1:
        raise ValueError('conflicting item and filename editions')
    return next(iter(editions)) if editions else 'other'


def _tile_identifier(filename):
    match = re.search(r'(?:DatabaseSci)_([A-Z]{2})_(\d{2})_', filename or '')
    return f'{match.group(1)}_{match.group(2)}' if match else None


def _md5_from_description(description):
    match = re.search(r'Checksum\s+MD5:\s*([0-9a-fA-F]{32})\b', description or '', re.I)
    return match.group(1).lower() if match else None


def _data_asset(feature):
    assets = feature.get('assets') or {}
    candidates = [(key, value) for key, value in assets.items()
                  if isinstance(value, dict) and
                  ('data' in (value.get('roles') or []) or
                   str(value.get('title', '')).lower().endswith('.sqlite'))]
    if len(candidates) != 1:
        return None, f'expected one SQLite data asset, found {len(candidates)}'
    return candidates[0], None


def project_inventory(features):
    """Project the mixed collection to v2.03 assets and report older editions."""
    seen_ids = set()
    duplicate_ids = []
    projected = []
    seen_current_tiles = set()
    counts = {'v203': 0, 'v202': 0, 'other': 0}
    older_bytes_known = 0
    malformed = []
    for feature in features:
        item_id = feature.get('id')
        if item_id in seen_ids:
            duplicate_ids.append(item_id)
            continue
        seen_ids.add(item_id)
        pair, error = _data_asset(feature)
        if error:
            malformed.append({'item_id': item_id, 'message': error})
            continue
        _, asset = pair
        edition = _edition(feature, asset)
        counts[edition] += 1
        filename = asset.get('title')
        url, url_redacted = _safe_url(asset.get('href', ''))
        if edition == 'v202' and isinstance(asset.get('file:size'), int):
            older_bytes_known += asset['file:size']
        if edition != 'v203':
            continue
        tile_id = _tile_identifier(filename)
        if tile_id is None or tile_id in seen_current_tiles:
            raise ValueError('missing or duplicate v2.03 tile identifier')
        seen_current_tiles.add(tile_id)
        projected.append({
            'item_id': item_id,
            'tile_identifier': _tile_identifier(filename),
            'filename': filename,
            'file_url': url,
            'file_url_auth_fields_redacted': url_redacted,
            'provider_file_size_bytes': asset.get('file:size'),
            'provider_file_checksum_multihash': asset.get('file:checksum'),
            'provider_file_checksum_md5': _md5_from_description(asset.get('description')),
            'product_datetime': (feature.get('properties') or {}).get('datetime'),
            'processing_chain_version': ((feature.get('properties') or {}).get('processing:software') or {}).get('chain_version'),
            'online_flag_in_asset_description': 'Is online: true' in (asset.get('description') or ''),
        })
    if duplicate_ids:
        raise ValueError('duplicate item IDs: ' + ', '.join(str(x) for x in sorted(set(duplicate_ids))))
    if malformed:
        raise ValueError('invalid data assets: ' + json.dumps(malformed, sort_keys=True))

    unknown_sizes = [item['item_id'] for item in projected
                     if type(item['provider_file_size_bytes']) is not int or item['provider_file_size_bytes'] <= 0]
    missing_checksums = [item['item_id'] for item in projected
                         if not item.get('provider_file_checksum_multihash')]
    missing_md5 = [item['item_id'] for item in projected
                   if not item.get('provider_file_checksum_md5')]
    missing_urls = [item['item_id'] for item in projected if not item.get('file_url')]
    known_sum = sum(item['provider_file_size_bytes'] for item in projected
                    if type(item['provider_file_size_bytes']) is int and item['provider_file_size_bytes'] > 0)
    exact_sum = None if unknown_sizes else known_sum
    region_counts = {}
    for item in projected:
        tile = item.get('tile_identifier')
        if tile:
            region = tile.split('_', 1)[0]
            region_counts[region] = region_counts.get(region, 0) + 1
    return {
        'v203_items': projected,
        'v203_item_count': len(projected),
        'v202_older_item_count': counts['v202'],
        'other_edition_item_count': counts['other'],
        'all_item_count': sum(counts.values()),
        'v202_older_provider_bytes_known_sum': older_bytes_known,
        'v203_provider_file_size_bytes_known_sum': known_sum,
        'v203_provider_file_size_bytes_exact_sum': exact_sum,
        'v203_unknown_size_item_ids': unknown_sizes,
        'v203_missing_provider_checksum_item_ids': missing_checksums,
        'v203_missing_md5_item_ids': missing_md5,
        'v203_missing_stable_file_url_item_ids': missing_urls,
        'v203_region_counts': dict(sorted(region_counts.items())),
        'v203_region_count': len(region_counts),
    }


def _range_probe(asset, opener=urllib.request.urlopen):
    """Request at most 16 bytes from a candidate asset; never retain arbitrary bodies."""
    url, redacted = _safe_url(asset.get('href', ''))
    result = {'method': 'GET', 'range': 'bytes=0-15', 'url': url,
              'url_auth_fields_redacted': redacted, 'body_bytes_read': 0,
              'sqlite_header_observed': False}
    if url is None or redacted:
        result.update({'status': None, 'error': 'no credential-free stable asset URL'})
        return result
    try:
        with _open_request(opener, url, headers={'Accept': 'application/octet-stream, application/json',
                                                 'Range': 'bytes=0-15'}) as response:
            result['status'] = response.status
            result['content_type'] = response.headers.get('Content-Type')
            result['content_range'] = response.headers.get('Content-Range')
            body = response.read(RANGE_PROBE_LIMIT)
            result['body_bytes_read'] = len(body)
            _retain_probe_body(result, body)
    except urllib.error.HTTPError as error:
        result['status'] = error.code
        result['content_type'] = error.headers.get('Content-Type')
        result['content_range'] = error.headers.get('Content-Range')
        body = error.read(RANGE_PROBE_LIMIT)
        result['body_bytes_read'] = len(body)
        _retain_probe_body(result, body)
    except Exception as error:
        result['status'] = None
        result['error'] = type(error).__name__
    return result


def _retain_probe_body(result, body):
    if len(body) > RANGE_PROBE_LIMIT:
        result['body_limit_exceeded'] = True
        body = body[:RANGE_PROBE_LIMIT]
    content_type = (result.get('content_type') or '').lower()
    if 'json' in content_type:
        try:
            parsed = json.loads(body)
            safe = {key: value for key, value in parsed.items()
                    if key.lower() in ('error', 'message', 'detail', 'status') and
                    isinstance(value, (str, int, float, bool, type(None)))} if isinstance(parsed, dict) else parsed
            result['nonsecret_json_prefix'] = json.dumps(safe, separators=(',', ':'))[:160]
        except Exception:
            prefix = body[:RANGE_PROBE_LIMIT].decode('utf-8', errors='replace')
            result['nonsecret_json_prefix'] = (prefix if not re.search(
                r'token|signature|secret|api.?key|authorization|https?://', prefix, re.I)
                else '[redacted sensitive JSON prefix]')
    elif 'octet-stream' in content_type or 'sqlite' in content_type:
        result['sqlite_header_observed'] = body.startswith(b'SQLite format 3\x00')


def _build_result(capture):
    try:
        inventory = project_inventory(capture['features'])
        failures = list(capture['failures'])
        count_complete = (capture.get('number_matched') is not None and
                          capture['number_matched'] == inventory['all_item_count'])
        if not count_complete:
            failures.append({'type': 'item_count_mismatch',
                             'message': f"STAC matched {capture['number_matched']} but received {inventory['all_item_count']} unique items"})
        collection = capture.get('collection') or {}
        collection_consistent = (collection.get('release') == '2.03 Sci' and
                                 collection.get('total_items') == inventory['all_item_count'] and
                                 collection.get('license') == 'ETALAB 2.0')
        if not collection_consistent:
            failures.append({'type': 'collection_metadata_mismatch',
                             'message': 'collection release, license, or item count does not match reviewed scope'})
        complete = (not failures and collection_consistent and count_complete and
                    inventory['v203_unknown_size_item_ids'] == [] and
                    inventory['v203_missing_provider_checksum_item_ids'] == [] and
                    inventory['v203_missing_md5_item_ids'] == [] and
                    inventory['v203_missing_stable_file_url_item_ids'] == [] and
                    inventory['other_edition_item_count'] == 0 and
                    inventory['v203_region_count'] == 9)
        status = 'metadata_qualified_provider_declared_bytes' if complete else 'metadata_inventory_incomplete_or_unknown'
        smallest = min((item for item in inventory['v203_items']
                        if isinstance(item['provider_file_size_bytes'], int)),
                       key=lambda item: item['provider_file_size_bytes'], default=None)
        probe = None
        if smallest is not None and smallest['provider_file_size_bytes'] < 128 * 1024 * 1024:
            source_asset = next((a for f in capture['features'] if f.get('id') == smallest['item_id']
                                 for a in (f.get('assets') or {}).values()
                                 if a.get('title') == smallest['filename']), None)
            if source_asset:
                probe = _range_probe(source_asset, capture.get('opener', urllib.request.urlopen))
        return {
            'captured_at_utc': datetime.now(timezone.utc).isoformat(),
            'source': {'collection_url': COLLECTION_URL, 'items_url': ITEMS_URL,
                       'method': 'unauthenticated public HTTPS GET, paginated STAC items'},
            'status': status,
            'qualification_scope': 'v2.03 scientific SQLite tile inventory only; mixed v2.02 items counted separately',
            'inventory_basis': 'provider-declared STAC metadata; file bytes and checksums were not independently verified by download',
            'data_downloaded': False,
            'collection_metadata': collection,
            'max_response_bytes': MAX_RESPONSE_BYTES,
            'max_total_metadata_response_bytes': MAX_TOTAL_BYTES,
            'metadata_response_bytes': capture['metadata_response_bytes'],
            'page_count': len(capture['pages']),
            'pages': capture['pages'],
            'counts_and_sizes': {key: value for key, value in inventory.items() if key != 'v203_items'},
            'v203_items': inventory['v203_items'],
            'smallest_v203_asset_range_probe': probe,
            'failures': failures,
        }
    except Exception as error:
        return {
            'captured_at_utc': datetime.now(timezone.utc).isoformat(),
            'source': {'collection_url': COLLECTION_URL, 'items_url': ITEMS_URL,
                       'method': 'unauthenticated public HTTPS GET, paginated STAC items'},
            'status': 'capture_failed', 'data_downloaded': False,
            'metadata_response_bytes': capture.get('metadata_response_bytes', 0),
            'page_count': len(capture.get('pages', [])), 'pages': capture.get('pages', []),
            'v203_items': [], 'failures': list(capture.get('failures', [])) +
            [{'type': type(error).__name__, 'message': str(error)[:1000]}],
        }


def capture_to_path(output, opener=urllib.request.urlopen):
    """Refuse existing outputs before making any request, then persist a capture."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to replace a prior SWOT metadata capture')
    capture = fetch_pages(opener=opener)
    capture['opener'] = opener
    result = _build_result(capture)
    # The capture is metadata only and should be far below the 10 MB artifact cap.
    payload = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if len(payload.encode('utf-8')) > MAX_RESPONSE_BYTES:
        raise ValueError('projected capture exceeds 10 MB output cap')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='new output path; existing captures are never overwritten')
    args = parser.parse_args(argv)
    try:
        result = capture_to_path(args.output)
    except FileExistsError as error:
        parser.error(str(error))
    print(json.dumps({'status': result.get('status'),
                      'v203_item_count': result.get('counts_and_sizes', {}).get('v203_item_count'),
                      'v203_provider_file_size_bytes_exact_sum': result.get('counts_and_sizes', {}).get('v203_provider_file_size_bytes_exact_sum'),
                      'metadata_response_bytes': result.get('metadata_response_bytes'),
                      'failures': result.get('failures', [])}, sort_keys=True))
    return 0 if result.get('status') == 'metadata_qualified_provider_declared_bytes' else 1


if __name__ == '__main__':
    raise SystemExit(main())

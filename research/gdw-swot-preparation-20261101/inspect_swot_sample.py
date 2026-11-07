#!/usr/bin/env python3
"""Download and inspect one bounded SWOT PLD v2.03 SQLite tile."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import urllib.parse
import urllib.request


EXPECTED_TILE = 'AU_55'
EXPECTED_BYTES = 14_954_496
MAX_FILE_BYTES = 128 * 1024 * 1024
MIN_FREE_BYTES = 40 * 1024**3
STOP_FREE_BYTES = 10 * 1024**3
MAX_REPORT_BYTES = 10_000_000
DEFAULT_STORAGE_DIR = Path('.local/swot-qualification-20261101/AU_55')
HYDROWEB_HOST = 'hydroweb.next.theia-land.fr'
USER_AGENT = 'data-publications-source-qualification/1.0'


def _credential_free_url(value):
    parsed = urllib.parse.urlsplit(value or '')
    if parsed.scheme != 'https' or parsed.hostname != HYDROWEB_HOST or parsed.username or parsed.password:
        return None
    safe_query = []
    for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower().replace('-', '_')
        if (any(word in key_l for word in ('token', 'signature', 'credential', 'authorization', 'api_key', 'apikey', 'secret', 'expires'))
                or key_l.startswith('x_amz_')):
            return None
        safe_query.append((key, val))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                                    urllib.parse.urlencode(safe_query), ''))


def select_sample(inventory):
    candidates = [item for item in inventory.get('v203_items', [])
                  if item.get('tile_identifier') == EXPECTED_TILE]
    if len(candidates) != 1:
        raise ValueError(f'expected one v2.03 {EXPECTED_TILE} item, found {len(candidates)}')
    item = candidates[0]
    if item.get('provider_file_size_bytes') != EXPECTED_BYTES:
        raise ValueError(f'{EXPECTED_TILE} provider size changed from reviewed {EXPECTED_BYTES} bytes')
    url = _credential_free_url(item.get('file_url'))
    if url is None:
        raise ValueError('sample asset URL is not a credential-free same-host HTTPS URL')
    if not str(item.get('filename', '')).endswith('_v203.sqlite'):
        raise ValueError('selected item is not a v2.03 SQLite asset')
    if Path(item['filename']).name != item['filename'] or '/' in item['filename'] or '\\' in item['filename']:
        raise ValueError('source filename must be a basename without path separators')
    md5 = item.get('provider_file_checksum_md5')
    if not isinstance(md5, str) or not re.fullmatch(r'[0-9a-fA-F]{32}', md5):
        raise ValueError('sample has no valid provider-described MD5 checksum')
    if EXPECTED_BYTES > MAX_FILE_BYTES:
        raise ValueError('sample exceeds the 128 MiB file cap')
    return {**item, 'file_url': url, 'expected_md5': md5.lower()}


def _disk_status(path):
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return {'checked_path': str(probe), 'free_bytes': usage.free,
            'required_free_bytes': MIN_FREE_BYTES,
            'passes_40_gib_minimum': usage.free >= MIN_FREE_BYTES}


def _path_exists(path):
    """Path.exists misses dangling symlinks, which must also block overwrites."""
    return os.path.lexists(os.fspath(path))


def download_sample(item, destination, opener=urllib.request.urlopen):
    """Fetch exactly one file, retaining a partial .part on transfer failure."""
    destination = Path(destination)
    partial = destination.with_name(destination.name + '.part')
    if _path_exists(destination) or _path_exists(partial):
        raise FileExistsError('refusing to replace existing sample or partial file')
    headers = {'Accept': 'application/octet-stream', 'Accept-Encoding': 'identity',
               'User-Agent': USER_AGENT}
    request = urllib.request.Request(item['file_url'], headers=headers, method='GET')
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    received = 0
    min_free_bytes = None
    transfer = {'request_method': 'GET', 'http_status': None,
                'expected_size_bytes': item['provider_file_size_bytes'],
                'provider_md5': item['expected_md5'], 'response_bytes_written': 0,
                'partial_path': str(partial), 'file_path': str(destination),
                'stop_free_disk_bytes': STOP_FREE_BYTES}
    try:
        with opener(request, timeout=60) as response:
            transfer['http_status'] = response.status
            transfer['content_type'] = response.headers.get('Content-Type')
            transfer['content_length_bytes'] = (int(response.headers['Content-Length'])
                                                if response.headers.get('Content-Length') else None)
            if transfer['content_length_bytes'] is not None and transfer['content_length_bytes'] > MAX_FILE_BYTES:
                raise ValueError('response Content-Length exceeds 128 MiB file cap')
            if (transfer['content_length_bytes'] is not None and
                    transfer['content_length_bytes'] != item['provider_file_size_bytes']):
                raise ValueError('response Content-Length differs from provider-declared size')
            partial.parent.mkdir(parents=True, exist_ok=True)
            with partial.open('xb') as stream:
                while True:
                    disk = _disk_status(partial.parent)
                    free_now = disk['free_bytes']
                    min_free_bytes = free_now if min_free_bytes is None else min(min_free_bytes, free_now)
                    if free_now < STOP_FREE_BYTES:
                        transfer['failure'] = 'free disk space fell below the 10 GiB transfer floor'
                        break
                    expected_remaining = item['provider_file_size_bytes'] - received
                    if expected_remaining < 0:
                        transfer['failure'] = 'response exceeded provider-declared size'
                        break
                    allowance = min(1024 * 1024, expected_remaining + 1,
                                    MAX_FILE_BYTES - received + 1)
                    block = response.read(allowance)
                    if not block:
                        break
                    if received + len(block) > MAX_FILE_BYTES:
                        transfer['failure'] = 'response exceeded 128 MiB file cap; excess bytes were not written'
                        break
                    allowed = min(len(block), expected_remaining)
                    if allowed:
                        accepted = block[:allowed]
                        stream.write(accepted)
                        md5.update(accepted)
                        sha256.update(accepted)
                        received += len(accepted)
                    transfer['response_bytes_written'] = received
                    if len(block) > allowed:
                        transfer['failure'] = 'response exceeded provider-declared size; overflow byte was not retained'
                        transfer['overflow_bytes_observed'] = len(block) - allowed
                        break
                    disk = _disk_status(partial.parent)
                    free_now = disk['free_bytes']
                    min_free_bytes = free_now if min_free_bytes is None else min(min_free_bytes, free_now)
                    if free_now < STOP_FREE_BYTES:
                        transfer['failure'] = 'free disk space fell below the 10 GiB transfer floor'
                        break
                stream.flush()
                os.fsync(stream.fileno())
            transfer['minimum_free_disk_bytes_observed'] = min_free_bytes
        transfer['partial_file_preserved'] = partial.exists()
        if transfer.get('failure'):
            if partial.exists():
                transfer['partial_sha256'] = _hash_file(partial, 'sha256')
                transfer['partial_md5'] = _hash_file(partial, 'md5')
            return transfer
        transfer['computed_md5'] = md5.hexdigest()
        transfer['computed_sha256'] = sha256.hexdigest()
        if received != item['provider_file_size_bytes']:
            transfer['failure'] = 'download byte count differs from provider-declared size'
            return transfer
        if md5.hexdigest() != item['expected_md5']:
            transfer['failure'] = 'download MD5 does not match provider-described MD5'
            return transfer
        partial.rename(destination)
        transfer['partial_file_preserved'] = False
        transfer['file_path'] = str(destination)
        transfer['validated_file_bytes'] = received
        transfer['size_matches_provider'] = True
        transfer['md5_matches_provider'] = True
        return transfer
    except Exception as error:
        transfer['response_bytes_written'] = received
        transfer['partial_file_preserved'] = partial.exists()
        transfer['failure'] = type(error).__name__ + ': request or file validation failed'
        if partial.exists():
            transfer['partial_sha256'] = _hash_file(partial, 'sha256')
            transfer['partial_md5'] = _hash_file(partial, 'md5')
        return transfer


def _hash_file(path, algorithm):
    digest = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _quote_identifier(identifier):
    return '"' + str(identifier).replace('"', '""') + '"'


def inspect_sqlite(path):
    """Read SQLite metadata and ordinary table counts in immutable read-only mode."""
    path = Path(path).resolve()
    uri = 'file:' + urllib.parse.quote(str(path), safe='/') + '?mode=ro&immutable=1'
    result = {'path': str(path), 'mode': 'read-only immutable', 'quick_check': None,
              'tables': [], 'views': [], 'errors': []}
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        if hasattr(connection, 'enable_load_extension'):
            connection.enable_load_extension(False)
        connection.execute('PRAGMA query_only=ON')
        result['quick_check'] = [row[0] for row in connection.execute('PRAGMA quick_check')]
        objects = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY type,name").fetchall()
        for object_type, name, table_name, create_sql in objects:
            quoted = _quote_identifier(name)
            columns = [{'cid': row[0], 'name': row[1], 'type': row[2],
                        'not_null': bool(row[3]), 'default': row[4], 'primary_key_position': row[5]}
                       for row in connection.execute(f'PRAGMA table_info({quoted})')]
            foreign_keys = [{'id': row[0], 'sequence': row[1], 'referenced_table': row[2],
                             'from_column': row[3], 'to_column': row[4],
                             'on_update': row[5], 'on_delete': row[6], 'match': row[7]}
                            for row in connection.execute(f'PRAGMA foreign_key_list({quoted})')]
            record = {'name': name, 'table_name': table_name, 'create_sql': create_sql,
                      'columns': columns, 'foreign_keys': foreign_keys}
            if object_type == 'table':
                if create_sql and re.search(r'CREATE\s+VIRTUAL\s+TABLE', create_sql, re.I):
                    record['row_count'] = None
                    record['row_count_skipped'] = 'virtual table; no virtual table module invoked'
                else:
                    record['row_count'] = connection.execute(f'SELECT COUNT(*) FROM {quoted}').fetchone()[0]
                result['tables'].append(record)
            else:
                # A count query would execute the upstream view definition; inspect only its declared columns.
                record['row_count'] = None
                record['row_count_skipped'] = 'view query not executed'
                result['views'].append(record)
    except Exception as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error)[:1000]})
    finally:
        if connection is not None:
            connection.close()
    return result


def verify_download(transfer, inspector=inspect_sqlite):
    """Open a sample only after expected size and provider MD5 have both matched."""
    if transfer.get('failure'):
        return {'status': 'not_inspected_download_failure', 'errors': [transfer['failure']]}
    if not transfer.get('size_matches_provider') or not transfer.get('md5_matches_provider'):
        return {'status': 'not_inspected_checksum_or_size_mismatch',
                'errors': ['download size and provider MD5 must match before SQLite inspection']}
    result = inspector(transfer['file_path'])
    if result.get('quick_check') == ['ok'] and not result.get('errors'):
        result['status'] = 'inspected'
    else:
        if result.get('quick_check') != ['ok'] and not result.get('errors'):
            result.setdefault('errors', []).append(
                'SQLite PRAGMA quick_check did not return exactly ["ok"]')
        result['status'] = 'failed_sqlite_validation'
    return result


def capture_sample(inventory_path, output_path, storage_dir=DEFAULT_STORAGE_DIR,
                   opener=urllib.request.urlopen, inspector=inspect_sqlite):
    output_path = Path(output_path)
    if _path_exists(output_path):
        raise FileExistsError('refusing to replace an existing sample inspection report')
    inventory_path = Path(inventory_path)
    report = {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'ONE TILE ONLY: SWOT PLD scientific v2.03 AU_55; no global release claim and no conversion',
        'source_inventory_path': str(inventory_path),
        'source_inventory_sha256': None,
        'status': 'failed',
        'downloaded_product_files': 0,
        'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                        'platform': platform.platform()},
        'failures': [],
    }
    try:
        inventory_bytes = inventory_path.read_bytes()
        report['source_inventory_sha256'] = hashlib.sha256(inventory_bytes).hexdigest()
        inventory = json.loads(inventory_bytes)
        report['source_inventory_status'] = inventory.get('status')
        if inventory.get('status') != 'metadata_qualified_provider_declared_bytes':
            raise ValueError('saved source inventory is not metadata-qualified')
        item = select_sample(inventory)
        report['source_item'] = {key: item.get(key) for key in (
            'item_id', 'tile_identifier', 'filename', 'file_url',
            'provider_file_size_bytes', 'provider_file_checksum_multihash',
            'provider_file_checksum_md5')}
        report['storage_dir'] = str(storage_dir)
        destination = Path(storage_dir) / item['filename']
        partial = destination.with_name(destination.name + '.part')
        if _path_exists(destination) or _path_exists(partial):
            raise FileExistsError('refusing to replace existing sample data or partial file')
        disk = _disk_status(storage_dir)
        report['disk_check'] = disk
        if not disk['passes_40_gib_minimum']:
            raise OSError('free disk space is below the required 40 GiB before sample download')
        if item['provider_file_size_bytes'] > MAX_FILE_BYTES:
            raise ValueError('selected sample exceeds the 128 MiB transfer cap')
        report['transfer'] = download_sample(item, destination, opener=opener)
        report['downloaded_product_files'] = 1 if not report['transfer'].get('failure') else 0
        report['sqlite_inspection'] = verify_download(report['transfer'], inspector=inspector)
        if report['sqlite_inspection'].get('status') == 'inspected' and not report['sqlite_inspection'].get('errors'):
            report['status'] = 'one_tile_source_inspected'
        else:
            report['failures'].extend(report['transfer'].get('failure') and [report['transfer']['failure']] or [])
            report['failures'].extend(report['sqlite_inspection'].get('errors', []))
    except Exception as error:
        report['failures'].append({'type': type(error).__name__, 'message': str(error)[:1000]})
    payload = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if len(payload.encode('utf-8')) > MAX_REPORT_BYTES:
        raise ValueError('sample inspection report exceeds 10 MB cap')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True,
                        help='saved metadata-only SWOT inventory JSON')
    parser.add_argument('--output', type=Path, required=True,
                        help='new report path; existing reports are never overwritten')
    parser.add_argument('--storage-dir', type=Path, default=DEFAULT_STORAGE_DIR,
                        help=f'ignored local sample storage (default: {DEFAULT_STORAGE_DIR})')
    args = parser.parse_args(argv)
    try:
        report = capture_sample(args.inventory, args.output, args.storage_dir)
    except FileExistsError as error:
        parser.error(str(error))
    print(json.dumps({'status': report.get('status'),
                      'downloaded_product_files': report.get('downloaded_product_files'),
                      'failures': report.get('failures', [])}, sort_keys=True))
    return 0 if report.get('status') == 'one_tile_source_inspected' else 1


if __name__ == '__main__':
    raise SystemExit(main())

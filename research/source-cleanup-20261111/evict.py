"""Evict only the 22 approved, checksum-audited local Source copies."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import urllib.request

INVENTORY = "research/readme-cleanup-20261110/local-cache-inventory.json"
REMOTE = "research/readme-cleanup-20261110/remote-assets.json"

def stamp():
    return datetime.now(timezone.utc).isoformat()

def guard(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Not a regular file: {path}")
    return {"device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--expected-inventory-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume-from', type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    raw = (root / INVENTORY).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expected_inventory_sha256:
        raise ValueError('Inventory checksum differs')
    inventory = json.loads(raw)
    rows = inventory['files']
    if len(rows) != 22 or len({r['path'] for r in rows}) != 22:
        raise ValueError('Expected the exact 22-file inventory')
    if sum(r['logical_bytes'] for r in rows) != 38179645339:
        raise ValueError('Inventory total differs')
    prior_deleted = {}
    if args.resume_from:
        previous = json.loads(args.resume_from.read_text())
        if previous.get('inventory_sha256') != digest or previous.get('execute') is not True:
            raise ValueError('Resume receipt does not bind this inventory')
        prior_deleted = {r['path']: r for r in previous['files'] if r['status'] == 'deleted'}
        if set(prior_deleted) - {r['path'] for r in rows}:
            raise ValueError('Resume receipt includes unapproved paths')
    for row in rows:
        path = root / row['path']
        if (not row['path'].startswith('.local/') or path.resolve() != path
                or not path.is_relative_to(root / '.local')
                or path.suffix not in {'.parquet', '.pmtiles'}):
            raise ValueError(f"Unsafe inventory path: {row['path']}")
        if row['path'] in prior_deleted:
            if path.exists() or prior_deleted[row['path']]['sha256'] != row['sha256']:
                raise ValueError('Previously evicted file reappeared or receipt differs')
        elif row['local_hash_status'] != 'matched' or guard(path) != row['stat_guard']:
            raise ValueError(f"Changed file requires a new hash audit: {row['path']}")
        proof = json.loads((root / row['remote_receipt']).read_text())
        if (proof['expected_sha256'] != row['sha256']
                or proof['remote_sha256'] != row['sha256']
                or proof['expected_size_bytes'] != row['logical_bytes']
                or row['remote_url'] != 'https://data.source.coop/' + proof['bucket'] + '/' + proof['object_key']):
            raise ValueError(f"Remote checksum receipt differs: {row['path']}")
    old_heads = {r['url']: r for r in json.loads((root / REMOTE).read_text())['assets']}
    remote_checks = []
    for url in sorted({r['remote_url'] for r in rows}):
        previous = old_heads[url]
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30) as response:
            current = {'url': url, 'status': response.status,
                       'size_bytes': int(response.headers['Content-Length']),
                       'etag': response.headers.get('ETag'),
                       'last_modified': response.headers.get('Last-Modified')}
        if (current['status'] != 200 or current['size_bytes'] != previous['expected_size_bytes']
                or current['etag'] != previous['etag']
                or current['last_modified'] != previous['last_modified']):
            raise ValueError(f'Remote object changed or unavailable: {url}')
        remote_checks.append(current)
    receipt = {'schema_version': 1, 'started_at': stamp(),
               'authorization': 'User go ahead after recommendation to remove all 22 verified hosted copies.',
               'inventory': INVENTORY, 'inventory_sha256': digest,
               'status': 'preflight_passed', 'execute': args.execute,
               'files_selected': len(rows), 'selected_logical_bytes': sum(r['logical_bytes'] for r in rows),
               'remote_checks': remote_checks, 'files': list(prior_deleted.values()),
               'resumed_from': str(args.resume_from) if args.resume_from else None,
               'free_bytes_before': shutil.disk_usage(root).free,
               'preserved': 'All files outside these exact 22 inventory paths, including raw inputs, small package metadata, reports and scripts.',
               'space_caveat': 'Free-space changes include concurrent activity and APFS clone/snapshot behavior.'}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    def save():
        temporary = args.receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(args.receipt)
    if args.execute:
        try:
            for row in rows:
                if row['path'] in prior_deleted:
                    continue
                path = root / row['path']
                if path.resolve() != path or guard(path) != row['stat_guard']:
                    raise ValueError(f"File changed after preflight: {row['path']}")
                parent_stat = path.parent.stat()
                parent_mode = stat.S_IMODE(parent_stat.st_mode)
                if parent_stat.st_uid != os.getuid():
                    raise ValueError('Parent directory not owned by current user')
                try:
                    if not parent_mode & stat.S_IWUSR:
                        path.parent.chmod(parent_mode | stat.S_IWUSR)
                    path.unlink()
                finally:
                    if stat.S_IMODE(path.parent.stat().st_mode) != parent_mode:
                        path.parent.chmod(parent_mode)
                receipt['files'].append({'path': row['path'], 'logical_bytes': row['logical_bytes'],
                                         'sha256': row['sha256'], 'status': 'deleted'})
                save()
            if any((root / r['path']).exists() for r in rows):
                raise ValueError('An inventoried path still exists')
            receipt['status'] = 'complete'
        except Exception as exc:
            receipt['status'] = 'partial_failure'
            receipt['error'] = str(exc)
            receipt['files_deleted'] = len(receipt['files'])
            receipt['deleted_logical_bytes'] = sum(r['logical_bytes'] for r in receipt['files'])
            receipt['free_bytes_after'] = shutil.disk_usage(root).free
            save()
            raise
    receipt['files_deleted'] = len(receipt['files'])
    receipt['deleted_logical_bytes'] = sum(r['logical_bytes'] for r in receipt['files'])
    receipt['free_bytes_after'] = shutil.disk_usage(root).free
    receipt['completed_at'] = stamp()
    save()
    print(json.dumps({k: receipt[k] for k in ('status', 'files_deleted', 'deleted_logical_bytes', 'free_bytes_before', 'free_bytes_after')}))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Verify a downloaded Pages tar artifact and anonymous canonical URLs against a plan."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from urllib.request import Request, urlopen


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--artifact', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit('Report already exists')
    raw = args.plan.read_bytes()
    plan = json.loads(raw)
    if plan['destination'] != 'github-pages://nthh/data-publications/':
        raise SystemExit('Unexpected publication destination')
    expected = {}
    for entry in plan['files']:
        path = PurePosixPath(entry['path'])
        if path.is_absolute() or '..' in path.parts or not entry['path'].startswith('catalog/'):
            raise SystemExit('Unsafe planned path')
        relative = str(path.relative_to('catalog'))
        if (relative in expected or entry['target_url'] != 'https://nthh.github.io/data-publications/' + relative
                or not 0 < entry['size_bytes'] <= 10 * 1024 * 1024):
            raise SystemExit('Invalid or duplicate planned asset')
        expected[relative] = entry
    report = {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Exact Pages metadata artifact plus canonical anonymous GETs; no analytical data reads.',
              'plan_sha256': sha(raw), 'status': 'failed', 'artifact': {}, 'live_files': []}
    try:
        archive_raw = args.artifact.read_bytes()
        observed = {}
        with tarfile.open(args.artifact, 'r:*') as archive:
            for member in archive:
                name = member.name[2:] if member.name.startswith('./') else member.name
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe artifact member')
                if member.isdir():
                    continue
                if not member.isfile() or name in observed or name not in expected:
                    raise ValueError('Unexpected or duplicate artifact member: ' + name)
                entry = expected[name]
                if member.size != entry['size_bytes']:
                    raise ValueError('Artifact size mismatch: ' + name)
                data = archive.extractfile(member).read(entry['size_bytes'] + 1)
                if sha(data) != entry['sha256']:
                    raise ValueError('Artifact hash mismatch: ' + name)
                observed[name] = {'size_bytes': len(data), 'sha256': sha(data)}
        if set(observed) != set(expected):
            raise ValueError('Artifact inventory differs from plan')
        report['artifact'] = {'sha256': sha(archive_raw), 'file_count': len(observed),
                              'all_files_match_plan': True, 'files': observed}

        def check(item):
            name, entry = item
            result = {'path': name, 'url': entry['target_url'], 'status': 'failed'}
            try:
                request = Request(entry['target_url'], headers={
                    'Origin': 'https://browser.portolan-sdi.org',
                    'User-Agent': 'data-publications-catalog-verifier'})
                with urlopen(request, timeout=30) as response:
                    data = response.read(entry['size_bytes'] + 1)
                    result.update(http_status=response.status, final_url=response.url,
                                  size_bytes=len(data), sha256=sha(data),
                                  content_type=response.headers.get('Content-Type'),
                                  cors=response.headers.get('Access-Control-Allow-Origin'))
                media = {'.json': 'application/json', '.png': 'image/png', '.md': 'text/markdown'}[Path(name).suffix]
                if (result['http_status'] != 200 or result['final_url'] != entry['target_url']
                        or len(data) != entry['size_bytes'] or sha(data) != entry['sha256']
                        or result['cors'] != '*' or result['content_type'].split(';')[0] != media):
                    raise ValueError('Live bytes, MIME, CORS or response identity differs from plan')
                result['status'] = 'passed'
            except Exception as error:
                result['error'] = str(error)
            return result

        with ThreadPoolExecutor(max_workers=4) as pool:
            report['live_files'] = list(pool.map(check, sorted(expected.items())))
        if not all(item['status'] == 'passed' for item in report['live_files']):
            raise ValueError('At least one canonical live file failed verification')
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x') as destination:
        json.dump(report, destination, indent=2)
        destination.write('\n')
    print(json.dumps({'status': report['status'], 'files_checked': len(report['live_files']),
                      'error': report.get('error')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

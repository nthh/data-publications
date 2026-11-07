#!/usr/bin/env python3
"""Opt-in metadata-only source size capture. Refuses to overwrite its output."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

VARIABLES = ['cld', 'dtr', 'frs', 'pet', 'pre', 'tmn', 'tmp', 'tmx', 'vap', 'wet']
BASE = 'https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.10/cruts.2604091129.v4.10/'


def capture(job):
    key, url, method = job
    out = {'key': key, 'url': url, 'method': method, 'observed_at': datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, method=method, headers={'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(req, timeout=25) as response:
            out['http_status'] = response.status
            length = response.headers.get('Content-Length')
            out['content_length_bytes'] = int(length) if length is not None else None
            out['content_type'] = response.headers.get('Content-Type')
            out['etag'] = response.headers.get('ETag')
            out['last_modified'] = response.headers.get('Last-Modified')
            if method == 'GET':
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError('JSON exceeds metadata bound')
                out['response_sha256'] = hashlib.sha256(body).hexdigest()
                data = json.loads(body)
                out['projection'] = {
                    'id': data.get('id'), 'version': data.get('version'), 'doi': data.get('doi'),
                    'files': [{'id': f.get('id'), 'name': f.get('name'), 'size': f.get('size'), 'computed_md5': f.get('computed_md5')} for f in data.get('files', [])],
                }
    except Exception as error:
        out['error'] = str(error)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to replace a prior capture')
    jobs = [(f'cru_{v}', f'{BASE}{v}/cru_ts4.10.1901.2025.{v}.dat.nc.gz', 'HEAD') for v in VARIABLES]
    jobs += [
        ('terraclimate_ws_2025', 'https://tds-proxy.nkn.uidaho.edu/thredds/fileServer/TERRACLIMATE_ALL/data/TerraClimate_ws_2025.nc', 'HEAD'),
        ('riveratlas_gdb', 'https://figshare.com/ndownloader/files/20087321', 'HEAD'),
        ('gdw_article_v1', 'https://api.figshare.com/v2/articles/25988293/versions/1', 'GET'),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        observations = list(pool.map(capture, jobs))
    cru = [o for o in observations if o['key'].startswith('cru_')]
    complete = len(cru) == 10 and all(o.get('http_status') == 200 and o.get('content_length_bytes', 0) and 'gzip' in str(o.get('content_type') or '').lower() and not o.get('error') for o in cru)
    result = {'observations': observations, 'cru_full_period_file_count': 10,
              'cru_exact_header_sum_bytes': sum(o['content_length_bytes'] for o in cru) if complete else None,
              'scope': 'HEAD only for dataset objects; one bounded JSON metadata GET. No dataset bodies fetched. Header sizes are not downloaded checksum validation.'}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'cru_exact_header_sum_bytes': result['cru_exact_header_sum_bytes'],
                      'observations': [{'key': o['key'], 'status': o.get('http_status'), 'bytes': o.get('content_length_bytes'), 'error': o.get('error')} for o in observations]}))


if __name__ == '__main__':
    main()

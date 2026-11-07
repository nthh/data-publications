#!/usr/bin/env python3
"""Acquire the pinned producer GRWL ZIP in verified, resumable HTTP ranges."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import shutil
import socket
import time
import urllib.error
import urllib.request

URL = 'https://zenodo.org/api/records/18624542/files/GRWL_vector_V01.01.zip/content'
NAME = 'GRWL_vector_V01.01.zip'
SIZE = 3_104_998_836
MD5 = '40171f15c0fccd470db32446dda0480e'
RANGE_BYTES = 16 * 1024**2
START_FLOOR = 40 * 1024**3
STOP_FLOOR = 15 * 1024**3
MAX_CONNECTIONS = 4
MAX_BUFFERED_CHUNKS = 4
MAX_RETRIES = 3


def save(path, data):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def digests(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def script_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _retry_after(headers):
    value = headers.get('Retry-After') if headers else None
    if not value:
        return 0
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            at = parsedate_to_datetime(value)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            delay = (at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 0
    return max(0, min(30, delay))


def _download_range(start, stop):
    expected_range = f'bytes {start}-{stop}/{SIZE}'
    request = urllib.request.Request(
        URL,
        headers={'Range': f'bytes={start}-{stop}', 'Accept-Encoding': 'identity'},
    )
    for attempt in range(MAX_RETRIES + 1):
        retry_delay = 0
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 206 or response.headers.get('Content-Range') != expected_range:
                    raise ValueError('Refusing a response that does not match the exact requested range')
                encoding = response.headers.get('Content-Encoding', 'identity').lower()
                if encoding not in ('', 'identity'):
                    raise ValueError('Refusing a non-identity encoded range response')
                data = response.read(stop - start + 2)
            if len(data) != stop - start + 1:
                raise ValueError('Truncated or oversized source response')
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502) or attempt == MAX_RETRIES:
                raise
            retry_delay = _retry_after(exc.headers)
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            if attempt == MAX_RETRIES:
                raise
        if retry_delay:
            time.sleep(retry_delay)


def _validate_resume(partial, state):
    if state.get('url') != URL or state.get('size_bytes') != SIZE or state.get('provider_md5') != MD5:
        raise ValueError('Partial acquisition has different source pins')
    end = 0
    with partial.open('rb') as stream:
        for item in state['ranges']:
            if item['start'] != end:
                raise ValueError('Existing receipt ranges are not a contiguous ordered prefix')
            data = stream.read(item['bytes'])
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Existing partial range checksum differs')
            if item['end'] != end + item['bytes'] - 1:
                raise ValueError('Existing receipt range bounds differ from its byte count')
            end += item['bytes']
    if partial.stat().st_size != end:
        raise ValueError('Unreceipted partial bytes exist; preserve this failure and start a new output directory')
    return end


def acquire(directory, resume=False, connections=MAX_CONNECTIONS):
    if not isinstance(connections, int) or not 1 <= connections <= MAX_CONNECTIONS:
        raise ValueError(f'Connections must be between 1 and {MAX_CONNECTIONS}')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / NAME
    partial = directory / (NAME + '.partial')
    receipt = directory / 'acquisition.json'
    if target.exists():
        raise FileExistsError('Pinned source already exists; verify/use it, do not overwrite')
    if shutil.disk_usage(directory).free < START_FLOOR:
        raise RuntimeError('Source acquisition requires 40 GiB free at start')
    current_script_hash = script_hash()
    if receipt.exists() or partial.exists():
        if not resume or not (receipt.exists() and partial.exists()):
            raise FileExistsError('Use --resume for a consistent existing partial acquisition')
        state = json.loads(receipt.read_text())
        end = _validate_resume(partial, state)
        state.setdefault('code_version_history', []).append({
            'script_sha256': current_script_hash,
            'resumed_at': datetime.now(timezone.utc).isoformat(),
        })
        # Preserve the original script_sha256 as the code version that began acquisition.
        save(receipt, state)
    else:
        state = {
            'schema_version': 1,
            'url': URL,
            'filename': NAME,
            'size_bytes': SIZE,
            'provider_md5': MD5,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'status': 'partial',
            'ranges': [],
            'script_sha256': current_script_hash,
            'code_version_history': [{'script_sha256': current_script_hash,
                                      'started_at': datetime.now(timezone.utc).isoformat()}],
        }
        end = 0
        partial.touch(exist_ok=False)
        save(receipt, state)

    try:
        next_to_submit = end
        next_to_append = end
        outstanding = {}
        ready = {}
        failures = {}
        stop_submitting = False
        buffered_limit = min(connections, MAX_BUFFERED_CHUNKS)
        with partial.open('ab') as sink, ThreadPoolExecutor(max_workers=connections) as executor:
            while next_to_append < SIZE:
                while not stop_submitting and next_to_submit < SIZE and len(outstanding) < buffered_limit:
                    if shutil.disk_usage(directory).free < STOP_FLOOR:
                        raise RuntimeError('Source acquisition stopped at 15 GiB disk reserve')
                    stop = min(SIZE, next_to_submit + RANGE_BYTES) - 1
                    future = executor.submit(_download_range, next_to_submit, stop)
                    outstanding[next_to_submit] = (stop, future)
                    next_to_submit = stop + 1

                if next_to_append not in ready and next_to_append not in failures:
                    futures = [future for _, future in outstanding.values()]
                    completed = {future for future in futures if future.done()}
                    if not completed:
                        pending = futures
                        completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                    if not completed:
                        raise RuntimeError('No outstanding range can advance the ordered download prefix')
                    for future in completed:
                        start = next(start for start, (_, item) in outstanding.items() if item is future)
                        try:
                            ready[start] = future.result()
                        except BaseException as exc:
                            failures[start] = exc
                            stop_submitting = True

                while next_to_append in ready:
                    stop, _ = outstanding.pop(next_to_append)
                    data = ready.pop(next_to_append)
                    sink.write(data)
                    sink.flush()
                    state['ranges'].append({
                        'start': next_to_append,
                        'end': stop,
                        'bytes': len(data),
                        'sha256': hashlib.sha256(data).hexdigest(),
                    })
                    next_to_append = stop + 1
                    end = next_to_append
                    state['received_bytes'] = end
                    state['status'] = 'partial'
                    save(receipt, state)
                    if len(state['ranges']) % 16 == 0:
                        print(json.dumps({'received_bytes': end, 'total_bytes': SIZE}), flush=True)

                if next_to_append in failures:
                    raise failures[next_to_append]

        actual_md5, actual_sha = digests(partial)
        if partial.stat().st_size != SIZE or actual_md5 != MD5:
            raise ValueError('Whole archive byte count or provider MD5 mismatch')
        state.update(status='verified', sha256=actual_sha, source_sha256=actual_sha,
                     whole_archive_checksum_verified=True,
                     completed_at=datetime.now(timezone.utc).isoformat())
        partial.rename(target)
        save(receipt, state)
        print(json.dumps({'status': 'verified', 'size_bytes': SIZE, 'md5': actual_md5, 'sha256': actual_sha}), flush=True)
        return state
    except BaseException as exc:
        state['status'] = 'failed_partial'
        state['received_bytes'] = end
        state['last_error'] = f'{type(exc).__name__}: {exc}'
        save(receipt, state)
        with (directory / 'failures.jsonl').open('a') as stream:
            stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                     'received_bytes': end, 'error': state['last_error']}) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--connections', type=int, choices=range(1, MAX_CONNECTIONS + 1), default=MAX_CONNECTIONS)
    args = parser.parse_args()
    acquire(args.output, args.resume, args.connections)

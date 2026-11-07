#!/usr/bin/env python3
"""Package a local release with evidence bound to the same release manifest."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
HISTORY_FILES = {
    'gee-strict-validation.json': 'evidence/gee-strict-validation.json',
    'gee-unique-geodesic-validation.json': 'evidence/gee-unique-geodesic-validation.json',
    'gee-parity-contract.json': 'gee-parity-contract.json',
    'gee-geometry-diagnostic.json': 'gee-geometry-diagnostic.json',
    'gee-coincident-diagnostic.json': 'gee-coincident-diagnostic.json',
    'publication-benchmarks.json': 'publication-benchmarks.json',
    'gee-capture.json': 'evidence/gee-capture.json',
}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or value in ('.', '..') or '\\' in value or '\x00' in value:
        raise ValueError(f'Unsafe archive path: {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'Unsafe archive path: {value!r}')
    return path


def _required(obj, key, context):
    if not isinstance(obj, dict) or key not in obj:
        raise ValueError(f'Missing {context}.{key}')
    return obj[key]


def _manifest_geoparquet(manifest):
    assets = _required(manifest, 'assets', 'manifest')
    paths = [name for name in assets if name.endswith('.parquet')]
    if len(paths) != 1:
        raise ValueError('Manifest must contain exactly one GeoParquet asset')
    path = paths[0]
    safe_relative(path)
    return path, _required(assets[path], 'sha256', f'manifest.assets[{path}]')


def validate_evidence(manifest_bytes: bytes, evidence: dict) -> dict:
    """Validate all receipts against one manifest; evidence also supplies test code bytes."""
    try:
        manifest = json.loads(manifest_bytes)
        manifest_sha = digest(manifest_bytes)
        parquet_path, parquet_sha = _manifest_geoparquet(manifest)
        commit = _required(manifest, 'conversion_git_commit', 'manifest')
        records = _required(manifest, 'records', 'manifest')
        validation = _required(evidence, 'validation', 'evidence')
        stac = _required(evidence, 'stac_validation', 'evidence')
        reproduction = _required(evidence, 'reproducibility', 'evidence')
        paper = _required(evidence, 'publication_validation', 'evidence')
        gee = _required(evidence, 'gee_validation', 'evidence')
        faults = _required(evidence, 'fault_tests', 'evidence')
        if validation.get('status') != 'passed' or validation.get('http', {}).get('status') != 'passed':
            raise ValueError('Publication validation did not pass')
        if validation.get('source_rows') != records or validation.get('release_manifest_sha256') != manifest_sha:
            raise ValueError('Publication validation is not bound to this release manifest')
        if stac.get('exit_code') != 0 or stac.get('release_manifest_sha256') != manifest_sha:
            raise ValueError('STAC validation is not passed and bound to this release manifest')
        if (reproduction.get('status') != 'passed' or reproduction.get('manifest_equal') is not True
                or reproduction.get('conversion_git_commit') != commit
                or reproduction.get('manifest_sha256') != manifest_sha):
            raise ValueError('Reproducibility evidence is incomplete or refers to another release')
        hashes = _required(reproduction, 'hashes', 'reproducibility')
        if set(hashes) != set(manifest['assets']):
            raise ValueError('Reproducibility asset list differs from the release manifest')
        for name, asset in manifest['assets'].items():
            safe_relative(name)
            if hashes.get(name) != asset.get('sha256'):
                raise ValueError(f'Reproducibility hash mismatch: {name}')
        if paper.get('status') != 'passed':
            raise ValueError('Publication paper validation did not pass')
        paper_provenance = _required(paper, 'provenance', 'publication_validation')
        if (paper_provenance.get('release_manifest_sha256') != manifest_sha
                or paper_provenance.get('geoparquet_sha256') != parquet_sha):
            raise ValueError('Publication paper validation is not bound to this release data')
        historical = _required(evidence, 'historical_file_bytes', 'evidence')
        history_archive_names = {f'verification/history/{name}' for name in HISTORY_FILES}
        if set(historical) != history_archive_names or not all(isinstance(raw, bytes) for raw in historical.values()):
            raise ValueError('Historical verification files are incomplete')
        history_sha = {name.removeprefix('verification/history/'): digest(raw)
                       for name, raw in historical.items()}
        if paper_provenance.get('benchmark_contract_sha256') != history_sha['publication-benchmarks.json']:
            raise ValueError('Publication validation references a different benchmark contract')
        if (gee.get('status') != 'passed_with_documented_geometry_difference'
                or gee.get('strict_coordinate_parity') != 'failed'):
            raise ValueError('GEE diagnostic must retain the documented geometry difference and strict failure')
        gee_provenance = _required(gee, 'provenance', 'gee_validation')
        if gee_provenance.get('geoparquet_sha256') != parquet_sha:
            raise ValueError('GEE diagnostic is not bound to this release GeoParquet')
        contract_bindings = {
            'parent_contract_sha256': 'gee-parity-contract.json',
            'diagnostic_contract_sha256': 'gee-geometry-diagnostic.json',
            'coincident_contract_sha256': 'gee-coincident-diagnostic.json',
            'capture_receipt_sha256': 'gee-capture.json',
        }
        for field, filename in contract_bindings.items():
            if gee_provenance.get(field) != history_sha[filename]:
                raise ValueError(f'GEE diagnostic references a different historical input: {filename}')
        if faults.get('status') != 'passed' or faults.get('release_manifest_sha256') != manifest_sha:
            raise ValueError('Aggregate fault tests did not pass for this release manifest')
        cases = faults.get('cases')
        tests = _required(faults, 'tests', 'fault_tests')
        if isinstance(cases, bool) or not isinstance(cases, int) or cases <= 0 or not isinstance(tests, list) or not tests:
            raise ValueError('Aggregate fault test receipt must list positive cases and tested code')
        code_bytes = _required(evidence, 'fault_test_file_bytes', 'evidence')
        for i, test in enumerate(tests):
            context = f'fault_tests.tests[{i}]'
            path = str(safe_relative(_required(test, 'path', context)))
            if test.get('exit_code') != 0 or not isinstance(test.get('sha256'), str):
                raise ValueError(f'Fault test did not pass or lacks a code hash: {path}')
            raw = code_bytes.get(path)
            if not isinstance(raw, bytes) or digest(raw) != test['sha256']:
                raise ValueError(f'Fault test code hash mismatch: {path}')
        return {'manifest': manifest, 'manifest_sha256': manifest_sha,
                'geoparquet_path': parquet_path, 'geoparquet_sha256': parquet_sha,
                'conversion_git_commit': commit}
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f'Invalid verification evidence: {error}') from error


def _receipt(path: Path) -> tuple[dict, bytes]:
    return json.loads(path.read_text()), path.read_bytes()


def _read_fault_code(root: Path, receipt: dict) -> dict[str, bytes]:
    code = {}
    for i, test in enumerate(_required(receipt, 'tests', 'fault_tests')):
        rel = safe_relative(_required(test, 'path', f'fault_tests.tests[{i}]'))
        path = (root / Path(*rel.parts)).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f'Fault test path escapes pilot or is not a file: {rel}')
        code[rel.as_posix()] = path.read_bytes()
    return code


def _zipinfo(name: str, timestamp: tuple[int, ...]) -> zipfile.ZipInfo:
    safe_relative(name)
    info = zipfile.ZipInfo(name, timestamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def check_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        for name in names:
            safe_relative(name)
        if archive.testzip() is not None:
            raise ValueError('Archive CRC validation failed')
        binding = json.loads(archive.read('verification/receipt.json'))
        manifest_bytes = archive.read('manifest.json')
        if digest(manifest_bytes) != binding['manifest_sha256']:
            raise ValueError('Archive manifest hash mismatch')
        manifest = json.loads(manifest_bytes)
        expected_names = {'manifest.json', 'verification/receipt.json'}
        for name, item in manifest['assets'].items():
            safe_relative(name)
            expected_names.add(name)
            payload = archive.read(name)
            if len(payload) != item['size_bytes'] or digest(payload) != item['sha256']:
                raise ValueError(f'Archive asset hash mismatch: {name}')
        verification = binding['verification_sha256']
        expected_names.update(verification)
        if set(names) != expected_names:
            raise ValueError('Archive has missing or unexpected members')
        for name, expected in verification.items():
            safe_relative(name)
            if not name.startswith('verification/') or name == 'verification/receipt.json':
                raise ValueError(f'Invalid verification hash path: {name}')
            if digest(archive.read(name)) != expected:
                raise ValueError(f'Archive verification hash mismatch: {name}')
    return {'status': 'archive_hashes_verified', 'sha256': digest(path.read_bytes()), 'members_verified': len(names)}


def package(directory: Path, validation_path: Path, stac_path: Path, reproducibility_path: Path,
            publication_validation_path: Path, gee_validation_path: Path, fault_tests_path: Path,
            output: Path) -> dict:
    receipt_path = output.with_suffix('.receipt.json')
    if output.exists() or receipt_path.exists():
        raise ValueError('Archive or receipt already exists; choose a new output')
    directory = directory.resolve()
    manifest_bytes = (directory / 'manifest.json').read_bytes()
    evidence = {
        'validation': json.loads(validation_path.read_text()),
        'stac_validation': json.loads(stac_path.read_text()),
        'reproducibility': json.loads(reproducibility_path.read_text()),
        'publication_validation': json.loads(publication_validation_path.read_text()),
        'gee_validation': json.loads(gee_validation_path.read_text()),
        'fault_tests': json.loads(fault_tests_path.read_text()),
    }
    evidence['fault_test_file_bytes'] = _read_fault_code(HERE, evidence['fault_tests'])
    history_bytes = {}
    for name, source_rel in HISTORY_FILES.items():
        source = HERE / source_rel
        if not source.is_file():
            raise ValueError(f'Missing required historical verification file: {source_rel}')
        history_bytes['verification/history/' + name] = source.read_bytes()
    evidence['historical_file_bytes'] = history_bytes
    identity = validate_evidence(manifest_bytes, evidence)
    manifest = identity['manifest']
    entries = {'manifest.json': manifest_bytes}
    for name, expected in manifest['assets'].items():
        rel = safe_relative(name)
        path = (directory / Path(*rel.parts)).resolve()
        if not path.is_relative_to(directory):
            raise ValueError(f'Manifest path escapes the release: {name}')
        payload = path.read_bytes()
        if len(payload) != expected['size_bytes'] or digest(payload) != expected['sha256'] or digest(payload) != evidence['reproducibility']['hashes'].get(name):
            raise ValueError(f'Asset changed after verification: {name}')
        entries[name] = payload
    supplied = (
        ('validation.json', validation_path), ('stac-validation.json', stac_path),
        ('reproducibility.json', reproducibility_path),
        ('publication-validation.json', publication_validation_path),
        ('gee-validation.json', gee_validation_path), ('fault-tests.json', fault_tests_path),
    )
    for name, path in supplied:
        entries['verification/' + name] = path.read_bytes()
    for name, raw in evidence['fault_test_file_bytes'].items():
        entries['verification/fault-test-code/' + name] = raw
    for name in ('LICENSE', 'NOTICE'):
        entries['verification/fault-test-code/' + name] = (HERE.parents[1] / name).read_bytes()
    history_hashes = {}
    for archive_name, raw in evidence['historical_file_bytes'].items():
        entries[archive_name] = raw
        history_hashes[archive_name] = digest(raw)
    timestamp = dt.datetime.fromisoformat(manifest['source']['metadata_timestamp'].replace('Z', '+00:00')).timetuple()[:6]
    binding = {
        'status': 'locally_verified_not_published',
        'conversion_git_commit': identity['conversion_git_commit'],
        'manifest_sha256': identity['manifest_sha256'],
        'geoparquet_sha256': identity['geoparquet_sha256'],
        'packaging_script_sha256': digest(Path(__file__).read_bytes()),
        'verification_sha256': {name: digest(data) for name, data in entries.items() if name.startswith('verification/')},
        'historical_verification_sha256': history_hashes,
        'limits': 'No Source Cooperative upload or registry submission. HTTP validation used a loopback server; remote hosting remains untested.',
    }
    entries['verification/receipt.json'] = (json.dumps(binding, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.with_suffix('.receipt.json')
    if output.exists() or receipt_path.exists():
        raise ValueError('Archive or receipt already exists; choose a new output')
    archive_temp = None
    receipt_temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.package-', suffix='.zip', dir=output.parent, delete=False) as temp:
            archive_temp = Path(temp.name)
        with zipfile.ZipFile(archive_temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(entries.items()):
                archive.writestr(_zipinfo(name, timestamp), data, compresslevel=9)
        check_archive(archive_temp)
        receipt = {**binding, 'archive': {'path': str(output), 'size_bytes': archive_temp.stat().st_size,
                    'sha256': digest(archive_temp.read_bytes()), 'members_verified': len(entries)}}
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.receipt-', suffix='.json', dir=output.parent, delete=False) as temp:
            receipt_temp = Path(temp.name)
            temp.write(json.dumps(receipt, indent=2) + '\n')
        # Hard links publish each completed file without clobbering existing outputs.
        os.link(archive_temp, output)
        try:
            os.link(receipt_temp, receipt_path)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        print(json.dumps(receipt['archive'], indent=2))
        return receipt
    finally:
        if archive_temp:
            archive_temp.unlink(missing_ok=True)
        if receipt_temp:
            receipt_temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--stac-validation', type=Path, required=True)
    parser.add_argument('--reproducibility', type=Path, required=True)
    parser.add_argument('--publication-validation', type=Path, required=True)
    parser.add_argument('--gee-validation', type=Path, required=True)
    parser.add_argument('--fault-tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        package(args.directory, args.validation, args.stac_validation, args.reproducibility,
                args.publication_validation, args.gee_validation, args.fault_tests, args.output)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()

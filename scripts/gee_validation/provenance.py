"""Independently bind validation inputs to tracked manifests and historical Git blobs."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provenance_archive import resolve_blob

ROOT=Path(__file__).resolve().parents[2]


def digest(data):return hashlib.sha256(data).hexdigest()


def blob(root, commit, path, expected_sha256=None):
    return resolve_blob(root, commit, path, expected_sha256)


def verify_provenance(sample_path, capture_dir, plan_path, root=ROOT):
    sample=json.loads(Path(sample_path).read_text())
    receipt=json.loads((Path(capture_dir)/'capture.json').read_text())
    source=sample.get('source',{})
    checks={};errors=[]
    def check(name,fn):
        try:
            ok=bool(fn())
        except Exception as e:
            ok=False;errors.append({'check':name,'error_type':type(e).__name__})
        checks[name]=ok
    manifest_path=source.get('manifest_path','')
    def manifest_bytes():
        p=PurePosixPath(manifest_path)
        if not manifest_path.startswith('datasets/') or p.is_absolute() or '..' in p.parts or '\\' in manifest_path:
            raise ValueError('Unsafe source manifest path')
        return (root/manifest_path).read_bytes()
    check('tracked_manifest_sha256',lambda:digest(manifest_bytes())==source.get('manifest_sha256'))
    def asset_pin():
        m=json.loads(manifest_bytes())
        matches=[a for a in m['assets'] if a['asset_id']==source.get('asset_id')]
        return len(matches)==1 and all(matches[0].get(k)==source.get(v) for k,v in [('sha256','parquet_sha256'),('row_count','row_count'),('size_bytes','size_bytes')])
    check('manifest_asset_sha256_rows_and_size',asset_pin)
    def canonical():
        dataset=source.get('dataset_id','')
        if not re.fullmatch(r'[a-z0-9-]+',dataset):return False
        publication=yaml.safe_load((root/'datasets'/dataset/'dataset.yaml').read_text())['publication']
        return publication['release']==source.get('release') and publication['manifest_path']==manifest_path and publication['manifest_sha256']==source.get('manifest_sha256')
    check('canonical_selected_release',canonical)
    check('historical_manifest_sha256',lambda:digest(blob(root,sample.get('git_commit'),manifest_path,source.get('manifest_sha256')))==source.get('manifest_sha256'))
    for role,obj,field,path in [
        ('sample_script',sample,'selection_script_sha256','scripts/gee_validation/sample.py'),
        ('sample_lock',sample,'lock_sha256','scripts/gee_validation/uv.lock'),
        ('capture_script',receipt,'script_sha256','scripts/gee_validation/capture.py'),
        ('capture_lock',receipt,'lock_sha256','scripts/gee_validation/uv.lock')]:
        check(f'historical_{role}',lambda obj=obj,field=field,path=path:digest(blob(root,obj.get('git_commit'),path,obj.get(field)))==obj.get(field))
    def plan_blob():
        path=Path(plan_path).resolve().relative_to(root.resolve()).as_posix()
        return digest(blob(root,receipt.get('git_commit'),path,receipt.get('plan_sha256')))==receipt.get('plan_sha256')==digest(Path(plan_path).read_bytes())
    check('historical_committed_request_plan',plan_blob)
    check('sample_bytes_match_committed_plan',lambda:json.loads(Path(plan_path).read_text())['sample_sha256']==digest(Path(sample_path).read_bytes()))
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'errors':errors,'scope':'Manifest/canonical asset pins and historical code/lock/request-plan bytes independently verified. The complete analytical SHA was checked during sample extraction; this replay does not rehash the multi-GB asset.'}

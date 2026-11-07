import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/gee_validation'))
from provenance import verify_provenance

class ProvenanceTests(unittest.TestCase):
    def test_bogus_historical_pins_and_wrong_asset_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'datasets/example').mkdir(parents=True);(root/'research').mkdir();(root/'capture').mkdir()
            digest=lambda x:hashlib.sha256(x).hexdigest()
            commit='a'*40
            manifest={'assets':[{'asset_id':'x','sha256':'f'*64,'row_count':10,'size_bytes':20}]}
            mb=json.dumps(manifest).encode();(root/'datasets/example/manifest.json').write_bytes(mb)
            pub={'release':'r1','manifest_path':'datasets/example/manifest.json','manifest_sha256':digest(mb)}
            (root/'datasets/example/dataset.yaml').write_text(yaml.safe_dump({'publication':pub}))
            sample={'source':{'dataset_id':'example','release':'r1','manifest_path':pub['manifest_path'],'manifest_sha256':digest(mb),'asset_id':'x','parquet_sha256':'f'*64,'row_count':10,'size_bytes':20},'git_commit':commit,'selection_script_sha256':digest(b'sample-code'),'lock_sha256':digest(b'lock')}
            sp=root/'sample.json';sp.write_text(json.dumps(sample))
            plan={'sample_sha256':digest(sp.read_bytes())};pp=root/'research/plan.json';pp.write_text(json.dumps(plan))
            receipt={'git_commit':commit,'script_sha256':digest(b'capture-code'),'lock_sha256':digest(b'lock'),'plan_sha256':digest(pp.read_bytes())}
            rp=root/'capture/capture.json';rp.write_text(json.dumps(receipt))
            blobs={'datasets/example/manifest.json':mb,'scripts/gee_validation/sample.py':b'sample-code','scripts/gee_validation/capture.py':b'capture-code','scripts/gee_validation/uv.lock':b'lock','research/plan.json':pp.read_bytes()}
            def snapshot(root, revision, path, expected=None):
                if revision != commit: raise ValueError('unknown revision')
                data=blobs[path]
                if expected is not None and digest(data)!=expected: raise ValueError('hash mismatch')
                return data
            with patch('provenance.resolve_blob',side_effect=snapshot):
                self.assertEqual(verify_provenance(sp,root/'capture',pp,root)['status'],'passed')
                for field in ['git_commit','script_sha256','lock_sha256']:
                    changed=dict(receipt);changed[field]='bogus';rp.write_text(json.dumps(changed))
                    self.assertEqual(verify_provenance(sp,root/'capture',pp,root)['status'],'failed')
                rp.write_text(json.dumps(receipt))
                sample['source']['row_count']=11;sp.write_text(json.dumps(sample))
                result=verify_provenance(sp,root/'capture',pp,root)
                self.assertFalse(result['checks']['manifest_asset_sha256_rows_and_size'])
                self.assertFalse(result['checks']['sample_bytes_match_committed_plan'])

    def test_hash_bound_archive_supports_missing_git_history(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'datasets/example').mkdir(parents=True);(root/'research').mkdir();(root/'capture').mkdir()
            digest=lambda x:hashlib.sha256(x).hexdigest()
            commit='b'*40
            manifest={'assets':[{'asset_id':'x','sha256':'f'*64,'row_count':10,'size_bytes':20}]}
            mb=json.dumps(manifest).encode();manifest_path='datasets/example/manifest.json'
            (root/manifest_path).write_bytes(mb)
            pub={'release':'r1','manifest_path':manifest_path,'manifest_sha256':digest(mb)}
            (root/'datasets/example/dataset.yaml').write_text(yaml.safe_dump({'publication':pub}))
            sample={'source':{'dataset_id':'example','release':'r1','manifest_path':manifest_path,'manifest_sha256':digest(mb),'asset_id':'x','parquet_sha256':'f'*64,'row_count':10,'size_bytes':20},'git_commit':commit,'selection_script_sha256':digest(b'sample-code'),'lock_sha256':digest(b'lock')}
            sp=root/'sample.json';sp.write_text(json.dumps(sample))
            plan={'sample_sha256':digest(sp.read_bytes())};pp=root/'research/plan.json';pp.write_text(json.dumps(plan))
            receipt={'git_commit':commit,'script_sha256':digest(b'capture-code'),'lock_sha256':digest(b'lock'),'plan_sha256':digest(pp.read_bytes())}
            (root/'capture/capture.json').write_text(json.dumps(receipt))
            blobs={manifest_path:mb,'scripts/gee_validation/sample.py':b'sample-code','scripts/gee_validation/capture.py':b'capture-code','scripts/gee_validation/uv.lock':b'lock','research/plan.json':pp.read_bytes()}
            archive_root=root/'research/history-portability-20261106';(archive_root/'blobs').mkdir(parents=True)
            records=[]
            for path,data in blobs.items():
                sha=digest(data);(archive_root/'blobs'/sha).write_bytes(data)
                records.append({'git_revision':commit,'path':path,'sha256':sha,'bytes':len(data),'blob':f'blobs/{sha}'})
            (archive_root/'index.json').write_text(json.dumps({'schema_version':1,'files':records}))
            unavailable=subprocess.CompletedProcess([],1)
            with patch('provenance_archive.subprocess.run',return_value=unavailable):
                result=verify_provenance(sp,root/'capture',pp,root)
            self.assertEqual(result['status'],'passed')
            self.assertTrue(result['checks']['historical_manifest_sha256'])
            self.assertTrue(result['checks']['historical_committed_request_plan'])

if __name__=='__main__':unittest.main()

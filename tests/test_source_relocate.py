"""Focused guards for additive Source relocation; no network requests."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/source_publish'))
import relocate

class RelocationTests(unittest.TestCase):
 def setUp(self):
  self.temporary=tempfile.TemporaryDirectory()
  self.root=Path(self.temporary.name).resolve()
  self.row={'dataset_id':'hydrolakes','filename':'lakes-v1.parquet','object_key':'hydrolakes/lakes-v1.parquet',
    'url':'https://data.source.coop/nthh/hydrolakes/lakes-v1.parquet','sha256':'a'*64,'size_bytes':32,
    'source_key':'hydrolakes/releases/r1/assets/lakes.parquet',
    'source_href':'https://data.source.coop/nthh/hydrolakes/releases/r1/assets/lakes.parquet',
    'source_sha256':'a'*64,'source_size_bytes':32,'operation':'copy','media_type':'application/vnd.apache.parquet'}
 def tearDown(self): self.temporary.cleanup()
 def plan(self,rows=None):
  path=self.root/'plan.json'
  data=json.dumps({'schema_version':1,'endpoint':relocate.ENDPOINT,'bucket':'nthh','files':rows or [self.row]}).encode()
  path.write_bytes(data)
  return path,hashlib.sha256(data).hexdigest()
 def test_frozen_plan_accepts_exact_copy(self):
  path,sha=self.plan()
  self.assertEqual(relocate.load_plan(path,sha,self.root)['files'][0],self.row)
  with self.assertRaisesRegex(ValueError,'checksum'): relocate.load_plan(path,'b'*64,self.root)
 def test_cross_product_and_duplicate_destinations_refused(self):
  path,sha=self.plan([self.row,self.row])
  with self.assertRaisesRegex(ValueError,'Duplicate'):relocate.load_plan(path,sha,self.root)
  self.row['source_key']='lakeatlas/releases/r1/lakes.parquet'
  path,sha=self.plan()
  with self.assertRaisesRegex(ValueError,'outside'):relocate.load_plan(path,sha,self.root)
 def test_changed_copy_bytes_and_traversal_refused(self):
  self.row['source_sha256']='c'*64
  path,sha=self.plan()
  with self.assertRaisesRegex(ValueError,'identity'):relocate.load_plan(path,sha,self.root)
  self.row['filename']='../data.parquet'
  path,sha=self.plan()
  with self.assertRaisesRegex(ValueError,'filename'):relocate.load_plan(path,sha,self.root)
 def test_single_copy_requires_unchanged_source_and_absent_target(self):
  client=mock.Mock(); client.head_object.return_value={'ContentLength':32,'ETag':'"source"'}
  session=mock.Mock();session.client.return_value=client
  relocate.copy_object(session,self.row,lambda:None,{})
  args=client.copy_object.call_args.kwargs
  self.assertEqual(args['IfNoneMatch'],'*')
  self.assertEqual(args['CopySourceIfMatch'],'"source"')
  self.assertEqual(args['CopySource'],{'Bucket':'nthh','Key':self.row['source_key']})
 def test_failed_multipart_aborts_only_own_upload(self):
  self.row['size_bytes']=self.row['source_size_bytes']=5_500_000_000
  client=mock.Mock();client.head_object.return_value={'ContentLength':5_500_000_000,'ETag':'"source"'}
  client.create_multipart_upload.return_value={'UploadId':'owned-upload'}
  client.upload_part_copy.side_effect=RuntimeError('fixture failure')
  session=mock.Mock();session.client.return_value=client
  record={}
  with self.assertRaises(RuntimeError):relocate.copy_object(session,self.row,lambda:None,record)
  client.abort_multipart_upload.assert_called_once_with(Bucket='nthh',Key=self.row['object_key'],UploadId='owned-upload')
  client.complete_multipart_upload.assert_not_called()
  self.assertEqual(record['multipart']['state'],'aborted')
 def test_composite_checksum_cannot_prove_full_byte_identity(self):
  value=base64.b64encode(bytes.fromhex('a'*64)).decode()
  self.assertEqual(relocate.full_checksum({'ChecksumSHA256':value}),'a'*64)
  self.assertIsNone(relocate.full_checksum({'ChecksumSHA256':value,'ChecksumType':'COMPOSITE'}))
  self.assertIsNone(relocate.full_checksum({'ChecksumSHA256':value+'-2'}))

 def test_parallel_ranges_hash_in_file_order_and_refuse_truncation(self):
  import time
  data=bytes(range(251))*7
  def fetch(start,end):
   if start==0:time.sleep(0.02)
   return data[start:end+1]
  self.assertEqual(relocate.ordered_range_hash(fetch,len(data),chunk_bytes=128,workers=4),hashlib.sha256(data).hexdigest())
  with self.assertRaisesRegex(ValueError,'truncated'):
   relocate.ordered_range_hash(lambda a,b:data[a:b],len(data),chunk_bytes=128,workers=2)

if __name__=='__main__':unittest.main()

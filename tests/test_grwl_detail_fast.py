"""Independent native wire oracle versus the retained UPB fixture oracle."""
from __future__ import annotations
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pmtiles.tile import Compression,zxy_to_tileid

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
fast=module('grwl_fast_fixture','datasets/grwl-raw/compare_detail_fast.py')
fixtures=module('grwl_repack_fixtures_for_fast','tests/test_grwl_repack.py')
reference=fast.reference


class FastDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native_temp=tempfile.TemporaryDirectory(prefix='grwl-native-oracle-fixture-')
        cls.build=Path(cls.native_temp.name)/'build'
        cls.binary,cls.native=fast.compile_oracle(cls.build)
    @classmethod
    def tearDownClass(cls):cls.native_temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'source.pmtiles';self.candidate=self.base/'candidate.pmtiles'
        fixtures.archive(self.source,[((8,0,0),fixtures.tile()),((12,0,0),fixtures.tile(duplicate=True))])
    def compare(self):return fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0)
    def candidate_archive(self,changed=None,tail=None):
        fixtures.archive(self.candidate,[((8,0,0),changed or fixtures.tile(False)),((12,0,0),tail or fixtures.tile(False,duplicate=True))])
    def native_pair(self,source,candidate,compression=Compression.NONE):
        if compression==Compression.GZIP:source,candidate=gzip.compress(source),gzip.compress(candidate)
        with fast.native_session(self.binary) as process:
            return fast.compare_pair(process,(12,0,0),source,candidate,compression,compression)

    def test_exact_counts_match_reference(self):
        self.candidate_archive()
        self.assertEqual(self.compare(),reference.compare(self.source,self.candidate,progress_every=0))
        self.assertEqual(self.compare()['detail_features'],3)

    def test_same_semantic_mutations_rejected_by_both_oracles(self):
        mutations={
            'id':lambda t:setattr(t.layers[0].features[0],'id',9),
            'dropped_id':lambda t:t.layers[0].features[0].ClearField('id'),
            'geometry':lambda t:t.layers[0].features[0].geometry.__setitem__(4,6),
            'width':lambda t:setattr(t.layers[0].values[0],'int_value',74),
            'width_type':lambda t:(t.layers[0].values[0].ClearField('int_value'),setattr(t.layers[0].values[0],'uint_value',73)),
            'valid':lambda t:setattr(t.layers[0].values[1],'bool_value',False),
            'unexpected_field':lambda t:t.layers[0].keys.append('invented'),
            'bad_tags':lambda t:t.layers[0].features[0].tags.append(100),
            'out_of_bounds_tags':lambda t:t.layers[0].features[0].tags.__setitem__(1,100),
            'duplicate_property':lambda t:t.layers[0].features[0].tags.extend([0,0]),
            'duplicate_key':lambda t:t.layers[0].keys.append('width_m'),
            'wrong_extent':lambda t:setattr(t.layers[0],'extent',8192),
            'wrong_version':lambda t:setattr(t.layers[0],'version',1),
            'wrong_layer':lambda t:setattr(t.layers[0],'name','invented'),
            'wrong_type':lambda t:setattr(t.layers[0].features[0],'type',1),
            'empty_geometry':lambda t:t.layers[0].features[0].ClearField('geometry'),
            'dropped_feature':lambda t:t.layers[0].ClearField('features'),
            'multiple_value_types':lambda t:setattr(t.layers[0].values[0],'uint_value',73),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                changed=fixtures.tile(False);mutate(changed);self.candidate_archive(changed)
                with self.assertRaises(ValueError):self.compare()
                with self.assertRaises(ValueError):reference.compare(self.source,self.candidate,progress_every=0)

    def test_order_and_dictionary_permutation_preserve_semantics(self):
        old=fixtures.tile(duplicate=True);new=fixtures.tile(False,duplicate=True)
        extra=copy.deepcopy(new.layers[0].features[0]);extra.id=77
        new.layers[0].features.add().CopyFrom(extra)
        old.layers[0].features.add().CopyFrom(extra)
        old.layers[0].features[-1].tags[:]=old.layers[0].features[0].tags
        new.layers[0].features.reverse();new.layers[0].keys.reverse();new.layers[0].values.reverse()
        for feature in new.layers[0].features:feature.tags[:]=[1,1,0,0]
        expected=sum(reference.signature(old.SerializeToString(),source=True)[2].values())
        self.assertEqual(expected,3)
        for compression in (Compression.NONE,Compression.GZIP):
            self.assertEqual(self.native_pair(old.SerializeToString(),new.SerializeToString(),compression),expected)

    def test_integer_types_negative_values_optional_width_and_full_ids(self):
        for kind,value in [('int_value',-73),('uint_value',(1<<64)-1),('sint_value',-73)]:
            old,new=fixtures.tile(),fixtures.tile(False)
            for tile in (old,new):
                tile.layers[0].features[0].id=(1<<64)-1
                tile.layers[0].values[0].Clear();setattr(tile.layers[0].values[0],kind,value)
            self.assertEqual(self.native_pair(old.SerializeToString(),new.SerializeToString()),1)
            self.assertEqual(reference.signature(old.SerializeToString(),source=True),reference.signature(new.SerializeToString(),source=False))
        old,new=fixtures.tile(),fixtures.tile(False)
        for tile in (old,new):del tile.layers[0].features[0].tags[:2]
        self.assertEqual(self.native_pair(old.SerializeToString(),new.SerializeToString()),1)

    def test_source_bbox_is_validated_but_not_compared(self):
        old,new=fixtures.tile(),fixtures.tile(False)
        old.layers[0].values[2].double_value=-0.0
        self.assertEqual(self.native_pair(old.SerializeToString(),new.SerializeToString()),1)
        for change in ('missing','nonfinite'):
            bad=fixtures.tile()
            if change=='missing':del bad.layers[0].features[0].tags[-2:]
            else:bad.layers[0].values[2].double_value=float('nan')
            with self.assertRaises(ValueError):self.native_pair(bad.SerializeToString(),new.SerializeToString())
            with self.assertRaises(ValueError):reference.signature(bad.SerializeToString(),source=True)

    def test_tile_coordinates_and_multiplicity(self):
        for tiles in [[((8,0,0),fixtures.tile(False))],
                      [((8,0,0),fixtures.tile(False)),((12,0,0),fixtures.tile(False))],
                      [((8,0,0),fixtures.tile(False)),((12,0,0),fixtures.tile(False,duplicate=True)),((12,1,0),fixtures.tile(False))]]:
            fixtures.archive(self.candidate,tiles)
            with self.assertRaises(ValueError):self.compare()
            with self.assertRaises(ValueError):reference.compare(self.source,self.candidate,progress_every=0)

    def test_malformed_wire_and_stream_bounds(self):
        old,new=fixtures.tile().SerializeToString(),fixtures.tile(False).SerializeToString()
        for malformed in [b'',b'\x1a\x80',b'\x1a'+b'\xff'*10+b'\x01',new+new,b'\x00']:
            with self.subTest(malformed=malformed[:20]):
                with self.assertRaises(ValueError):self.native_pair(old,malformed)
        for payload in [b'badmagic',b'GRWLFC01'+b'\x00',
                        b'GRWLFC01'+fast.FRAME.pack(12,0,0,0,0,0,(256<<20)+1,1)]:
            result=subprocess.run([str(self.binary)],input=payload,capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertTrue(result.stderr)
        with self.assertRaises(ValueError),fast.native_session(self.binary) as process:
            fast.compare_pair(process,(12,0,0),gzip.compress(old)[:-3],gzip.compress(new),Compression.GZIP,Compression.GZIP)

    def test_overview_checked_without_detail_native_decode(self):
        overview=fixtures.tile(False);overview.layers[0].name='grwl_overview'
        fixtures.archive(self.candidate,[((0,0,0),overview),((8,0,0),fixtures.tile(False)),((12,0,0),fixtures.tile(False,duplicate=True))])
        result=fast.compare(self.source,self.candidate,binary=self.binary,allow_overview=True,progress_every=0)
        self.assertEqual(result,reference.compare(self.source,self.candidate,allow_overview=True,progress_every=0))
        with self.assertRaises(ValueError):self.compare()

    def paired_tiles(self,count=24,mutated_index=None):
        source=[];candidate=[]
        coordinates=sorted(((8,index,0) for index in range(count)),key=lambda xyz:zxy_to_tileid(*xyz))
        for index,xyz in enumerate(coordinates):
            old,new=fixtures.tile(),fixtures.tile(False)
            old.layers[0].features[0].id+=index;new.layers[0].features[0].id+=index
            if index==mutated_index:new.layers[0].values[0].int_value+=1
            source.append((xyz,old));candidate.append((xyz,new))
        fixtures.archive(self.source,source);fixtures.archive(self.candidate,candidate)
        return coordinates[mutated_index] if mutated_index is not None else None

    def test_two_workers_match_one_worker_and_keep_two_persistent_children(self):
        self.paired_tiles()
        expected=fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0,workers=1)
        with patch.object(fast.subprocess,'Popen',wraps=fast.subprocess.Popen) as launches:
            actual=fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0,workers=2)
        self.assertEqual(actual,expected);self.assertEqual(launches.call_count,2)
        for workers in (1,2):
            limited=fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0,workers=workers,maximum_tile_bytes=1)
            self.assertEqual(limited['detail_tiles_over_byte_limit'],24)

    def test_second_worker_mismatch_propagates_and_sessions_close(self):
        changed_xyz=self.paired_tiles(mutated_index=8)
        with self.assertRaises(ValueError) as rejected:
            fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0,workers=2)
        self.assertIn('Native detail oracle rejected '+str(changed_xyz),str(rejected.exception))
        with self.assertRaises(ValueError):reference.compare(self.source,self.candidate,progress_every=0)
        self.paired_tiles()
        self.assertEqual(fast.compare(self.source,self.candidate,binary=self.binary,progress_every=0,workers=2)['detail_features'],24)

    def test_two_worker_receipt_records_pipeline_bounds(self):
        self.paired_tiles()
        result=fast.run(self.source,self.candidate,self.base/'two-worker.json',source_sha256=fast.sha256(self.source),native_build_dir=self.build,workers=2)
        self.assertEqual(result['workers'],2)
        self.assertEqual(result['pipeline']['batch_tiles'],8)
        self.assertEqual(result['pipeline']['maximum_outstanding_batches'],2)
        self.assertEqual(result['pipeline']['maximum_outstanding_tile_pairs'],16)
        self.assertEqual(result['counts']['detail_features'],24)

    def test_compiler_pins_and_immutable_reports(self):
        self.candidate_archive()
        binary,pins=fast.compile_oracle(self.build)
        self.assertEqual(binary,self.binary);self.assertEqual(pins['binary']['sha256'],fast.sha256(binary))
        report=self.base/'report.json'
        result=fast.run(self.source,self.candidate,report,source_sha256=fast.sha256(self.source),native_build_dir=self.build)
        self.assertEqual(result['status'],'passed');self.assertEqual(result['counts']['detail_features'],3)
        self.assertEqual(result['native_oracle']['source']['sha256'],fast.sha256(fast.NATIVE_SOURCE))
        with self.assertRaises(FileExistsError):fast.run(self.source,self.candidate,report,source_sha256=fast.sha256(self.source),native_build_dir=self.build)
        failed=self.base/'failed.json'
        with self.assertRaises(ValueError):fast.run(self.source,self.candidate,failed,source_sha256='bad',native_build_dir=self.build)
        self.assertEqual(json.loads(failed.read_text())['status'],'failed')


class PipelineRefusalTests(unittest.TestCase):
    def test_workers_and_batch_bounds_refused_before_io(self):
        for workers in (0,3,-1,True,'2'):
            with self.subTest(workers=workers):
                with self.assertRaisesRegex(ValueError,'workers must be 1 or 2'):
                    fast.compare('missing-source','missing-candidate',binary='missing-binary',workers=workers)
        for batch in (0,9,True,'8'):
            with self.subTest(batch=batch):
                with self.assertRaisesRegex(ValueError,'batch must contain'):
                    fast.compare('missing-source','missing-candidate',binary='missing-binary',batch_tiles=batch)


if __name__=='__main__':unittest.main()

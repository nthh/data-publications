"""Independent occupancy oracle fixtures fixed before candidate measurements."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
import shapely
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_overview_oracle', ROOT/'datasets/grwl-raw/validate_overview.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def pairs(cells, n):
    return {(int(cell) % n, int(cell) // n) for cell in cells}


def layer(ring=None):
    if ring is None:
        ring = [[0, 0], [16, 0], [16, 8], [0, 8], [0, 0]]
    return {'extent': 4096, 'features': [{'properties': {}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}]}


class ClosedCellOracleTests(unittest.TestCase):
    def test_diagonal_marks_corner_neighbors_without_connectors(self):
        expected = {(0,0),(1,0),(0,1),(1,1),(2,1),(1,2),(2,2)}
        for segment in [[.2,.2,2.8,2.8], [2.8,2.8,.2,.2]]:
            self.assertEqual(pairs(oracle.oracle_cells([segment], 4), 4), expected)

    def test_exact_horizontal_vertical_and_point_seams(self):
        self.assertEqual(pairs(oracle.oracle_cells([[.2,1,2.8,1]],4),4), {(x,y) for x in range(3) for y in (0,1)})
        self.assertEqual(pairs(oracle.oracle_cells([[1,.2,1,2.8]],4),4), {(x,y) for x in (0,1) for y in range(3)})
        self.assertEqual(pairs(oracle.oracle_cells([[1,1,1,1]],4),4), {(0,0),(0,1),(1,0),(1,1)})

    def test_periodic_world_seam_and_vertical_clamp(self):
        for x in (0, 4, -4):
            self.assertEqual(pairs(oracle.oracle_cells([[x,.2,x,.8]],4),4), {(0,0),(3,0)})
        self.assertEqual(pairs(oracle.oracle_cells([[.2,0,.8,0]],4),4), {(0,0)})
        self.assertEqual(pairs(oracle.oracle_cells([[.2,4,.8,4]],4),4), {(0,3)})

    def test_long_segment_recursive_budget_matches_direct(self):
        segment = [[.2,.3,20.8,22.9]]
        np.testing.assert_array_equal(oracle.oracle_cells(segment,32,maximum_candidates=30), oracle.oracle_cells(segment,32))

    def test_projection_keeps_multipart_independent_and_periodic(self):
        geometry = MultiLineString([[(179.9,0),(-179.9,0)], [(10,10),(10.01,10)]])
        segments = oracle.oracle_segments([geometry],65536)
        self.assertEqual(segments.shape,(2,4))
        self.assertLess(abs(segments[0,2]-segments[0,0]),40)
        self.assertLess(abs(segments[1,2]-segments[1,0]),2)
        self.assertEqual(segments[0,1],32768)
        self.assertEqual(len(oracle.oracle_segments([GeometryCollection([geometry])],65536)),2)
        with self.assertRaises(ValueError):
            oracle.oracle_segments([GeometryCollection([geometry,Point(0,0)])],65536)

    def test_projection_exact_dateline_marks_both_edge_columns(self):
        for longitude in (-180,180):
            segments = oracle.oracle_segments([LineString([(longitude,0),(longitude,.001)])],65536)
            cells = pairs(oracle.oracle_cells(segments,65536),65536)
            self.assertEqual({x for x,y in cells},{0,65535})

    def test_empty_segments(self):
        self.assertEqual(len(oracle.oracle_cells([],4)),0)


class DecodedMaskTests(unittest.TestCase):
    def test_horizontal_run(self):
        mask=oracle.decoded_tile_mask(layer())
        self.assertEqual(int(mask.sum()),2)
        self.assertTrue(mask[0,0] and mask[0,1])

    def test_reject_attributes_holes_wrong_grid_overlap_and_shape(self):
        fixtures=[]
        value=layer();value['features'][0]['properties']={'width_m':12};fixtures.append(value)
        value=layer();value['features'].append(copy.deepcopy(value['features'][0]));fixtures.append(value)
        value=layer();value['features'][0]['geometry']['coordinates'].append([[0,0],[8,0],[8,8],[0,0]]);fixtures.append(value)
        fixtures.extend([layer([[0,0],[15,0],[15,8],[0,8],[0,0]]),
                         layer([[0,0],[16,0],[16,16],[0,16],[0,0]]),
                         layer([[0,0],[16,8],[16,0],[0,8],[0,0]]),
                         layer([[0,0],[0,8],[16,8],[16,0],[0,0]])])
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                with self.assertRaises(ValueError):oracle.decoded_tile_mask(fixture)

    def test_packed_mask_reduction_matches_dense_reference(self):
        rng=np.random.default_rng(20261103)
        n=8*(1<<4)
        fine=rng.random((n,n)) < .05
        for bitorder in ('little','big'):
            packed=np.packbits(fine.reshape(-1),bitorder=bitorder)
            for z in range(5):
                scale=1<<(4-z)
                for x,y in [(0,0),((1<<z)-1,(1<<z)-1)]:
                    side=8*scale
                    expected=fine[y*side:(y+1)*side,x*side:(x+1)*side].reshape(8,scale,8,scale).any(axis=(1,3))
                    np.testing.assert_array_equal(oracle.expected_tile_mask(packed,z,x,y,8,4,bitorder),expected)


class ProductionDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('production_overview_fixture',ROOT/'datasets/grwl-raw/build_overview.py')
        cls.production=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.production)

    def test_fixed_rational_segments_against_geos(self):
        rng=np.random.default_rng(20261103)
        segments=rng.integers(0,65,size=(150,4))/4
        segments=np.vstack([segments,[[0,0,16,16],[16,0,0,16],[1,1,15,15],[1,15,15,1],[0,2,0,14]]])
        for index,segment in enumerate(segments):
            with self.subTest(index=index,segment=segment):
                np.testing.assert_array_equal(oracle.oracle_cells([segment],16),self.production.cells_for_segments([segment],16))

    def test_source_projection_independent_comparison(self):
        fixtures=[MultiLineString([[(-180,0),(-179.999,0)],[(179.9,10),(-179.9,10)]]),
                  LineString([(-30,30),(-29.99,30.001)])]
        self.assertTrue(oracle.compare_source_subset(fixtures,self.production,65536)['passed'])

    def test_encode_decode_runs_match_mask(self):
        import gzip
        import mapbox_vector_tile
        mask=np.zeros((512,512),dtype=bool)
        mask[0,0:3]=True;mask[120,3:510]=True;mask[511,511]=True
        raw,count=self.production.encode_tile(mask)
        decoded=mapbox_vector_tile.decode(gzip.decompress(raw),default_options={'y_coord_down':True})
        self.assertEqual(count,3)
        np.testing.assert_array_equal(oracle.decoded_tile_mask(decoded['grwl_overview']),mask)


class ImmutableRunnerTests(unittest.TestCase):
    def test_source_selection_and_exclusive_receipt(self):
        import json
        import tempfile
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.parquet';manifest=root/'manifest.json';receipt=root/'source-receipt.json'
            geometry=shapely.to_wkb(LineString([(10,10),(10.01,10.01)]))
            schema=pa.schema([('source_tile',pa.string()),('source_row',pa.uint32()),('geometry',pa.binary())])
            with pq.ParquetWriter(source,schema) as writer:
                for tile,count in [('AA01',3),('AA02',2)]:
                    writer.write_table(pa.Table.from_pylist([{'source_tile':tile,'source_row':row,'geometry':geometry} for row in range(1,count+1)],schema=schema))
            manifest.write_text(json.dumps({'parquet_sha256':oracle.sha256(source),'tiles':[{'tile':'AA01','records':3},{'tile':'AA02','records':2}]}))
            criteria={'source':{'parquet_sha256':oracle.sha256(source)},'heldout_source_tiles':['AA02'],
                      'overview':{'cells_per_tile':8,'zooms':[0,1],'independent_source_controls':{'all_records_in_heldout_source_tiles':True,'first_records_per_other_source_tile':1}}}
            spec=importlib.util.spec_from_file_location('runner_production',ROOT/'datasets/grwl-raw/build_overview.py')
            production=importlib.util.module_from_spec(spec);spec.loader.exec_module(production)
            result=oracle.validate_source_subset(source,manifest,criteria,production,receipt)
            self.assertEqual(result['status'],'passed');self.assertEqual(result['records'],3)
            self.assertEqual(result['records_by_tile'],{'AA01':1,'AA02':2})
            with self.assertRaises(FileExistsError):oracle.validate_source_subset(source,manifest,criteria,production,receipt)

    def test_source_controls_across_mixed_tile_row_group(self):
        import json
        import tempfile
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.parquet';manifest=root/'manifest.json'
            geometry=shapely.to_wkb(LineString([(10,10),(10.01,10.01)]))
            table=pa.Table.from_pylist([{'source_tile':tile,'source_row':row,'geometry':geometry}
                for tile,count in [('AA01',3),('AA02',2)] for row in range(1,count+1)])
            pq.write_table(table,source,row_group_size=100)
            manifest.write_text(json.dumps({'parquet_sha256':oracle.sha256(source),'tiles':[{'tile':'AA01','records':3},{'tile':'AA02','records':2}]}))
            criteria={'source':{'parquet_sha256':oracle.sha256(source)},'heldout_source_tiles':['AA02'],
                'overview':{'cells_per_tile':8,'zooms':[0,1],'independent_source_controls':{'all_records_in_heldout_source_tiles':True,'first_records_per_other_source_tile':1}}}
            spec=importlib.util.spec_from_file_location('mixed_production',ROOT/'datasets/grwl-raw/build_overview.py')
            production=importlib.util.module_from_spec(spec);spec.loader.exec_module(production)
            result=oracle.validate_source_subset(source,manifest,criteria,production,root/'receipt.json')
            self.assertEqual(result['records_by_tile'],{'AA01':1,'AA02':2})
            self.assertEqual(result['records'],3)

    def test_archive_all_cells_and_missing_tile_failure(self):
        import gzip
        import json
        import tempfile
        import mapbox_vector_tile
        from pmtiles.writer import Writer
        from pmtiles.tile import Compression,TileType,zxy_to_tileid
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fine=np.zeros((16,16),dtype=bool);fine[0,0]=True;fine[13,13]=True
            mask=root/'mask.bin';np.packbits(fine.reshape(-1),bitorder='little').tofile(mask)
            criteria={'overview':{'zooms':[0,1],'cells_per_tile':8,'extent':4096,'layer':'grwl_overview','maximum_gzip_tile_bytes':262144}}
            entries=[]
            for z in range(2):
                scale=1<<(1-z)
                for y in range(1<<z):
                    for x in range(1<<z):
                        side=8*scale
                        block=fine[y*side:(y+1)*side,x*side:(x+1)*side].reshape(8,scale,8,scale).any(axis=(1,3))
                        features=[]
                        for cy,cx in zip(*np.nonzero(block)):
                            a,b=int(cx)*512,int(cy)*512
                            features.append({'geometry':{'type':'Polygon','coordinates':[[[a,b],[a+512,b],[a+512,b+512],[a,b+512],[a,b]]]},'properties':{}})
                        if features:
                            raw=mapbox_vector_tile.encode({'name':'grwl_overview','features':features},default_options={'y_coord_down':True,'extents':4096})
                            entries.append((zxy_to_tileid(z,x,y),gzip.compress(raw,mtime=0)))
            for omit in (False,True):
                archive=root/('missing.pmtiles' if omit else 'complete.pmtiles')
                with archive.open('wb') as stream:
                    writer=Writer(stream)
                    for index,(tileid,raw) in enumerate(sorted(entries)):
                        if omit and index==len(entries)-1:continue
                        writer.write_tile(tileid,raw)
                    writer.finalize({'tile_type':TileType.MVT,'tile_compression':Compression.GZIP,'min_lon_e7':-1800000000,'min_lat_e7':-850000000,'max_lon_e7':1800000000,'max_lat_e7':850000000,'center_zoom':0,'center_lon_e7':0,'center_lat_e7':0},{})
                receipt=root/('missing-receipt.json' if omit else 'archive-receipt.json')
                if omit:
                    with self.assertRaisesRegex(ValueError,'missing occupied'):oracle.validate_archive(archive,mask,receipt,criteria)
                    self.assertEqual(json.loads(receipt.read_text())['status'],'failed')
                else:
                    self.assertEqual(oracle.validate_archive(archive,mask,receipt,criteria)['status'],'passed')
                    with self.assertRaises(FileExistsError):oracle.validate_archive(archive,mask,receipt,criteria)


if __name__ == '__main__':unittest.main()

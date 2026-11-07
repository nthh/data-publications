import importlib.util
from pathlib import Path
import tempfile
import unittest
import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import LineString, MultiLineString
import shapely
import struct

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('width_builder',ROOT/'datasets/grwl-raw/build_width_overview.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class WidthOverviewTests(unittest.TestCase):
    def batch(self, rows):
        return pa.record_batch({'geometry':pa.array([shapely.to_wkb(LineString([(x,y),(x+0.0001,y+0.0001)])) for _,_,x,y in rows]),
            'feature_id':pa.array([i for i,_,_,_ in rows],type=pa.uint64()),
            'width_m':pa.array([w for _,w,_,_ in rows],type=pa.int64()),
            'width_valid':pa.array([w is not None and w>0 and w!=1 for _,w,_,_ in rows])})

    def test_actual_anchor_first_nonempty_part_and_byte_order(self):
        shape=MultiLineString([[(1.5,2.5),(8,9)],[(30,40),(50,60)]])
        for order in [0,1]:
            self.assertEqual(b.first_anchor(shapely.to_wkb(shape,byte_order=order)),(1.5,2.5))
        empty=struct.pack('<BII',1,2,0)
        nonempty=shapely.to_wkb(LineString([(4,5),(9,10)]))
        multipart=struct.pack('<BII',1,5,2)+empty+nonempty
        self.assertEqual(b.first_anchor(multipart),(4,5))
        with self.assertRaises(ValueError):b.first_anchor(nonempty[:-2])

    def test_widest_valid_and_original_id_ties_survive_batch_partition(self):
        rows=[(50,1,-90,35),(49,None,-90,35),(12,595,-90,35),(11,595,-90,35),(10,200,-90,35),
              (100,None,10,20),(99,1,10,20),(20,50,30,10)]
        outputs=[]
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            for split in [len(rows),2,1]:
                path=tmp/f'input-{split}.parquet'
                with pq.ParquetWriter(path,b.SCHEMA) as w:
                    for offset in range(0,len(rows),split):w.write_table(b.candidate_batch(self.batch(rows[offset:offset+split])))
                c=duckdb.connect();c.execute('SET threads=2')
                output=tmp/f'out-{split}.parquet'
                b.select_winners(c,path,output);c.close()
                outputs.append(pq.read_table(output).to_pylist())
            self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])
            winners={r['feature_id']:r['width_m'] for r in outputs[0]}
            self.assertEqual(winners,{11:595,99:1,20:50})

    def test_external_selection_spans_batches_under_small_memory_limit(self):
        # One cell crosses multiple reader batches; many other cells require
        # sorting under a much smaller budget than the production 1 GB cap.
        count=100000
        cell=np.r_[np.repeat(np.arange(count,dtype=np.uint64),2),np.zeros(65540,dtype=np.uint64)]
        ids=np.arange(1,len(cell)+1,dtype=np.uint64)
        width=np.r_[np.tile(np.array([50,595],dtype=np.int64),count),np.full(65540,595,dtype=np.int64)]
        n=len(cell)
        table=pa.Table.from_arrays([pa.array(cell[::-1]),pa.array(ids[::-1]),pa.array(width[::-1]),
            pa.array(np.ones(n,dtype=bool)),pa.array(np.zeros(n,dtype=np.uint32)),
            pa.array(np.zeros(n,dtype=np.uint32)),pa.array(np.zeros(n)),pa.array(np.zeros(n))],schema=b.SCHEMA)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);source=tmp/'input.parquet';target=tmp/'winners.parquet'
            pq.write_table(table,source)
            c=duckdb.connect();c.execute("SET memory_limit='64MB'");c.execute('SET threads=2')
            c.execute('SET temp_directory='+b.sql_string(tmp/'spill'))
            b.select_winners(c,source,target);c.close()
            actual=pq.read_table(target)
            np.testing.assert_array_equal(actual['cell'].to_numpy(),np.arange(count))
            np.testing.assert_array_equal(actual['feature_id'].to_numpy(),np.arange(2,count*2+1,2))
            self.assertTrue(np.all(actual['width_m'].to_numpy()==595))

    def test_coarsening_is_exact_same_priority_not_average(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);rows=[(1,50,-90,35),(2,1000,-89.998,35),(3,500,-89.999,35)]
            path=tmp/'fine.parquet';pq.write_table(b.candidate_batch(self.batch(rows)),path)
            c=duckdb.connect();c.execute('SET threads=2')
            for z in range(6,-1,-1):
                out=tmp/f'z{z}.parquet';b.select_winners(c,path,out,previous_zoom=z+1);path=out
            c.close()
            r=pq.read_table(path).to_pylist()
            self.assertEqual(len(r),1);self.assertEqual(r[0]['feature_id'],2);self.assertEqual(r[0]['width_m'],1000)

    def test_periodic_seam_and_southern_edge_buffers_preserve_anchor(self):
        qx,qy=b.project_anchors(np.array([-180.,180.,0.]),np.array([0.,0.,-90.]))
        np.testing.assert_array_equal(qx[:2],[0,0]);self.assertEqual(qy[-1],b.Q)
        t=pa.Table.from_arrays([pa.array([0],type=pa.uint64()),pa.array([123],type=pa.uint64()),pa.array([595],type=pa.int64()),pa.array([True]),
            pa.array([0],type=pa.uint32()),pa.array([b.Q//2],type=pa.uint32()),pa.array([-180.]),pa.array([0.])],schema=b.SCHEMA)
        tiles,indices,x,y=b.point_copies(t,0)
        self.assertEqual(len(indices),2);self.assertEqual(set(x),{0,b.EXTENT});self.assertEqual(set(tiles),{0})
        self.assertTrue(all(y==b.EXTENT//2))

    def test_streamed_encoding_keeps_points_across_batch_and_tile_row_boundaries(self):
        import gzip
        import mapbox_vector_tile
        from pmtiles.reader import all_tiles
        n=1024 << 7
        cell=np.arange(n*1024-20000,n*1024+13000,dtype=np.uint64)
        qx=((cell % n) << 11).astype(np.uint32)
        qy=((cell // n) << 11).astype(np.uint32)
        ids=np.arange(1,len(cell)+1,dtype=np.uint64)
        table=pa.Table.from_arrays([pa.array(cell),pa.array(ids),pa.array(np.full(len(cell),595,dtype=np.int64)),
            pa.array(np.ones(len(cell),dtype=bool)),pa.array(qx),pa.array(qy),
            pa.array(qx.astype(float)/b.Q*360-180),pa.array(np.zeros(len(cell)))],schema=b.SCHEMA)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);samples=tmp/'samples';samples.mkdir()
            pq.write_table(table,samples/'z7.parquet',row_group_size=1000)
            c=duckdb.connect();c.execute('SET threads=2')
            for z in range(6,-1,-1):b.select_winners(c,samples/f'z{z+1}.parquet',samples/f'z{z}.parquet',previous_zoom=z+1)
            c.close()
            stats=b.encode_overview(samples,tmp/'overview.pmtiles',tmp)
            payload=(tmp/'overview.pmtiles').read_bytes();observed=set()
            for xyz,tile in all_tiles(lambda offset,length:payload[offset:offset+length]):
                if xyz[0]!=7:continue
                decoded=mapbox_vector_tile.decode(gzip.decompress(tile),default_options={'y_coord_down':True})
                for feature in decoded[b.LAYER]['features']:
                    self.assertEqual(feature['properties'],{'width_m':595,'width_valid':True})
                    observed.add(feature['id'])
            self.assertEqual(observed,set(range(1,33001)))
            self.assertEqual(stats[7]['selected_observations'],33000)

    def test_invalid_source_validity_refused(self):
        batch=self.batch([(1,1,1,2)])
        batch=batch.set_column(batch.schema.get_field_index('width_valid'),'width_valid',pa.array([True]))
        with self.assertRaisesRegex(ValueError,'sentinel'):b.candidate_batch(batch)

if __name__=='__main__':unittest.main()

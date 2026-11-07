"""Ensure altered analytic output cannot pass the complete source comparison."""
import json,tempfile,unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import Polygon
import shapely
from test_convert import HydroLAKESConverterTests
import validate

class SourceFidelityFaults(unittest.TestCase):
    def test_value_null_geometry_and_record_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); helper=HydroLAKESConverterTests()
            source=helper._source(root,[1,2,3]); output,_=helper._convert(source,root,[1,2,3])
            # Fixture is a direct SHP; real release uses a fully pinned ZIP.
            size,digest=validate.identity(source)
            kw={'expected_count':3,'source_sha':digest,'source_bytes':size}
            self.assertEqual(validate.validate(source,output,**kw)['status'],'passed')
            table=pq.read_table(output)
            altered={
              'value':table.set_column(table.schema.get_field_index('Lake_area'),'Lake_area',pa.array([99.,1.25,2.25])),
              'null':table.set_column(table.schema.get_field_index('Lake_name'),'Lake_name',pa.array(['Lake 0','lost null','Lake 2'])),
              'geometry':table.set_column(table.schema.get_field_index('wkb_geometry'),'wkb_geometry',pa.array([shapely.to_wkb(Polygon([(0,0),(1,0),(1,1),(0,0)]))]+table['wkb_geometry'].to_pylist()[1:],type=pa.binary())),
              'drop':table.slice(0,2),
              'duplicate':pa.concat_tables([table.slice(0,2),table.slice(0,1)])}
            for name,t in altered.items():
                with self.subTest(name=name):
                    path=root/(name+'.parquet');pq.write_table(t.replace_schema_metadata(table.schema.metadata),path)
                    with self.assertRaisesRegex(ValueError,'differ|count|Duplicate|schema'):
                        validate.validate(source,path,**kw)
if __name__=='__main__':unittest.main(verbosity=2)

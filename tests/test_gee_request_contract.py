import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'scripts/gee_validation'
sys.path.insert(0,str(TOOLS))
from capture import validate_plan
from sample import rectangles,group_indices

class Contracts(unittest.TestCase):
    def plan(self):
        return {'schema_version':1,'quota_project':'mtnmap-f75ec','limits':{'maximum_requests':256,'maximum_total_bytes':512000000,'maximum_response_bytes':64000000,'timeout_seconds':45,'maximum_elapsed_seconds':7200},'requests':[{'id':'count','operation':'count','resource':'projects/earthengine-public/assets/WWF/HydroSHEDS/v1/FreeFlowingRivers'}]}
    def test_count_only(self):
        validate_plan(self.plan())
        for field,value in [('operation','export'),('resource','https://elsewhere.example/a'),('params',{'filter':'X=1'}),('paginate',True)]:
            p=self.plan();p['requests'][0][field]=value
            with self.assertRaises(AssertionError):validate_plan(p)
    def test_limits(self):
        for key in ['maximum_requests','maximum_total_bytes','maximum_response_bytes','timeout_seconds','maximum_elapsed_seconds']:
            p=self.plan();p['limits'][key]*=100
            with self.assertRaises(AssertionError):validate_plan(p)
    def test_count_deadline_is_bounded(self):
        p=self.plan();p['requests'][0]['timeout_seconds']=180;validate_plan(p)
        p['requests'][0]['timeout_seconds']=181
        with self.assertRaises(AssertionError):validate_plan(p)
        p=self.plan();p['requests'][0]['operation']='get';p['requests'][0]['timeout_seconds']=46
        with self.assertRaises(AssertionError):validate_plan(p)
    def test_names_unique(self):
        p=self.plan();p['requests']*=2
        with self.assertRaises(AssertionError):validate_plan(p)
    def test_global_group_coverage(self):
        for n in [1,2,128,2070,8315]:
            indices=group_indices(n)
            self.assertEqual(indices[0],0);self.assertEqual(indices[-1],n-1)
            self.assertEqual(len(indices),min(n,128));self.assertEqual(len(set(indices)),len(indices))
    def test_dateline_rectangles(self):
        from shapely.geometry import shape
        for x,count in [(0,1),(179.99995,2),(-179.99995,2)]:
            polys=rectangles(x,10)
            self.assertEqual(len(polys),count)
            geom=shape({'type':'MultiPolygon','coordinates':polys})
            self.assertTrue(geom.is_valid)
            for polygon in geom.geoms:
                self.assertLess(polygon.bounds[2]-polygon.bounds[0],.001)

if __name__=='__main__':unittest.main()

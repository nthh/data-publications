import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/gee_validation'))
from diagnose_geometry import geometry_diagnostic

class GeometryDiagnosticTests(unittest.TestCase):
    def test_rotation_and_submetre_shift(self):
        a={'type':'Polygon','coordinates':[[[0,0],[.01,0],[.01,.01],[0,.01],[0,0]]]}
        b={'type':'Polygon','coordinates':[[[.010001,0],[.010001,.01],[.000001,.01],[.000001,0],[.010001,0]]]}
        self.assertTrue(geometry_diagnostic(a,b)['discrete_within_one_meter'])
    def test_extra_chord_is_detected_by_midpoint(self):
        a={'type':'LineString','coordinates':[[0,0],[0,.01],[.01,.01]]}
        b={'type':'MultiLineString','coordinates':[a['coordinates'],[[0,0],[.01,.01]]]}
        self.assertGreater(geometry_diagnostic(a,b)['maximum_sampled_distance_m'],100)
    def test_dateline_and_separate_parts(self):
        a={'type':'MultiLineString','coordinates':[[[179.999,0],[-179.999,0]],[[179.999,.01],[-179.999,.01]]]}
        self.assertLess(geometry_diagnostic(a,a)['maximum_sampled_distance_m'],1e-9)
        self.assertLess(geometry_diagnostic(a,a)['maximum_projected_segment_length_m'],300)
    def test_collection_preserves_line_parts(self):
        polygon={'type':'Polygon','coordinates':[[[0,0],[.01,0],[.01,.01],[0,0]]]}
        collection={'type':'GeometryCollection','geometries':[polygon,{'type':'LineString','coordinates':[[1,0],[2,0]]}]}
        self.assertGreater(geometry_diagnostic(polygon,collection)['maximum_sampled_distance_m'],1000)

if __name__=='__main__':unittest.main()

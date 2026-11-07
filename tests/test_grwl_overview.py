"""Boundary-focused coverage tests, independent expected cell coordinates."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from shapely.geometry import MultiLineString, LineString
spec=importlib.util.spec_from_file_location('overview',Path(__file__).resolve().parents[1]/'datasets/grwl-raw/build_overview.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class OverviewTests(unittest.TestCase):
    def cells(self,s,n=16):
        return {(int(c)%n,int(c)//n) for c in m.cells_for_segments(np.array(s),n)}
    def test_inside(self):self.assertEqual(self.cells([[1.1,2.1,1.9,2.9]]),{(1,2)})
    def test_closed_edge(self):self.assertEqual(self.cells([[2,2.1,2,2.9]]),{(1,2),(2,2)})
    def test_closed_corner(self):self.assertEqual(self.cells([[2,2,2,2]]),{(1,1),(2,1),(1,2),(2,2)})
    def test_no_bbox_fill(self):
        actual=self.cells([[1.2,1.2,3.8,3.8]])
        self.assertNotIn((1,3),actual);self.assertNotIn((3,1),actual)
        self.assertEqual(actual,{(1,1),(1,2),(2,1),(2,2),(2,3),(3,2),(3,3)})
    def test_dateline(self):
        self.assertEqual(self.cells([[15.8,3.5,16.2,3.5]]),{(15,3),(0,3)})
        self.assertEqual(self.cells([[0,3.1,0,3.9]]),{(15,3),(0,3)})
    def test_y_world_edge(self):self.assertEqual(self.cells([[2.2,0,2.8,0]]),{(2,0)})
    def test_long(self):self.assertEqual(self.cells([[1.2,4.5,14.8,4.5]]),{(x,4) for x in range(1,15)})
    def test_parts_not_connected(self):
        g=MultiLineString([[(-30,0),(-29,0)],[(30,0),(31,0)]])
        self.assertEqual(m.project_segments([g],16).shape,(2,4))
    def test_unwrap(self):
        s=m.project_segments([LineString([(179,0),(-179,0)])],16)
        self.assertLess(abs(s[0,2]-s[0,0]),1)
    def test_downsample(self):
        grid=np.zeros((32,32),dtype=np.uint8);grid[3,6]=1;grid[12,31]=1
        actual=np.unpackbits(m.downsample(np.packbits(grid.reshape(-1),bitorder='little'),32),bitorder='little').reshape(16,16)
        expected=np.zeros((16,16),dtype=np.uint8);expected[1,3]=1;expected[6,15]=1
        np.testing.assert_array_equal(actual,expected)

if __name__=='__main__':unittest.main()

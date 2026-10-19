"""Regression checks for analytic poses, curvature and exact board constraints."""
import math
import unittest

import numpy as np

try:
    from .geometry import (fillet_polyline, dubins, length, sample, validate,
                           intersections, bounds)
except ImportError:
    from geometry import (fillet_polyline, dubins, length, sample, validate,
                          intersections, bounds)


class GeometryTests(unittest.TestCase):
    def test_right_angle_fillet_has_fixed_endpoints_and_exact_length(self):
        result = fillet_polyline([(0,10),(20,10),(20,30)],5.)
        self.assertEqual([p['kind'] for p in result],['line','arc','line'])
        self.assertEqual(result[0]['p0'],[0.,10.])
        self.assertEqual(result[-1]['p1'],[20.,30.])
        self.assertAlmostEqual(length(result),30.+2.5*math.pi)
        self.assertEqual(validate(result,(0,10),(20,30),(1,0),(0,1)),[])

    def test_clockwise_fillet_and_redundant_vertices(self):
        result = fillet_polyline([(10,0),(10,0),(10,10),(10,20),(30,20)],5.)
        self.assertEqual(len(result),3)
        self.assertLess(result[1]['sweep'],0)
        self.assertEqual(validate(result,(10,0),(30,20),(0,1),(1,0)),[])

    def test_infeasible_fillet_is_rejected_without_radius_reduction(self):
        with self.assertRaises(ValueError):
            fillet_polyline([(0,0),(2,0),(2,2)],5.)
        with self.assertRaises(ValueError):
            fillet_polyline([(0,0),(10,0),(0,0)],5.)

    def test_all_six_dubins_families_satisfy_poses(self):
        start, end = (60.,60.,.4),(67.,65.,1.7)
        candidates = dubins(start,end,5.)
        self.assertGreaterEqual(len(candidates),5)
        for result in candidates:
            issues = validate(result,start[:2],end[:2],start[2],end[2])
            # Long looped families may self-intersect; the pose and G1 must hold.
            self.assertFalse([e for e in issues if not e.startswith('self_')],issues)
        lengths = [length(r) for r in candidates]
        self.assertEqual(lengths,sorted(lengths))

    def test_random_dubins_pose_integration(self):
        rng = np.random.default_rng(1024)
        for _ in range(250):
            start = (*rng.uniform(30,120,2),rng.uniform(-math.pi,math.pi))
            end = (*rng.uniform(30,120,2),rng.uniform(-math.pi,math.pi))
            for route in dubins(start,end,5.):
                issues = validate(route,start[:2],end[:2],start[2],end[2])
                self.assertFalse([e for e in issues if e.startswith(('start_','end_','discontinuous_','arc_endpoint_'))],issues)
                self.assertNotIn('self_intersection:0:1',issues)
                self.assertNotIn('self_intersection:1:2',issues)

    def test_sampling_sagitta_and_exact_endpoints(self):
        route = fillet_polyline([(10,0),(10,20),(30,20)],5.)
        sampled = sample(route,.0005)
        self.assertTrue(np.array_equal(sampled[0],(10.,0.)))
        self.assertTrue(np.array_equal(sampled[-1],(30.,20.)))
        arc_samples = sampled[1:-1]
        center = np.asarray(route[1]['center'])
        for p,q in zip(arc_samples[:-1],arc_samples[1:]):
            self.assertLessEqual(5.-np.linalg.norm((p+q)/2-center),.0005+1e-10)

    def test_width_at_flat_boundary_port_and_transverse_clearance(self):
        good = [{'kind':'line','p0':[0.,10.],'p1':[150.,10.]}]
        bad = [{'kind':'line','p0':[0.,0.01],'p1':[150.,0.01]}]
        self.assertEqual(validate(good,(0,10),(150,10),(1,0),(1,0)),[])
        self.assertIn('board_out_of_bounds:0',validate(bad,(0,.01),(150,.01),(1,0),(1,0)))

    def test_arc_extrema_detect_excursion_between_endpoints(self):
        arc = {'kind':'arc','center':[147.,75.],'radius':5.,
               'start_angle':-math.pi/2,'sweep':math.pi,'p0':[147.,70.],'p1':[147.,80.]}
        self.assertAlmostEqual(bounds(arc)[2],152.)
        self.assertIn('board_out_of_bounds:0',validate([arc],arc['p0'],arc['p1'],(1,0),(-1,0)))

    def test_line_and_arc_intersections_and_overlap(self):
        horizontal = {'kind':'line','p0':[0.,0.],'p1':[10.,0.]}
        vertical = {'kind':'line','p0':[5.,-10.],'p1':[5.,10.]}
        points, overlap = intersections(horizontal,vertical)
        self.assertFalse(overlap)
        self.assertTrue(np.allclose(points[0],(5,0)))
        self.assertTrue(intersections(horizontal,{'kind':'line','p0':[5.,0.],'p1':[15.,0.]})[1])
        circle = {'kind':'arc','center':[5.,0.],'radius':3.,'start_angle':0.,'sweep':2*math.pi,
                  'p0':[8.,0.],'p1':[8.,0.]}
        self.assertEqual(len(intersections(horizontal,circle)[0]),2)

    def test_self_intersection_and_illegal_layer_are_reported(self):
        route = [{'kind':'line','p0':[10.,10.],'p1':[30.,30.]},
                 {'kind':'line','p0':[30.,30.],'p1':[10.,30.]},
                 {'kind':'line','p0':[10.,30.],'p1':[30.,10.],'layer':1}]
        issues = validate(route,(10,10),(30,10),(1,1),(1,-1))
        self.assertIn('self_intersection:0:2',issues)
        self.assertIn('nonzero_layer:2',issues)


if __name__ == '__main__':
    unittest.main()

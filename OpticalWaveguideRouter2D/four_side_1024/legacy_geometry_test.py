"""Legacy-formula fixtures and all twelve ordered four-side pose checks."""
import contextlib
import io
import math
import tempfile
import unittest

import numpy as np

from .geometry import length,validate
from .legacy_geometry import adjacent,canonicalize,opposite,transform_primitives


class LegacyGeometryTests(unittest.TestCase):
    def test_short_s_uses_original_radius_and_partial_arcs(self):
        for displacement in (-3.175,3.175):
            route=opposite((50.,0.),(50.+displacement,150.),75.)
            arcs=[p for p in route if p['kind']=='arc']
            theta=math.acos(1.-abs(displacement)/10.)
            self.assertEqual(len(arcs),2)
            self.assertTrue(all(a['radius']==5. for a in arcs))
            self.assertTrue(all(abs(abs(a['sweep'])-theta)<1e-12 for a in arcs))
            self.assertAlmostEqual(arcs[0]['p1'][0],50.+displacement/2.)
            self.assertEqual(arcs[0]['p1'],arcs[1]['p0'])
            self.assertEqual(validate(route,(50.,0.),(50.+displacement,150.),(0,1),(0,1)),[])

    def test_two_quarter_arcs_and_zero_dx_straight(self):
        for displacement in (-25.,-10.,10.,25.):
            route=opposite((70.,0.),(70.+displacement,150.),75.)
            arcs=[p for p in route if p['kind']=='arc']
            self.assertEqual(len(arcs),2)
            self.assertTrue(all(abs(abs(a['sweep'])-math.pi/2)<1e-12 for a in arcs))
        straight=opposite((70.,0.),(70.,150.),75.)
        self.assertEqual(len(straight),1)
        self.assertEqual(straight[0]['kind'],'line')
        self.assertEqual(length(straight),150.)

    def test_insufficient_track_space_rejects_without_radius_shrink(self):
        for track in (1.,149.):
            with self.assertRaises(ValueError):
                opposite((50.,0.),(53.175,150.),track)
        with self.assertRaises(ValueError):
            adjacent((143.,0.),(150.,100.),60.)
        with self.assertRaises(ValueError):
            adjacent((30.,0.),(150.,100.),95.)

    def test_adjacent_is_single_l_or_required_three_quarters(self):
        p,q=(30.,0.),(150.,100.)
        direct=adjacent(p,q,100.)
        detour=adjacent(p,q,60.)
        self.assertEqual(sum(a['kind']=='arc' for a in direct),1)
        self.assertEqual(sum(a['kind']=='arc' for a in detour),3)
        for route in (direct,detour):
            self.assertEqual(validate(route,p,q,(0,1),(1,0)),[])
            self.assertTrue(all(p.get('layer',0)==0 for p in route))
            self.assertTrue(all(p['radius']==5. for p in route if p['kind']=='arc'))

    def test_all_twelve_ordered_side_pairs_and_reflected_arcs(self):
        inward={'S':(0,1),'N':(0,-1),'E':(-1,0),'W':(1,0)}
        points={'S':(30.,0.),'N':(100.,150.),'E':(150.,100.),'W':(0.,30.)}
        count=0
        for source in 'NSEW':
            for target in 'NSEW':
                if source==target:
                    continue
                p,q=points[source],points[target]
                cp,cq,transform,kind=canonicalize(source,target,p,q)
                self.assertAlmostEqual(cp[1],0.)
                if kind=='opposite':
                    self.assertAlmostEqual(cq[1],150.)
                    route=opposite(cp,cq,75.)
                else:
                    self.assertAlmostEqual(cq[0],150.)
                    route=adjacent(cp,cq,cq[1])
                mapped=transform_primitives(route,transform,inverse=True)
                self.assertEqual(validate(mapped,p,q,inward[source],-np.asarray(inward[target])),[])
                self.assertAlmostEqual(length(route),length(mapped),places=9)
                back=transform_primitives(mapped,transform)
                for a,b in zip(route,back):
                    self.assertTrue(np.allclose(a['p0'],b['p0'],atol=1e-10))
                    self.assertTrue(np.allclose(a['p1'],b['p1'],atol=1e-10))
                    if a['kind']=='arc':
                        self.assertAlmostEqual(a['sweep'],b['sweep'],places=10)
                count+=1
        self.assertEqual(count,12)

    def test_against_actual_reverse_engineered_plotter_bend(self):
        # The fixture calls the real old function, while production geometry
        # has no matplotlib/pandas/workbook I/O.  Original tangent points and
        # derived centres are rounded to 4 decimal places: 0.00005 mm tolerance.
        import pandas as pd
        import matplotlib.pyplot as plt
        try:
            from wiring_bend_826 import plotter_bend
        except ImportError:
            from OpticalWaveguideRouter2D.wiring_bend_826 import plotter_bend
        with tempfile.TemporaryDirectory() as folder:
            for dx in (-25.,-10.,-3.175,0.,3.175,10.,25.):
                sx,lx,track=70.,70.+dx,75.
                xs=[sx,lx] if dx==0 else [sx,sx,lx,lx]
                ys=[0.,150.] if dx==0 else [0.,track,track,150.]
                frame=pd.DataFrame([dict(inflection_x=xs,inflection_y=ys,dx=abs(dx),dz=0)])
                with contextlib.redirect_stdout(io.StringIO()):
                    original=plotter_bend(frame,.05,.175,bend_radius=5.,delta_arc=.05,
                                          save_folder=folder,file_name='legacy_fixture').iloc[0]
                plt.close('all')
                arcs=[p for p in opposite((sx,0.),(lx,150.),track) if p['kind']=='arc']
                self.assertEqual(len(arcs),len(original['center']))
                for i,arc in enumerate(arcs):
                    self.assertTrue(np.allclose(arc['center'],original['center'][i],rtol=0.,atol=.000051),
                                    (dx,arc['center'],original['center'][i]))
                    for j,field in ((0,'p0'),(1,'p1')):
                        expected=[original['bend_x'][2*i+j],original['bend_y'][2*i+j]]
                        self.assertTrue(np.allclose(arc[field],expected,rtol=0.,atol=.000051),(dx,field,expected,arc[field]))
                    a,b=original['theta'][i]
                    self.assertAlmostEqual(abs(arc['sweep']),b-a,places=12)
                    actual=sorted([round((arc['start_angle']%(2*math.pi)),10),
                                   round(((arc['start_angle']+arc['sweep'])%(2*math.pi)),10)])
                    expected=sorted([round(a%(2*math.pi),10),round(b%(2*math.pi),10)])
                    self.assertEqual(actual,expected)


if __name__=='__main__':
    unittest.main(verbosity=2)

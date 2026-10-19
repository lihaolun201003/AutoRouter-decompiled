"""Independent acceptance checks against the actual, unmodified 1024 CSV.

Run after the experiment with ``python -m four_side_1024.test_acceptance``.
The same checks can run during search; checkpoint-dependent checks then skip
explicitly rather than treating an incomplete search as a successful result.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import math
import unittest
from collections import Counter

import numpy as np

from .geometry import bounds, length, validate
from .inputs import DEFAULT_INPUT, DEFAULT_OUTPUT, config, load
from .router import candidates


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config()
        cls.routes, cls.endpoints, cls.connectors, cls.validation = load(DEFAULT_INPUT, cls.cfg)
        with DEFAULT_INPUT.open(encoding='utf-8-sig', newline='') as stream:
            cls.original = list(csv.DictReader(stream))

    def checkpoint(self):
        path = DEFAULT_OUTPUT/'search_checkpoint.json'
        if not path.exists():
            self.skipTest('Search has not saved search_checkpoint.json yet; rerun after completion')
        return json.loads(path.read_text(encoding='utf-8'))

    def test_fixed_single_layer_and_initial_validation_parameters(self):
        self.assertEqual(self.cfg['board_mm'],[150.,150.])
        self.assertEqual(self.cfg['layer'],0)
        self.assertEqual(self.cfg['routing_layers'],1)
        self.assertEqual(self.cfg['min_radius_mm'],5.)
        self.assertEqual(self.cfg['width_mm'],.05)
        self.assertEqual(self.cfg['edge_gap_mm'],.125)
        self.assertTrue(self.cfg['initial_validation_parameters_not_final_glass_process'])
        self.assertEqual(self.cfg['endpoint_mode'],'virtual_unfolded')
        self.assertEqual(self.cfg['connector_pitch_status'],'provisional')
        self.assertTrue(math.isfinite(self.cfg['search_seconds']) and self.cfg['search_seconds']>0)
        self.assertGreater(self.cfg['candidate_evaluation_budget'],0)
        self.assertEqual(set(self.cfg['strategies']),{'csv','longest','congested','opposite_first'})

    def test_all_1024_original_connections_preserved_field_by_field(self):
        self.assertEqual(len(self.original),1024)
        self.assertEqual(len(self.routes),1024)
        self.assertEqual({r['route_id'] for r in self.routes},set(range(1,1025)))
        for raw, actual in zip(self.original,self.routes):
            for field, original_value in raw.items():
                self.assertEqual(str(actual[field]),original_value,(actual['route_id'],field))
            for role in ('source','target'):
                identity = f"{raw[role+'_connector']}:{raw[role+'_row']}:{raw[role+'_column']}"
                self.assertEqual(actual[role+'_endpoint'],identity)
                endpoint = self.endpoints[identity]
                self.assertEqual(endpoint['side'],raw[role+'_side'])
                self.assertEqual(endpoint['channel'],int(raw[role+'_channel']))

    def test_all_2048_physical_identities_used_exactly_once(self):
        usage = Counter(r[role+'_endpoint'] for r in self.routes for role in ('source','target'))
        self.assertEqual(len(self.endpoints),2048)
        self.assertEqual(set(usage),set(self.endpoints))
        self.assertEqual(set(usage.values()),{1})
        connectors = Counter(self.endpoints[key]['connector'] for key in usage)
        self.assertEqual(len(connectors),64)
        self.assertEqual(set(connectors.values()),{32})
        self.assertEqual(Counter(e['side'] for e in self.endpoints.values()),dict.fromkeys('NSEW',512))

    def test_physical_two_by_sixteen_coordinates_and_half_mm_row_pitch(self):
        self.assertEqual(self.cfg['physical_row_pitch_mm'],.5)
        self.assertEqual(self.cfg['physical_column_pitch_mm'],.25)
        for side in 'NSEW':
            for connector in range(1,17):
                name = f'{side}{connector:02d}'
                face_coordinates = []
                for column in range(1,17):
                    rows = [self.endpoints[f'{name}:{row}:{column}'] for row in (1,2)]
                    for row, endpoint in enumerate(rows,1):
                        self.assertEqual(endpoint['row'],row)
                        self.assertEqual(endpoint['column'],column)
                        self.assertEqual(endpoint['channel'],(row-1)*16+column)
                        self.assertAlmostEqual(endpoint['physical_face_u_mm'],(column-8.5)*.25)
                        self.assertAlmostEqual(endpoint['physical_face_v_mm'],(row-1.5)*.5)
                        face_coordinates.append((endpoint['physical_face_u_mm'],endpoint['physical_face_v_mm']))
                    self.assertAlmostEqual(rows[1]['physical_face_v_mm']-rows[0]['physical_face_v_mm'],.5)
                    self.assertEqual(rows[0]['physical_projected_xy'],rows[1]['physical_projected_xy'])
                self.assertEqual(len(set(face_coordinates)),32)

    def test_virtual_mapping_explicit_distinct_and_fixed_on_correct_boundary(self):
        coordinates = set()
        for endpoint in self.endpoints.values():
            side = endpoint['side']
            x,y = endpoint['routing_xy']
            physical = endpoint['physical_projected_xy']
            expected_center = 7.5+(int(endpoint['connector'][1:])-1)*9.
            along = expected_center+(endpoint['channel']-16.5)*.175
            physical_along = expected_center+(endpoint['column']-8.5)*.25
            if side in 'NS':
                self.assertAlmostEqual(x,along)
                self.assertEqual(y,150. if side=='N' else 0.)
                self.assertAlmostEqual(physical[0],physical_along)
            else:
                self.assertAlmostEqual(y,along)
                self.assertEqual(x,150. if side=='E' else 0.)
                self.assertAlmostEqual(physical[1],physical_along)
            self.assertGreaterEqual(min(x,y),0.)
            self.assertLessEqual(max(x,y),150.)
            self.assertEqual(endpoint['layer'],0)
            self.assertEqual(endpoint['mode'],'virtual_unfolded')
            coordinates.add((x,y))
        self.assertEqual(len(coordinates),2048)
        self.assertEqual(len({tuple(e['physical_projected_xy']) for e in self.endpoints.values()}),1024)
        self.assertIn('not a manufactured fanout',self.validation['physical_projection_limitation'])

    def test_row_one_opposite_row_two_adjacent_and_all_six_pair_types(self):
        self.assertEqual(Counter(r['relation'] for r in self.routes),{'opposite':512,'adjacent':512})
        self.assertEqual(set(r['pair'] for r in self.routes),{'NS','EW','EN','ES','SW','NW'})
        for route in self.routes:
            self.assertNotEqual(route['source_side'],route['target_side'])
            row = 1 if route['relation']=='opposite' else 2
            self.assertEqual(route['source_row'],row)
            self.assertEqual(route['target_row'],row)

    def test_real_candidates_cover_six_pairs_without_moving_ports(self):
        for pair in ('NS','EW','EN','ES','SW','NW'):
            group = [r for r in self.routes if r['pair']==pair]
            route = group[len(group)//2]
            source = self.endpoints[route['source_endpoint']]
            target = self.endpoints[route['target_endpoint']]
            before_source, before_target = tuple(source['routing_xy']),tuple(target['routing_xy'])
            pool,rejections = candidates(route,self.endpoints,self.cfg)
            self.assertTrue(pool,(pair,route['route_id'],rejections))
            self.assertEqual(tuple(source['routing_xy']),before_source)
            self.assertEqual(tuple(target['routing_xy']),before_target)
            for candidate in pool:
                geometry = candidate['primitives']
                self.assertEqual(geometry[0]['p0'],list(before_source))
                self.assertEqual(geometry[-1]['p1'],list(before_target))
                issues = validate(geometry,before_source,before_target,source['inward'],
                                  -np.asarray(target['inward']),board=150.,width=.05,min_radius=5.)
                self.assertEqual(issues,[],(pair,issues))
                self.assertAlmostEqual(candidate['length_mm'],length(geometry),places=8)

    def test_full_width_clearance_rejects_centerline_only_false_positive(self):
        outside = [{'kind':'line','p0':[0.,.02],'p1':[150.,.02]}]
        self.assertLess(bounds(outside[0],width=.05)[1],0.)
        self.assertIn('board_out_of_bounds:0',validate(outside,(0.,.02),(150.,.02),0.,0.,width=.05))
        on_port = [{'kind':'line','p0':[0.,1.],'p1':[150.,1.]}]
        self.assertEqual(validate(on_port,(0.,1.),(150.,1.),0.,0.,width=.05),[])

    def test_phase_one_immutable_copy_hash_and_visualization_exist(self):
        data = DEFAULT_INPUT.read_bytes()
        copy = DEFAULT_OUTPUT/'input_connectivity.csv'
        self.assertTrue(copy.exists())
        self.assertEqual(copy.read_bytes(),data)
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(self.validation['csv_sha256'],digest)
        saved = json.loads((DEFAULT_OUTPUT/'connectivity_validation.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['csv_sha256'],digest)
        self.assertGreater((DEFAULT_OUTPUT/'01_connectivity.png').stat().st_size,10000)

    def test_checkpoint_complete_partition_explicit_failures_and_strict_layer_zero(self):
        checkpoint = self.checkpoint()
        accepted,failed = checkpoint['accepted'],checkpoint['failed']
        ids = [r['route_id'] for r in accepted+failed]
        self.assertEqual(len(ids),1024)
        self.assertEqual(set(ids),set(range(1,1025)))
        self.assertEqual(len(set(ids)),len(ids))
        self.assertLessEqual(checkpoint['search']['candidate_evaluations'],self.cfg['candidate_evaluation_budget'])
        for record in accepted:
            self.assertEqual(record['layer'],0)
            for primitive in record['primitives']:
                self.assertEqual(primitive.get('layer',0),0)
                self.assertEqual(primitive.get('z',0),0)
                self.assertEqual(len(primitive['p0']),2)
                self.assertEqual(len(primitive['p1']),2)
        for failure in failed:
            self.assertTrue(failure['reason'])
            self.assertGreaterEqual(failure['evaluated'],0)
            self.assertIsInstance(failure['rejection_counts'],dict)
            self.assertIsInstance(failure['generation_rejections'],dict)

    def test_checkpoint_all_accepted_routes_have_exact_valid_geometry(self):
        checkpoint = self.checkpoint()
        by_id = {r['route_id']:r for r in self.routes}
        for record in checkpoint['accepted']:
            connection = by_id[record['route_id']]
            source = self.endpoints[connection['source_endpoint']]
            target = self.endpoints[connection['target_endpoint']]
            geometry = record['primitives']
            issues = validate(geometry,source['routing_xy'],target['routing_xy'],source['inward'],
                              -np.asarray(target['inward']),board=150.,width=.05,min_radius=5.)
            self.assertEqual(issues,[],(record['route_id'],issues))
            self.assertAlmostEqual(record['length_mm'],length(geometry),places=7)


def main():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AcceptanceTests))
    log = ('Acceptance audit against original CSV: '+str(DEFAULT_INPUT)+'\n'
           +'Run at '+datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()+'\n'
           +stream.getvalue())
    DEFAULT_OUTPUT.mkdir(parents=True,exist_ok=True)
    (DEFAULT_OUTPUT/'acceptance_tests.log').write_text(log,encoding='utf-8')
    print(log)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()

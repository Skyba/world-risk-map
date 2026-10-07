import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import manage
import world
import world_sources
from display_geometry import smooth_overview


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.old_root=manage.ROOT
        manage.ROOT=self.root

    def tearDown(self):
        manage.ROOT=self.old_root
        self.temp.cleanup()

    def record(self,advice):
        return {'countries':{'FRA':{'overview':None,'local_overview':None,'detail':None,'exceptions':None,'advice':manage.store(advice,'public')}}}

    def test_recheck_does_not_claim_changed_advice(self):
        a={'provider':'uk_fcdo','context':{'text':'Reviewed safety text.'},'alert_status':[],'checked_at':'2026-09-01','page_sha256':'old'}
        b={**a,'checked_at':'2026-10-01','page_sha256':'different boilerplate','advice_sha256':'new stable digest'}
        self.assertEqual(world.difference(self.record(a),self.record(b)),[])

    def test_changed_content_and_new_coverage_are_distinct(self):
        a={'provider':'france_diplomatie','advice_sha256':'old','context':{'text':'Old'}}
        b={**a,'advice_sha256':'new'}
        result=world.difference(self.record(a),self.record(b))
        self.assertEqual(result[0]['kind'],'source_or_geometry_change')
        self.assertIn('Official advice content changed',result[0]['reasons'])
        before=self.record(a);after=copy.deepcopy(before)
        after['countries']['FRA']['overview']={'sha256':'new'}
        self.assertEqual(world.difference(before,after)[0]['kind'],'new_coverage')

    def test_public_world_build_rejects_private_shapes(self):
        s={'countries':{'X':{'overview':{'scope':'private'},'review_status':'approved','rights_status':'cleared'}}}
        self.assertEqual(world.public_blockers(s),['X'])
        s['countries']['X']['overview']['scope']='public'
        self.assertEqual(world.public_blockers(s),[])

    def test_display_rounding_preserves_partition_and_small_zones(self):
        from shapely.geometry import Polygon, box, mapping, shape
        from shapely.ops import unary_union
        country=box(0,0,2,2)
        red=Polygon([(0,0),(1,0),(1,.5),(.8,.5),(.8,1),(1.1,1),(1.1,1.5),(1,1.5),(1,2),(0,2)])
        island=Polygon([(1.4,.4),(1.6,.4),(1.5,.6)])
        red=red.union(island)
        fs=[{'type':'Feature','properties':{'risk':risk,'zone_id':risk},'geometry':mapping(g)} for risk,g in [('red',red),('orange',country.difference(red))]]
        original=manage.topology({'type':'FeatureCollection','features':fs})
        untouched=copy.deepcopy(original)
        display,metrics=smooth_overview(original)
        geometries=[shape(f['geometry']) for f in display['features']]
        self.assertGreater(metrics['shared_arcs_rounded'],0)
        self.assertEqual(original,untouched)
        self.assertEqual([f['properties'] for f in display['features']],[f['properties'] for f in fs])
        self.assertTrue(all(g.is_valid for g in geometries))
        self.assertLess(geometries[0].intersection(geometries[1]).area,1e-8)
        self.assertLess(unary_union(geometries).symmetric_difference(country).area,1e-7)
        self.assertGreater(geometries[0].symmetric_difference(red).area,0)
        self.assertEqual(len(geometries[0].geoms),2)
        self.assertGreater(geometries[0].intersection(island).area,.9*island.area)

    def test_display_rounding_keeps_unmapped_gaps_and_country_outline(self):
        from shapely.geometry import Polygon, mapping, shape
        g=Polygon([(0,0),(1,0),(1,.5),(.8,.5),(.8,1),(0,1)],holes=[[(.2,.2),(.3,.2),(.3,.3),(.2,.3)]])
        original=manage.topology({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'risk':'red'},'geometry':mapping(g)}]})
        display,metrics=smooth_overview(original)
        self.assertEqual(metrics['shared_arcs_rounded'],0)
        self.assertTrue(shape(display['features'][0]['geometry']).equals(g))

    def test_source_outage_keeps_last_success_and_date(self):
        cached={'status':'ok','checked_at':'2026-09-01','provider':'france_diplomatie','name':'Example'}
        (self.root/'fr-1.json').write_text(json.dumps(cached))
        with patch.object(world_sources,'CACHE',self.root),patch.object(world_sources,'build_opener',side_effect=OSError('offline')):
            result=world_sources.french(('1','Example'),{},refresh=True)
        self.assertEqual(result['checked_at'],'2026-09-01')
        self.assertEqual(result['status'],'ok')
        self.assertIn('offline',result['refresh_error'])

    @unittest.skipUnless((world.ROOT/'private/maps/countries.geojson').exists(),'Local Natural Earth extraction fixture is not included in the source-only checkout')
    def test_france_and_overseas_territories_do_not_overlap(self):
        from shapely.geometry import shape
        fs=world.countries();shapes={f['properties']['ADM0_A3']:shape(f['geometry']) for f in fs}
        self.assertGreater(shapes['FRA'].bounds[0],-6)
        self.assertGreater(shapes['FRA'].bounds[1],40)
        for iso in ['GUF','GLP','MTQ','REU','MYT']:
            self.assertFalse(shapes[iso].is_empty)
            self.assertLess(shapes[iso].intersection(shapes['FRA']).area,1e-10)


if __name__=='__main__':unittest.main()

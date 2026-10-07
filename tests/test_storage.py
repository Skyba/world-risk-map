import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('manage',Path(__file__).resolve().parents[1]/'scripts/manage.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def square(x,risk):
 return {'type':'Feature','properties':{'country':'sample','risk':risk,'zone_id':str(x)},'geometry':{'type':'Polygon','coordinates':[[[x,0],[x+1,0],[x+1,1],[x,1],[x,0]]]}}

class StorageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old_root=m.ROOT;m.ROOT=Path(self.temp.name)
 def tearDown(self):
  m.ROOT=self.old_root;self.temp.cleanup()
 def test_dedup_and_corruption_detection(self):
  first=m.store({'a':1,'b':2},'private');second=m.store({'b':2,'a':1},'private')
  self.assertEqual(first,second)
  (m.ROOT/'private/objects'/(first['sha256']+'.json')).write_text('{}')
  with self.assertRaisesRegex(ValueError,'checksum'):m.read_object(first)
 def test_topology_preserves_shared_edges_and_attributes(self):
  from shapely.geometry import shape
  original=m.collection([square(0,'red'),square(1,'yellow')]);original['features'][0]['properties']['restriction']='closed_to_civilians'
  decoded=m.decode(m.store(m.topology(original),'private'))
  self.assertEqual([f['properties'] for f in decoded['features']],[f['properties'] for f in original['features']])
  a,b=[shape(f['geometry']) for f in decoded['features']]
  self.assertEqual(a.intersection(b).area,0)
  self.assertEqual(a.boundary.intersection(b.boundary).length,1)
 def test_city_point_roundtrip(self):
  points=m.collection([{'type':'Feature','properties':{'capital':True,'name':'Example'},'geometry':{'type':'Point','coordinates':[3.1,4.2]}}])
  self.assertEqual(m.decode(m.store(points,'public')),points)
 def test_snapshots_are_immutable_and_reuse_objects(self):
  incoming=m.ROOT/'import';incoming.mkdir()
  country={'rights':{'status':'needs_review'},'review':{'status':'candidate'},'display':{'source_only':False}}
  m.write(incoming/'catalogue.json',{'countries':{'sample':country},'display_metrics':{}})
  for name in ['land','sample-overview','sample-detail']:m.write(incoming/(name+'.geojson'),m.collection([square(0,'red')]))
  m.write(incoming/'cities.geojson',m.collection([]))
  first=m.snapshot(incoming,'2026-01-01');count=len(list(m.ROOT.rglob('objects/*.json')))
  self.assertEqual(first,m.snapshot(incoming,'2026-01-01'))
  second=m.snapshot(incoming,'2026-02-01')
  self.assertEqual(first['countries']['sample']['geometry'],second['countries']['sample']['geometry'])
  self.assertEqual(count,len(list(m.ROOT.rglob('objects/*.json'))))
  self.assertEqual(first['countries']['sample']['geometry']['detail']['scope'],'private')
  m.write(incoming/'sample-detail.geojson',m.collection([square(0,'yellow')]))
  with self.assertRaisesRegex(ValueError,'immutable'):m.snapshot(incoming,'2026-01-01')
 def test_public_build_requires_rights_review_and_public_storage(self):
  s={'countries':{'sample':{'display':{},'review':{'status':'candidate'},'rights':{'status':'needs_review'},'geometry':{'detail':{'scope':'private'}}}}}
  self.assertTrue(m.public_blockers(s))
  c=s['countries']['sample'];c['review']['status']='approved';c['rights']['status']='cleared'
  self.assertTrue(m.public_blockers(s))
  c['geometry']['detail']['scope']='public'
  self.assertEqual(m.public_blockers(s),[])
 def test_source_check_does_not_mutate_snapshot(self):
  image=b'example image';url='https://www.diplomatie.gouv.fr/files/files/cav/sample/map.jpg'
  s={'snapshot_date':'2026-01-01','countries':{'sample':{'source':{'page_url':'https://www.diplomatie.gouv.fr/fr/sample','map_url':url,'map_sha256':hashlib.sha256(image).hexdigest()}}}}
  before=copy.deepcopy(s)
  page=f'<a href="{url}"><img src="{url}"></a>'.encode()
  with patch.object(m,'fetch',side_effect=[(page,'text/html'),(image,'image/jpeg')]):report,path=m.check_sources(s,['sample'])
  self.assertFalse(report['countries']['sample']['map_changed'])
  self.assertIsNone(report['countries']['sample']['page_changed'])
  self.assertEqual(s,before)

if __name__=='__main__':unittest.main()

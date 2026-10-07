import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
import manage

parser=argparse.ArgumentParser(description='Stage regenerated candidates for manual review, never approve or publish.')
parser.add_argument('--date',required=True)
args=parser.parse_args()
from datetime import date
date.fromisoformat(args.date)
root=manage.ROOT
result_dir=root/'private/extraction'
maps=root/'private/maps'
target=root/'private/import'/args.date
target.mkdir(parents=True,exist_ok=True)
previous=manage.current()
metrics=manage.load(result_dir/'test-results.json')
config=manage.load(maps/'control-points.json')
overlays=manage.load(maps/'overlays.json')
report_path=root/'private/updates'/(args.date+'.json')
report=manage.load(report_path) if report_path.exists() else {'countries':{}}
catalogue={'countries':{},'display_metrics':manage.load(result_dir/'display-test-results.json')}
cities=manage.load(result_dir/'display-cities.geojson')['features']
manage.write(target/'cities.geojson',manage.collection([f for f in cities if f['properties']['kind']=='city']))
shutil.copyfile(maps/'display-land.json',target/'land.geojson')
for slug,country in previous['countries'].items():
 row=copy.deepcopy(country)
 row.pop('geometry',None);row.pop('exceptions',None)
 digest=hashlib.sha256((maps/(slug+'.jpg')).read_bytes()).hexdigest()
 checked=report['countries'].get(slug,{})
 verified=checked.get('status')=='checked' and checked['map_sha256']==digest and checked['map_url']==config[slug]['image_url']
 if digest!=country['source']['map_sha256'] or config[slug]['image_url']!=country['source']['map_url']:
  row['rights']['status']='needs_review'
  row['source']['retrieved_at']=None
 row['source'].update({'map_url':config[slug]['image_url'],'map_date':config[slug].get('map_date'),'page_updated_at':config[slug].get('page_date'),'map_sha256':digest})
 if verified:row['source'].update({'retrieved_at':report['checked_at'],'page_sha256':checked['page_sha256']})
 row['review'].update({'status':'withheld' if metrics[slug]['source_only'] else 'candidate','reviewed_at':None})
 row['display']=metrics[slug]
 row['image_overlay']={'coordinates':overlays[slug]['coordinates']}
 catalogue['countries'][slug]=row
 for lod in ['overview','detail']:
  fs=[f for f in manage.load(result_dir/f'display-zones-{lod}.geojson')['features'] if f['properties']['country']==slug]
  if fs:manage.write(target/f'{slug}-{lod}.geojson',manage.collection(fs))
 exceptions=[f for f in cities if f['properties']['kind']=='city_exception' and f['properties']['country']==slug]
 if exceptions:manage.write(target/f'{slug}-exceptions.geojson',manage.collection(exceptions))
 import base64
 (root/'private/media').mkdir(exist_ok=True)
 (root/'private/media'/f'{slug}-aligned.jpg').write_bytes(base64.b64decode(overlays[slug]['url'].split(',')[1]))
 shutil.copyfile(maps/(slug+'.jpg'),root/'private/media'/(slug+'.jpg'))
 shutil.copyfile(result_dir/(slug+'-comparison.png'),root/'private/media'/(slug+'-comparison.png'))
manage.write(target/'catalogue.json',catalogue)
print(target)
print('Candidates staged. Review source changes, geometry, control points, restrictions, rights, dates and context before creating a snapshot.')

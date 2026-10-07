import json
from pathlib import Path
import numpy as np
import cv2
from pyproj import Transformer, Geod
from scipy.ndimage import label

root=Path(__file__).resolve().parent.parent
src=root/'private/maps'; out=root/'private/extraction'
cfg=json.loads((src/'control-points.json').read_text())
results=json.loads((out/'test-results.json').read_text())
cities={(f['properties']['adm0name'],f['properties']['name']):f['geometry']['coordinates'] for f in json.loads((src/'cities.geojson').read_text())['features']}
countries={'gabon':'Gabon','senegal':'Senegal','tunisie':'Tunisia','colombie':'Colombia','indonesie':'Indonesia','egypte':'Egypt','russie':'Russia'}
geod=Geod(ellps='WGS84')
for name,c in cfg.items():
 xy=np.array(list(c['gcps'].values()),float)
 ll=np.array([cities[countries[name],n] for n in c['gcps']])
 design=np.c_[xy,np.ones(len(xy))]
 lon,lat=ll.mean(axis=0)
 projections={'mercator':'EPSG:3857','local_equidistant':f'+proj=eqc +lat_ts={lat} +lon_0={lon} +datum=WGS84', 'local_azimuthal':f'+proj=laea +lat_0={lat} +lon_0={lon} +datum=WGS84'}
 if name=='russie':projections['conic_hypothesis']='+proj=lcc +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84'
 comparisons={}
 for projection,crs in projections.items():
  fwd=Transformer.from_crs(4326,crs,always_xy=True); inv=Transformer.from_crs(crs,4326,always_xy=True)
  target=np.column_stack(fwd.transform(ll[:,0],ll[:,1]));pred=[]
  for j in range(len(xy)):
   keep=np.arange(len(xy))!=j
   co=np.linalg.lstsq(design[keep],target[keep],rcond=None)[0];pred.append(design[j]@co)
  pred=np.array(pred);plon,plat=inv.transform(pred[:,0],pred[:,1]);err=np.array(geod.inv(ll[:,0],ll[:,1],plon,plat)[2])/1000
  comparisons[projection]={'leave_one_out_rms_km':round(float(np.sqrt(np.mean(err**2))),2),'maximum_km':round(float(err.max()),2)}
 results[name]['projection_comparison']=comparisons
 mask=cv2.imread(str(src/f'{name}-classes.png'),cv2.IMREAD_GRAYSCALE)
 classes={}
 for k,risk in enumerate(['green','yellow','orange','red'],1):
  components,count=label(mask==k); counts=np.bincount(components.ravel())[1:]
  if not count:continue
  classes[risk]={'components':int(count),'components_at_most_4_pixels':int((counts<=4).sum()),'pixels_in_those_components':int(counts[counts<=4].sum())}
 results[name]['small_component_diagnostics']=classes
 results[name]['approved_for_publication']=False
 results[name]['validation_scope']='Source-pixel spot checks and city-based leave-one-out alignment; not independently surveyed boundary accuracy.'

restrictions=[
 {'country':'egypte','kind':'closed_to_civilians','evidence':'hatched map areas and accompanying text','geometry_status':'not_digitized','source_url':results['egypte']['source_url']},
 {'country':'indonesie','kind':'maritime_advisory','evidence':'accompanying text; no coloured sea polygons in source image','geometry_status':'text_only','source_url':results['indonesie']['source_url']},
 {'country':'colombie','kind':'island_inset','evidence':'San Andrés and Providencia inset','geometry_status':'separate_georeferencing_required','source_url':results['colombie']['source_url']},
 {'country':'colombie','kind':'city_access_exception','evidence':'small city symbols and access conditions in accompanying text','geometry_status':'point_and_text_review_required','source_url':results['colombie']['source_url']}
]
(out/'restrictions-review.json').write_text(json.dumps(restrictions,indent=2))
(out/'test-results.json').write_text(json.dumps(results,indent=2))
for name,r in results.items():
 print(name,r['projection_comparison'],r['small_component_diagnostics'])

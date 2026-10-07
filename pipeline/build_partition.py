import json
from pathlib import Path
import numpy as np
from PIL import Image
from rasterio.features import shapes,rasterize
from shapely.geometry import shape,mapping
from shapely.ops import unary_union,polygonize,transform
from shapely import coverage_is_valid,coverage_simplify
from pyproj import Transformer

root=Path(__file__).resolve().parent.parent;out=root/'private/extraction';src=root/'private/maps'
cfg=json.loads((src/'control-points.json').read_text())
results=json.loads((out/'test-results.json').read_text())
old=json.loads((out/'experimental-zones.geojson').read_text())['features']
cities={(f['properties']['adm0name'],f['properties']['name']):f['geometry']['coordinates'] for f in json.loads((src/'cities.geojson').read_text())['features']}
countries={'gabon':'Gabon','senegal':'Senegal','tunisie':'Tunisia','colombie':'Colombia','indonesie':'Indonesia','egypte':'Egypt'}
risks=['green','yellow','orange','red'];all_features=[]
to_area=Transformer.from_crs(4326,6933,always_xy=True).transform
fwd=Transformer.from_crs(4326,3857,always_xy=True);inv=Transformer.from_crs(3857,4326,always_xy=True)
def overlap_km2(features):
 by_class={}
 for f in features:by_class.setdefault(f['properties']['risk'],[]).append(shape(f['geometry']))
 groups=[transform(to_area,unary_union(geoms)) for geoms in by_class.values()]
 return sum(a.intersection(b).area for i,a in enumerate(groups) for b in groups[i+1:])/1e6

for name,city_country in countries.items():
 mask=np.asarray(Image.open(src/f'{name}-classes.png'))
 raw=[shape(g) for g,k in shapes(mask,mask=mask>0)]
 partition=[];values=[]
 for p in polygonize(unary_union([g.boundary for g in raw])):
  point=p.representative_point();k=int(mask[int(point.y),int(point.x)])
  if k:partition.append(p);values.append(k)
 assert coverage_is_valid(partition)
 simplified=list(coverage_simplify(partition,.5,simplify_boundary=False))
 assert coverage_is_valid(simplified)
 area_delta=unary_union(partition).symmetric_difference(unary_union(simplified)).area
 assert area_delta<1e-8
 roundtrip=rasterize(list(zip(simplified,values)),out_shape=mask.shape,dtype='uint8')
 cp=np.array(list(cfg[name]['gcps'].values()),float)
 ll=np.array([cities[city_country,n] for n in cfg[name]['gcps']])
 target=np.column_stack(fwd.transform(ll[:,0],ll[:,1]));co=np.linalg.lstsq(np.c_[cp,np.ones(len(cp))],target,rcond=None)[0]
 def pixel_geo(x,y,z=None):
  x=np.asarray(x)-.5;y=np.asarray(y)-.5
  return inv.transform(x*co[0,0]+y*co[1,0]+co[2,0],x*co[0,1]+y*co[1,1]+co[2,1])
 old_country=[f for f in old if f['properties']['country']==name]
 templates={f['properties']['risk']:f['properties'] for f in old_country}
 fs=[]
 for i,(p,k) in enumerate(zip(simplified,values)):
  props=dict(templates[risks[k-1]])
  identity=f'{cfg[name]["iso"]}-{risks[k-1]}-{props["source_sha256"][:8]}-{i}'
  props.update({'zone_id':identity,'zone_identity':'source_snapshot_component','method':'pixel partition; shared-edge simplification; manual city control points; affine fit','approved_for_publication':False})
  geom=transform(pixel_geo,p)
  assert geom.is_valid
  fs.append({'type':'Feature','id':identity,'properties':props,'geometry':mapping(geom)})
 new_overlap=overlap_km2(fs)
 assert new_overlap<1e-6
 results[name]['partition_validation']={'raw_partition_valid':True,'simplified_partition_valid':True,'source_coverage_change_square_pixels':area_delta,'source_classification_changed_pixels':int(np.count_nonzero(mask!=roundtrip)),'independent_contour_overlap_km2':round(overlap_km2(old_country),6),'shared_partition_overlap_km2':round(new_overlap,9),'exported_connected_zones':len(fs),'tiny_components_retained':True,'note':'Topology checks validate geometry against the classified raster, not the correctness of the image classification or advisory boundaries.'}
 (out/f'{name}-experimental.geojson').write_text(json.dumps({'type':'FeatureCollection','features':fs},separators=(',',':')))
 all_features.extend(fs)
 print(name,results[name]['partition_validation'])
results['russie']['valid_geometry']=None
(out/'experimental-zones.geojson').write_text(json.dumps({'type':'FeatureCollection','features':all_features},separators=(',',':')))
(out/'test-results.json').write_text(json.dumps(results,indent=2))

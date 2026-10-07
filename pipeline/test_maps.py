import json, hashlib, time, base64, io
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, binary_fill_holes
from scipy.ndimage import label as components
from scipy.interpolate import RBFInterpolator
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.ops import unary_union, transform
from pyproj import Transformer, Geod

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'private/extraction'
OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'private/maps'
palette=np.array([[194,215,100],[255,247,178],[245,160,77],[224,24,27]],dtype=float)
names=['green','yellow','orange','red']
configs=json.loads((SRC/'control-points.json').read_text())
city_countries={'gabon':'Gabon','senegal':'Senegal','tunisie':'Tunisia','colombie':'Colombia','indonesie':'Indonesia','egypte':'Egypt','russie':'Russia'}
cities={(f['properties']['adm0name'],f['properties']['name']):f['geometry']['coordinates'] for f in json.loads((SRC/'cities.geojson').read_text())['features']}
countries=json.loads((SRC/'countries.geojson').read_text())['features']
fwd=Transformer.from_crs(4326,3857,always_xy=True)
inv=Transformer.from_crs(3857,4326,always_xy=True)
geod=Geod(ellps='WGS84')
features=[]; results={}; panels=[]; overlays={}

def polygons(mask,tol):
 contours,hierarchy=cv2.findContours(mask.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
 out=[]
 if hierarchy is None: return []
 for i,c in enumerate(contours):
  if hierarchy[0,i,3]!=-1 or len(c)<3: continue
  holes=[]; j=hierarchy[0,i,2]
  while j!=-1:
   if len(contours[j])>=3: holes.append(contours[j][:,0,:])
   j=hierarchy[0,j,0]
  p=Polygon(c[:,0,:],holes)
  if not p.is_valid:p=p.buffer(0)
  if p.is_empty or p.area<2:continue
  p=p.simplify(tol,preserve_topology=True)
  out.extend(list(p.geoms) if p.geom_type=='MultiPolygon' else [p])
 return out

for name,cfg in configs.items():
 started=time.perf_counter()
 original=np.asarray(Image.open(SRC/f'{name}.jpg').convert('RGB'))
 dist=np.linalg.norm(original[:,:,None,:].astype(float)-palette[None,None,:,:],axis=3)
 labels=np.argmin(dist,axis=2).astype('uint8')+1
 labels[np.min(dist,axis=2)>48]=0
 naive={n:int((labels==k+1).sum()) for k,n in enumerate(names)}
 # Classes confirmed manually against the map and accompanying advisory text.
 allowed=cfg.get('allowed',{'gabon':[2],'senegal':[2,3],'tunisie':[2,3,4]}.get(name))
 allowed_dist=dist.copy()
 for k in range(1,5):
  if k not in allowed:allowed_dist[:,:,k-1]=np.inf
 labels=np.argmin(allowed_dist,axis=2).astype('uint8')+1
 labels[np.min(allowed_dist,axis=2)>48]=0
 labels[cfg['crop']:]=0
 for x0,y0,x1,y1 in cfg.get('exclusions',[]):labels[y0:y1,x0:x1]=0
 # Crops exclude the legend; blue locator insets are not risk colours.
 valid=labels>0
 footprint=binary_fill_holes(cv2.morphologyEx(valid.astype('uint8'),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8)))
 d,idx=distance_transform_edt(~valid,return_indices=True)
 repair=(~valid)&footprint&(d<=3)
 labels[repair]=labels[idx[0][repair],idx[1][repair]]
 color_polys={k:polygons(labels==k,1.0) for k in range(1,5)}
 cp=np.array(list(cfg['gcps'].values()),float)
 ll=np.array([cities[(city_countries[name],n)] for n in cfg['gcps']])
 design=np.c_[cp,np.ones(len(cp))]
 target=np.column_stack(fwd.transform(ll[:,0],ll[:,1]))
 coeff=np.linalg.lstsq(design,target,rcond=None)[0]
 def pixel_geo(x,y,z=None):
  x=np.asarray(x); y=np.asarray(y)
  return inv.transform(x*coeff[0,0]+y*coeff[1,0]+coeff[2,0],x*coeff[0,1]+y*coeff[1,1]+coeff[2,1])
 imbuf=io.BytesIO()
 Image.fromarray(original[:cfg['crop']]).save(imbuf,format='JPEG',quality=85)
 overlays[name]={'url':'data:image/jpeg;base64,'+base64.b64encode(imbuf.getvalue()).decode(),'coordinates':[list(pixel_geo(x,y)) for x,y in [(0,0),(original.shape[1],0),(original.shape[1],cfg['crop']),(0,cfg['crop'])]]}
 def errors(pred):
  lon,lat=inv.transform(pred[:,0],pred[:,1]);return np.asarray(geod.inv(ll[:,0],ll[:,1],lon,lat)[2])/1000
 loo=[]
 for j in range(len(cp)):
  keep=np.arange(len(cp))!=j
  co=np.linalg.lstsq(design[keep],target[keep],rcond=None)[0]
  loo.append(design[j]@co)
 looerr=errors(np.array(loo))
 tps_predictions=[]
 for j in range(len(cp)):
  keep=np.arange(len(cp))!=j
  tps_predictions.append(RBFInterpolator(cp[keep]/1000,target[keep],kernel='thin_plate_spline')(cp[j:j+1]/1000)[0])
 tpserr=errors(np.array(tps_predictions))
 country=shape(next(f['geometry'] for f in countries if f['properties']['ADM0_A3']==cfg['iso']))
 yy,xx=np.where(valid[:cfg['crop']])
 mnx,mny,mxx,mxy=country.bounds
 bboxll=np.c_[mnx+(cp[:,0]-xx.min())/(xx.max()-xx.min())*(mxx-mnx),mxy-(cp[:,1]-yy.min())/(yy.max()-yy.min())*(mxy-mny)]
 bboxerr=np.asarray(geod.inv(ll[:,0],ll[:,1],bboxll[:,0],bboxll[:,1])[2])/1000
 file_features=[]
 for k,polys in color_polys.items():
  if not polys:continue
  geom=transform(pixel_geo,unary_union(polys))
  f={'type':'Feature','id':f'{cfg["iso"]}-{names[k-1]}','properties':{'country':name,'iso3':cfg['iso'],'risk':names[k-1],'source_url':f'https://www.diplomatie.gouv.fr/fr/information-par-pays/{name}/conseils-aux-voyageurs-securite','method':'colour segmentation; manual city control points; affine fit','review_status':'experimental_unreviewed','retrieved_at':cfg.get('retrieved_at'),'source_sha256':hashlib.sha256((SRC/f'{name}.jpg').read_bytes()).hexdigest()},'geometry':mapping(geom)}
  f['properties'].update({'review_status':cfg.get('review_status','experimental_unreviewed'),'limitations':cfg.get('limitations',[]),'map_date':cfg.get('map_date'),'page_date':cfg.get('page_date'),'source_image_url':cfg.get('image_url')})
  if not cfg.get('source_only'):
   file_features.append(f);features.append(f)
 fc={'type':'FeatureCollection','features':file_features}
 raw=json.dumps(fc,separators=(',',':'))
 (OUT/f'{name}-experimental.geojson').write_text(raw)
 # Compare increasingly simplified traces in source pixel space.
 simpl=[]
 for tol in [0,0.5,1,2,4]:
  total_vertices=0;changed=0
  for k in range(1,5):
   reconstructed=np.zeros(labels.shape,np.uint8)
   for p in polygons(labels==k,tol):
    rings=[np.rint(np.asarray(p.exterior.coords)).astype('int32')]+[np.rint(np.asarray(r.coords)).astype('int32') for r in p.interiors]
    total_vertices+=sum(len(r) for r in rings)
    cv2.fillPoly(reconstructed,rings,1)
   changed+=int(np.logical_xor(reconstructed>0,labels==k).sum())
  simpl.append({'tolerance_px':tol,'vertices':total_vertices,'summed_class_xor_pixels':changed})
 results[name]={'source_size':list(original.shape[:2][::-1]),'naive_pixels_including_legend':naive,'cropped_repaired_pixels':{n:int((labels==k+1).sum()) for k,n in enumerate(names)},'repaired_pixels':int(repair.sum()),'unresolved_in_footprint_pixels':int((footprint&(labels==0)).sum()),'control_point_count':len(cp),'bbox_city_rmse_km':round(float(np.sqrt(np.mean(bboxerr**2))),2),'affine_leave_one_city_out_rmse_km':round(float(np.sqrt(np.mean(looerr**2))),2),'affine_leave_one_city_out_max_km':round(float(looerr.max()),2),'valid_geometry':all(shape(f['geometry']).is_valid for f in file_features),'geojson_bytes':len(raw),'simplification':simpl,'processing_seconds':round(time.perf_counter()-started,2)}
 preview=np.full(original.shape,245,np.uint8)
 results[name]['tps_leave_one_city_out_rmse_km']=round(float(np.sqrt(np.mean(tpserr**2))),2)
 results[name]['tps_leave_one_city_out_max_km']=round(float(tpserr.max()),2)
 results[name]['review_status']=cfg.get('review_status','experimental_unreviewed')
 results[name]['source_only']=cfg.get('source_only',False)
 results[name]['limitations']=cfg.get('limitations',[])
 results[name]['checkpoints']=[{'pixel':[x,y],'expected':int(k),'actual':int(labels[y,x]),'pass':bool(labels[y,x]==k)} for x,y,k in cfg.get('checkpoints',[])]
 results[name]['components_before_repair']={names[k-1]:int(components((valid)&(np.argmin(allowed_dist,axis=2)+1==k))[1]) for k in allowed}
 results[name]['components_after_repair']={names[k-1]:int(components(labels==k)[1]) for k in allowed}
 results[name]['candidate_polygon_count']={names[k-1]:len(color_polys[k]) for k in allowed}
 results[name]['exported_geometry']=not cfg.get('source_only',False)
 results[name]['source_image_url']=cfg.get('image_url')
 results[name]['source_url']=f'https://www.diplomatie.gouv.fr/fr/information-par-pays/{name}/conseils-aux-voyageurs-securite'
 for field in ['map_date','page_date','zone_text_date']:results[name][field]=cfg.get(field)
 Image.fromarray(labels).save(SRC/f'{name}-classes.png')
 for k,pal in enumerate(palette.astype('uint8'),1): preview[labels==k]=pal
 preview[footprint&(labels==0)]=[100,100,100]
 image=Image.fromarray(preview[:cfg['crop']])
 orig=Image.fromarray(original[:cfg['crop']])
 width=460; height=round(image.height*width/image.width)
 panel=Image.new('RGB',(width*2,height+48),'white'); draw=ImageDraw.Draw(panel)
 draw.text((10,12),name.upper()+' | official image',fill='black')
 draw.text((width+10,12),'Extracted classes | grey = unresolved',fill='black')
 panel.paste(orig.resize((width,height)),(0,48));panel.paste(image.resize((width,height)),(width,48))
 panels.append(panel)
 panel.save(OUT/f'{name}-comparison.png')
 # Standalone SVG retains pixel coordinates: demonstrates why SVG alone is not geographic data.
 paths=[]
 for k,polys in color_polys.items():
  for p in polys:
   d=' '.join('M'+' L'.join(f'{x:.1f},{y:.1f}' for x,y in ring.coords)+' Z' for ring in [p.exterior,*p.interiors])
   color='#'+''.join(f'{v:02x}' for v in palette[k-1].astype(int))
   paths.append(f'<path fill="{color}" fill-rule="evenodd" d="{d}"/>')
 (OUT/f'{name}-pixel-trace.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {original.shape[1]} {cfg["crop"]}">'+''.join(paths)+'</svg>')

sheet=Image.new('RGB',(920,sum(p.height for p in panels)),'white');y=0
for panel in panels:sheet.paste(panel,(0,y));y+=panel.height
sheet.save(OUT/'extraction-comparison.png')
(OUT/'test-results.json').write_text(json.dumps(results,indent=2))
(OUT/'experimental-zones.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},separators=(',',':')))
(SRC/'control-points.json').write_text(json.dumps(configs,indent=2))
(SRC/'overlays.json').write_text(json.dumps(overlays))
basemap=[]
for f in countries:
 geom=shape(f['geometry']).simplify(.015,preserve_topology=True)
 basemap.append({'type':'Feature','properties':{'name':f['properties']['NAME'],'iso3':f['properties']['ADM0_A3']},'geometry':mapping(geom)})
(SRC/'basemap.json').write_text(json.dumps({'type':'FeatureCollection','features':basemap},separators=(',',':')))
print(json.dumps(results,indent=2))

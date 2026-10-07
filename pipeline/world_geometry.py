import json
import hashlib
import re
from datetime import datetime
from world_countries import countries as country_features
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from affine import Affine
from pyproj import Transformer
from rasterio.features import rasterize, shapes
from scipy.ndimage import distance_transform_edt
from scipy.optimize import minimize
from shapely import coverage_simplify, make_valid, set_precision
from shapely.geometry import shape, mapping, box, MultiPolygon
from shapely.ops import transform, unary_union

ROOT=Path(__file__).resolve().parent.parent
WORK=ROOT/'private/world'
PALETTE=np.array([[197,215,107],[255,246,177],[247,170,78],[230,0,0]])
RISKS=['green','yellow','orange','red']


def polygonal(g):
    if g.geom_type in ('Polygon','MultiPolygon'):return g
    return MultiPolygon([p for p in getattr(g,'geoms',[]) if p.geom_type=='Polygon'])


def classify(rgb):
    ds=np.linalg.norm(rgb[:,:,None,:].astype(float)-PALETTE,axis=3)
    classes=(ds.argmin(2)+1).astype('uint8')
    classes[ds.min(2)>55]=0
    return classes


def fit_projection(rgb,countries):
    small=rgb[::4,::4]
    mask=(classify(small)>0).astype('uint8')
    h,w=mask.shape
    mask[:round(h*.078)]=0;mask[round(h*.919):]=0
    mask[:,:round(w*.009)]=0;mask[:,round(w*.991):]=0
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    gs=[shape(f['geometry']).intersection(box(-180,-60,180,85)).simplify(.05) for f in countries if f['properties']['ADM0_A3']!='ATA']
    fits=[]
    for proj in ['eqc','mill','gall']:
        tr=Transformer.from_crs('EPSG:4326',f'+proj={proj} +datum=WGS84',always_xy=True)
        geo=[make_valid(transform(tr.transform,g)) for g in gs if not g.is_empty]
        bounds=unary_union(geo).bounds
        sx=(w-18)/(bounds[2]-bounds[0]);sy=(h*.9-h*.094)/(bounds[3]-bounds[1])
        x0=9-bounds[0]*sx;y0=h*.094+bounds[3]*sy
        base=rasterize([(g,1) for g in geo],out_shape=(h,w),transform=~Affine(sx,0,x0,0,-sy,y0),dtype='uint8')
        def cost(p):
            a,b,tx,ty=p
            v=cv2.warpAffine(base,np.array([[a,0,tx],[0,b,ty]],dtype='float32'),(w,h),flags=cv2.INTER_NEAREST)
            return 1-np.count_nonzero(v&mask)/np.count_nonzero(v|mask)
        opt=minimize(cost,[1,1,0,0],method='Powell',bounds=[(.8,1.2),(.8,1.2),(-60,60),(-60,60)],options={'maxiter':80,'xtol':.0001,'ftol':.000001})
        a,b,tx,ty=opt.x
        fits.append({'projection':proj,'land_mask_iou':float(1-opt.fun),'pixel_transform':[float(4*sx*a),0,float(4*(x0*a+tx)),0,float(-4*sy*b),float(4*(y0*b+ty))]})
    best=max(fits,key=lambda f:f['land_mask_iou'])
    if best['land_mask_iou']<.9:raise ValueError('World map alignment below 90% land-mask IoU; inspect the new layout before using it.')
    return best,fits


def build():
    path=WORK/'region-0.jpg'
    rgb=np.asarray(Image.open(path).convert('RGB'))
    countries=country_features()
    source_url=json.loads((WORK/'region-sources.json').read_text())[0]
    source_date=datetime.strptime(re.search(r'/(20[0-9]{6})_',source_url)[1],'%Y%m%d').date().isoformat()
    fit,fits=fit_projection(rgb,countries)
    print('World projection:',fit,flush=True)
    tr=Transformer.from_crs('EPSG:4326',f'+proj={fit["projection"]} +datum=WGS84',always_xy=True)
    inv=Transformer.from_crs(f'+proj={fit["projection"]} +datum=WGS84','EPSG:4326',always_xy=True)
    matrix=Affine(*fit['pixel_transform'])
    classes=classify(rgb[::2,::2]);h,w=classes.shape
    classes[:round(h*.078)]=0;classes[round(h*.919):]=0
    classes[:,:round(w*.009)]=0;classes[:,round(w*.991):]=0
    land_pixel=[]
    for f in countries:
        if f['properties']['ADM0_A3']=='ATA':continue
        g=shape(f['geometry']).intersection(box(-180,-60,180,85))
        def pixel(x,y,z=None):
            a,b=tr.transform(x,y)
            return (np.asarray(a)*matrix.a+matrix.c)/2,(np.asarray(b)*matrix.e+matrix.f)/2
        if not g.is_empty:land_pixel.append((make_valid(transform(pixel,g)),1))
    expected=rasterize(land_pixel,out_shape=(h,w),dtype='uint8')
    distance,nearest=distance_transform_edt(classes==0,return_indices=True)
    fill=(classes==0)&(distance<=2)&(expected>0)
    classes[fill]=classes[nearest[0][fill],nearest[1][fill]]
    parts=[];values=[]
    for geometry,k in shapes(classes,mask=classes>0):
        p=shape(geometry)
        if p.area<1:continue
        parts.append(p);values.append(int(k))
    simplified=coverage_simplify(parts,1.0,simplify_boundary=True)
    def lonlat(x,y,z=None):
        return inv.transform((np.asarray(x)*2-matrix.c)/matrix.a,(np.asarray(y)*2-matrix.f)/matrix.e)
    grouped={}
    for risk in range(1,5):
        ps=[make_valid(transform(lonlat,g)) for g,k in zip(simplified,values) if k==risk]
        grouped[risk]=unary_union(ps)
    features=[];coverage={}
    equalarea=Transformer.from_crs(4326,6933,always_xy=True).transform
    for f in countries:
        p=f['properties'];iso=p['ADM0_A3']
        if iso=='FRA':coverage[iso]=0;continue
        country=shape(f['geometry']).simplify(.04,preserve_topology=True)
        gs=[]
        for k,g in grouped.items():
            clipped=polygonal(make_valid(g.intersection(country)))
            if clipped.is_empty:continue
            clipped=set_precision(clipped,.00001)
            if clipped.is_empty:continue
            props={'iso3':iso,'risk':RISKS[k-1],'provider':'france_diplomatie','resolution':'world_overview','zone_id':iso+'-world-'+RISKS[k-1],'map_date':source_date}
            features.append({'type':'Feature','properties':props,'geometry':mapping(clipped)})
            gs.append(clipped)
        area=transform(equalarea,country).area
        coverage[iso]=round(min(1,transform(equalarea,unary_union(gs)).area/area),4) if area else 0
    fc={'type':'FeatureCollection','features':features}
    (WORK/'world-zones.geojson').write_text(json.dumps(fc,separators=(',',':')))
    report={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_date':source_date,'source_url':source_url,'projection':fit,'projection_candidates':fits,'source_dimensions':[rgb.shape[1],rgb.shape[0]],'working_pixel_size':2,'simplification_tolerance_source_pixels':2,'country_coverage':coverage,'feature_count':len(features),'geometry_valid':all(shape(f['geometry']).is_valid for f in features),'review_status':'candidate','rights_status':'needs_review','limitations':['World-scale overview; not a detailed boundary survey.','Land-mask fit measures alignment, not the accuracy of advisory boundaries.','Western Alaska and very small islands can be outside the source frame or too small to classify.','White France in the source is unclassified, not a green advisory.','Country pages can be more recent than the overview image.']}
    (WORK/'geometry-report.json').write_text(json.dumps(report,indent=2))
    print('World zones:',len(features),'features;',sum(v>.5 for v in coverage.values()),'countries/territories with >50% mapped area',flush=True)


if __name__=='__main__':build()

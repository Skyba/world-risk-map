import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely import make_valid, set_precision
from shapely.ops import unary_union
import manage
from display_geometry import smooth_overview
from world_sources import ROOT, fetch, write
sys.path.insert(0,str(ROOT/'pipeline'))
from world_countries import countries

WORK=ROOT/'private/world'


def collection(fs):return {'type':'FeatureCollection','features':fs}


def current(snapshot=None):
    snapshot=snapshot or manage.load(ROOT/'data/world-current.json')['snapshot']
    date.fromisoformat(snapshot)
    return manage.load(ROOT/'data/world-snapshots'/f'{snapshot}.json')


def country_bounds(g):
    polys=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
    main=max(polys,key=lambda p:p.area)
    a,b,c,d=main.bounds
    if c-a<.2:a-=.12;c+=.12
    if d-b<.2:b-=.12;d+=.12
    return [round(x,5) for x in [a,b,c,d]]


def create_snapshot(day):
    date.fromisoformat(day)
    registry=manage.load(WORK/'registry.json')
    world_geo=manage.load(WORK/'world-zones.geojson')['features']
    report=manage.load(WORK/'geometry-report.json')
    if hashlib.sha256((WORK/'region-0.jpg').read_bytes()).hexdigest()!=report['source_sha256']:
        raise ValueError('World image changed after extraction; rerun geometry extraction.')
    old=manage.current()
    checks=sorted((ROOT/'private/updates').glob('*.json'))
    latest_check=manage.load(checks[-1]).get('countries',{}) if checks else {}
    details={}
    for slug,c in old['countries'].items():
        check=latest_check.get(slug,{})
        if c['geometry'] and not (check.get('status')=='checked' and check.get('map_sha256')!=c['source']['map_sha256']):
            iso=manage.decode(next(iter(c['geometry'].values())))['features'][0]['properties']['iso3']
            details[iso]=(slug,c)
    country_features=countries()
    overseas={f['properties']['ADM0_A3']:shape(f['geometry']).buffer(.03) for f in country_features if f['properties']['ADM0_A3'] in ['GUF','GLP','MTQ','REU','MYT']}
    city_groups={};major=[]
    raw_places=manage.load(ROOT/'private/maps/cities.geojson')['features']
    seen=set()
    for f in sorted(raw_places,key=lambda f:-f['properties']['pop_max']):
        p=f['properties'];iso=p['adm0_a3'];coords=f['geometry']['coordinates']
        if iso=='FRA':
            for candidate,g in overseas.items():
                if g.covers(shape(f['geometry'])):iso=candidate;break
        key=(iso,p['name'],round(coords[0],2),round(coords[1],2))
        if key in seen:continue
        seen.add(key)
        z=2 if p['adm0cap'] else 4 if p['pop_max']>=500000 else 5 if p['pop_max']>=100000 else 6
        cp={'id':str(p['ne_id']),'name':p['name'],'iso3':iso,'country_name':registry.get(iso,{}).get('name',p['adm0name']),'capital':bool(p['adm0cap']),'kind':'city','min_zoom':z,'priority':z*10000000-p['pop_max']}
        city={'type':'Feature','properties':cp,'geometry':{'type':'Point','coordinates':[round(v,5) for v in coords]}}
        city_groups.setdefault(iso,[]).append(city)
        if z<=4:major.append(city)
    land=[];rows={}
    for f in country_features:
        p=f['properties'];iso=p['ADM0_A3'];r=registry[iso]
        g=set_precision(make_valid(shape(f['geometry'])).simplify(.035,preserve_topology=True),.00001)
        land.append({'type':'Feature','properties':{'iso3':iso,'name':r['name']},'geometry':mapping(g)})
        advice=r['advice']
        stable_advice={k:v for k,v in advice.items() if k not in ['checked_at','page_sha256','refresh_error']} if advice else None
        row={'iso3':iso,'name':r['name'],'french_name':r['french_name'],'bounds':country_bounds(g),'source_status':r['source_status'],'advice':manage.store(stable_advice,'public') if advice else None,'advice_checked_at':advice.get('checked_at') if advice else None,'source_page_sha256':advice.get('page_sha256') if advice else None,'source_check_error':advice.get('refresh_error') if advice else None,'overview':None,'local_overview':None,'detail':None,'exceptions':None,'places':manage.store(collection(city_groups.get(iso,[])),'public'),'coverage_fraction':report['country_coverage'].get(iso,0),'geometry_source':{'provider':'france_diplomatie','url':report['source_url'],'map_date':report['source_date']},'review_status':'candidate','rights_status':'needs_review'}
        fs=[f for f in world_geo if f['properties']['iso3']==iso]
        if fs:row['overview']=manage.store(manage.topology(collection(fs)),'private')
        if iso in details:
            slug,c=details[iso]
            if c['geometry']:
                for lod,field in [('overview','local_overview'),('detail','detail')]:
                    geo=manage.decode(c['geometry'][lod])
                    for z in geo['features']:
                        z['properties'].update({'provider':'france_diplomatie','resolution':'country_map','map_date':c['source']['map_date']})
                    row[field]=manage.store(manage.topology(geo),'private')
                row['detail_source']=c['source']
                if c.get('exceptions'):
                    extra=manage.decode(c['exceptions'])
                    for point in extra['features']:point['properties']['iso3']=iso
                    row['exceptions']=manage.store(extra,'private')
        rows[iso]=row
    search_index={'cities':[[f['properties']['id'],f['properties']['name'],iso,*f['geometry']['coordinates'],f['properties']['capital']] for iso,fs in city_groups.items() if iso in rows for f in fs]}
    result={'schema_version':2,'snapshot_date':day,'cadence':'manual_monthly','countries':rows,'common':{'land':manage.store(manage.topology(collection(land)),'public'),'major_places':manage.store(collection(major),'public'),'search_index':manage.store(search_index,'public')},'world_source':{'url':report['source_url'],'map_date':report['source_date'],'image_sha256':report['source_sha256'],'land_mask_iou':report['projection']['land_mask_iou']},'source_coverage':manage.load(WORK/'source-coverage.json'),'geometry_coverage':{'countries_with_zones':sum(bool(c['overview']) for c in rows.values()),'countries_with_majority_coverage':sum(c['coverage_fraction']>.5 for c in rows.values()),'detailed_countries':sum(bool(c['detail']) for c in rows.values()),'city_count':sum(len(c) for c in city_groups.values())},'incident_records':[]}
    path=ROOT/'data/world-snapshots'/f'{day}.json'
    if path.exists() and manage.encoded(manage.load(path))!=manage.encoded(result):raise ValueError('World snapshots are immutable. Use another snapshot date.')
    write(path,result);write(ROOT/'data/world-current.json',{'snapshot':day})
    print('Saved world snapshot',day,flush=True)
    return result


def difference(before,after):
    result=[]
    for iso,c in after['countries'].items():
        previous=before['countries'].get(iso)
        if not previous:result.append({'iso3':iso,'kind':'new_coverage','reasons':['New country record']});continue
        reasons=[]
        for field in ['overview','local_overview','detail','exceptions']:
            old=previous.get(field);new=c.get(field)
            if (old or {}).get('sha256')!=(new or {}).get('sha256'):
                reasons.append('Geometry or mapped coverage changed');break
        pa=manage.read_object(previous['advice']) if previous.get('advice') else {}
        ca=manage.read_object(c['advice']) if c.get('advice') else {}
        if pa.get('provider')!=ca.get('provider'):reasons.append('Advice provider changed')
        else:
            old_content=pa.get('advice_sha256') if pa.get('advice_sha256') and ca.get('advice_sha256') else {'context':pa.get('context'),'alerts':pa.get('alert_status')}
            new_content=ca.get('advice_sha256') if pa.get('advice_sha256') and ca.get('advice_sha256') else {'context':ca.get('context'),'alerts':ca.get('alert_status')}
            if old_content!=new_content:reasons.append('Official advice content changed')
        if reasons:result.append({'iso3':iso,'kind':'new_coverage' if not previous.get('overview') and c.get('overview') else 'source_or_geometry_change','reasons':reasons})
    return result


def public_blockers(s):
    return [iso for iso,c in s['countries'].items() if any(c.get(k) for k in ['overview','local_overview','detail','exceptions']) and (c['review_status']!='approved' or c['rights_status']!='cleared' or any(c[k]['scope']!='public' for k in ['overview','local_overview','detail','exceptions'] if c.get(k)))]


def release_authorized(s):
    path=ROOT/'data/publication.json'
    if not path.exists():return False
    release=manage.load(path)
    return release.get('distribution')=='public' and release.get('snapshot')==s['snapshot_date'] and release.get('snapshot_sha256')==hashlib.sha256(manage.encoded(s)).hexdigest()


def build(preview=True):
    latest=current()
    if not preview and public_blockers(latest) and not release_authorized(latest):raise ValueError('Public world build withheld: no recorded release decision for this snapshot.')
    if not preview:validate(latest)
    target=ROOT/('preview' if preview else 'dist')
    target.mkdir(exist_ok=True);(target/'assets').mkdir(exist_ok=True);(target/'snapshots').mkdir(exist_ok=True)
    for source,name in [('world.html','index.html'),('world.js','world.js'),('world.css','world.css')]:shutil.copyfile(ROOT/'src'/source,target/name)
    if not preview:
        page=target/'index.html';page.write_text(page.read_text().replace('PRIVATE PREVIEW','BETA'))
        script=target/'world.js';script.write_text(script.read_text().replace('Independent preview','Independent map'))
    emitted=set();display_cache={};display_metrics={}
    def display(ref):
        key=ref['sha256']
        if key not in display_cache:
            display_cache[key],display_metrics[key]=smooth_overview(manage.read_object(ref))
        return display_cache[key]
    def asset(ref,smoothed=False):
        value=display(ref) if smoothed else None
        key=hashlib.sha256(manage.encoded(value)).hexdigest() if smoothed else ref['sha256'];relative=f'assets/{key}.json'
        if key not in emitted:
            if value is None:
                value=manage.read_object(ref)
                value=manage.decode(ref) if value.get('type')=='Topology' else value
            (target/relative).write_bytes(manage.encoded(value));emitted.add(key)
        return relative
    snapshots=sorted((ROOT/'data/world-snapshots').glob('*.json'))
    previous=None;history=[]
    for path in snapshots:
        s=manage.load(path)
        if not preview and public_blockers(s) and not release_authorized(s):continue
        countries_out={}
        global_features=[];fallback_features=[]
        land=manage.decode(s['common']['land'])
        for iso,c in s['countries'].items():
            row={k:v for k,v in c.items() if k not in ('review_status','rights_status')}
            for field in ['advice','overview','local_overview','detail','exceptions','places']:
                if c.get(field):row[field]=asset(c[field],smoothed=field=='overview')
            if c.get('overview'):global_features.extend(display(c['overview'])['features'])
            if c['source_status']=='uk_fallback':
                f=next((f for f in land['features'] if f['properties']['iso3']==iso),None)
                if f:fallback_features.append(f)
            countries_out[iso]=row
        over_hash=hashlib.sha256(manage.encoded(collection(global_features))).hexdigest()
        over_path=f'assets/{over_hash}.json';(target/over_path).write_bytes(manage.encoded(collection(global_features)))
        fallback_hash=hashlib.sha256(manage.encoded(collection(fallback_features))).hexdigest()
        fallback_path=f'assets/{fallback_hash}.json';(target/fallback_path).write_bytes(manage.encoded(collection(fallback_features)))
        manifest={'date':s['snapshot_date'],'countries':countries_out,'land':asset(s['common']['land']),'major_places':asset(s['common']['major_places']),'search_index':asset(s['common']['search_index']),'overview':over_path,'fallback_land':fallback_path,'world_source':s['world_source'],'geometry_coverage':s['geometry_coverage'],'source_coverage':s['source_coverage'],'previous_snapshot':previous['snapshot_date'] if previous else None,'changes':difference(previous,s) if previous else []}
        write(target/'snapshots'/path.name,manifest)
        history.append(s['snapshot_date']);previous=s
    write(target/'catalogue.json',{'current':latest['snapshot_date'],'snapshots':history})
    write(target/'smoothing-report.json',{'method':'Bounded corner rounding on arcs shared by different world-overview risk colours; country and coverage boundaries remain fixed. Source snapshots are unchanged.','objects':display_metrics})
    print(target/'index.html',flush=True)
    return target/'index.html'


def validate(s):
    from shapely.ops import unary_union
    n=0
    for iso,c in s['countries'].items():
        for field in ['overview','local_overview','detail']:
            if not c.get(field):continue
            features=manage.decode(c[field])['features'];geometries=[shape(f['geometry']) for f in features]
            if not all(g.is_valid for g in geometries):raise ValueError('Invalid geometry: '+iso)
            groups=[unary_union([g for g,f in zip(geometries,features) if f['properties']['risk']==risk]) for risk in ['green','yellow','orange','red']]
            if sum(a.intersection(b).area for i,a in enumerate(groups) for b in groups[i+1:])>1e-8:raise ValueError('Overlapping risk classes: '+iso)
            n+=len(features)
        if c['advice']:
            a=manage.read_object(c['advice'])
            if a['provider']=='france_diplomatie' and c['source_status']!='french':raise ValueError('Source attribution mismatch')
            if a['provider']=='uk_fcdo' and c['source_status']!='uk_fallback':raise ValueError('Fallback attribution mismatch')
    return {'polygon_features_validated':n,'country_records':len(s['countries']),'source_coverage':s['source_coverage'],'geometry_coverage':s['geometry_coverage'],'publication_blockers':len(public_blockers(s))}


def update():
    from world_sources import get_french
    from world_registry import build as registry
    get_french(refresh=True);registry(refresh=True)
    old=manage.current()
    detail_check,_=manage.check_sources(old,list(old['countries']))
    for slug,result in detail_check['countries'].items():
        if result.get('map_changed'):print('Country detail needs re-extraction before inclusion:',slug)
        if result['status']=='error':print('Country source check failed; retained data is not newly verified:',slug)
    url=manage.load(WORK/'region-sources.json')[0]
    raw,_=fetch(url)
    image_path=WORK/'region-0.jpg'
    changed=not image_path.exists() or hashlib.sha256(raw).digest()!=hashlib.sha256(image_path.read_bytes()).digest()
    image_path.write_bytes(raw)
    if changed or not (WORK/'geometry-report.json').exists():subprocess.run([sys.executable,str(ROOT/'pipeline/world_geometry.py')],check=True)
    print('Source staging complete. Review changed pages, world alignment, country maps and rights before creating a new dated snapshot. The current snapshot is unchanged.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Worldwide local map and manual monthly source staging; never publishes.')
    sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('snapshot');q.add_argument('--date',required=True)
    q=sub.add_parser('build');q.add_argument('--preview',action='store_true')
    sub.add_parser('update');sub.add_parser('validate')
    args=p.parse_args()
    try:
        if args.cmd=='snapshot':create_snapshot(args.date)
        elif args.cmd=='build':build(args.preview)
        elif args.cmd=='update':update()
        elif args.cmd=='validate':print(json.dumps(validate(current()),indent=2))
    except (ValueError,FileNotFoundError) as e:print(str(e),file=sys.stderr);sys.exit(2)

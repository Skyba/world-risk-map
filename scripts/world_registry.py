import concurrent.futures
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import pycountry
from world_sources import ROOT, CACHE, fetch, uk, norm, write
sys.path.insert(0,str(ROOT/'pipeline'))
from world_countries import countries

FR_CODES={'Groenland':'GRL','Hong Kong':'HKG','Macao':'MAC','Israël/Palestine':'ISR','Royaume-Uni':'GBR','Saint-Christophe-et-Niévès':'KNA','Taïwan':'TWN','Timor oriental':'TLS'}
UK_NAMES={'ATA':'Antarctica/British Antarctic Territory','ATF':None,'BES':'Bonaire/St Eustatius/Saba','COK':'Cook Islands, Tokelau and Niue','NIU':'Cook Islands, Tokelau and Niue','TKL':'Cook Islands, Tokelau and Niue','SHN':'St Helena, Ascension and Tristan da Cunha','BLM':'St Martin and St Barthélemy','MAF':'St Martin and St Barthélemy','SXM':'St Maarten','SPM':'St Pierre & Miquelon','PCN':'Pitcairn Island','PSE':'Palestine','XKX':'Kosovo','SAH':'Western Sahara','ESH':'Western Sahara'}


def build(refresh=False):
    fr=json.loads((ROOT/'private/world/french-sources.json').read_text())
    by_iso={}
    for r in fr:
        if r['status']!='ok':continue
        r['iso3']=FR_CODES.get(r['name'],r.get('iso3'))
        page=CACHE/f'fr-{r["id"]}.html'
        if page.exists():
            soup=BeautifulSoup(page.read_bytes(),'html.parser')
            r['page_title']=soup.h1.get_text(' ',strip=True)
            body=' '.join(p.get_text(' ',strip=True) for p in soup.select('article.node--type-fiche-pays-article-cav .fr-prose'))
            import hashlib
            r['advice_sha256']=hashlib.sha256(body.encode()).hexdigest()
        if r['iso3']:by_iso[r['iso3']]=r
        if r['name']=='Israël/Palestine':by_iso['PSE']=r
    raw,_=fetch('https://www.gov.uk/foreign-travel-advice')
    soup=BeautifulSoup(raw,'html.parser')
    uk_links={norm(a.get_text(' ',strip=True)):a['href'].split('/')[-1] for a in soup.select('a[href]') if a['href'].startswith('/foreign-travel-advice/') and len(a['href'].split('/'))==3}
    requested={};rows={}
    for f in countries():
        p=f['properties'];iso=p['ADM0_A3'];std=p.get('ISO_A3_EH',iso)
        if std=='-99':std={'KOS':'XKX','SAH':'ESH','CYN':'CYP','SOL':'SOM'}.get(iso,iso)
        source=by_iso.get(std) or by_iso.get(iso)
        row={'iso3':iso,'standard_iso3':std,'name':p.get('NAME_EN') or p['NAME'],'french_name':p.get('NAME_FR'),'advice':source,'source_status':'french' if source else 'unavailable'}
        if not source and iso!='CLP':
            pc=pycountry.countries.get(alpha_3=std)
            names=[UK_NAMES.get(std,''),p.get('NAME_EN',''),p.get('NAME_LONG',''),p['NAME']]
            if pc:names.extend([pc.name,getattr(pc,'common_name','')])
            slug=next((uk_links.get(norm(n)) for n in names if n and norm(n) in uk_links),None)
            if slug:requested[iso]=slug
        rows[iso]=row
    print('UK fallback destinations:',requested,flush=True)
    def get(pair):
        iso,slug=pair
        try:return iso,uk(slug,refresh)
        except Exception as e:
            cached=CACHE/f'uk-{slug}.json'
            if cached.exists():return iso,{**json.loads(cached.read_text()),'refresh_error':str(e)}
            return iso,{'status':'error','error':str(e),'provider':'uk_fcdo'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for iso,result in pool.map(get,requested.items()):
            if result['status']=='ok':rows[iso].update({'advice':result,'source_status':'uk_fallback'})
            else:rows[iso]['source_error']=result['error']
    write(ROOT/'private/world/registry.json',rows)
    report={'france_diplomatie':sum(r['source_status']=='french' for r in rows.values()),'uk_fallback':sum(r['source_status']=='uk_fallback' for r in rows.values()),'without_dedicated_advice':[{'iso3':k,'name':v['name']} for k,v in rows.items() if not v['advice']]}
    write(ROOT/'private/world/source-coverage.json',report)
    print(report,flush=True)
    return rows


if __name__=='__main__':build('--refresh' in sys.argv)

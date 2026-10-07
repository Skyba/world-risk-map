import argparse
import concurrent.futures
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import pycountry
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'private/world/sources'
BASE = 'https://www.diplomatie.gouv.fr'
INDEX = BASE + '/fr/conseils-aux-voyageurs'


def norm(s):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def fetch(url, data=None):
    for attempt in range(3):
        try:
            req = Request(url, data=data, headers={'User-Agent': 'WorldRiskMap/0.2 (local manual advisory research)'})
            with urlopen(req, timeout=25) as response:
                return response.read(), response.url
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1+attempt)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def text_context(article):
    start = next((h for h in article.select('h3,h4') if re.search('Risques encourus|Risques et recommandations', h.get_text(), re.I)), None)
    nodes = list(start.find_all_next(['h2','h3','h4','h5','p'])) if start else list(article.select('.fr-prose h3,.fr-prose h4,.fr-prose p'))
    paragraphs, tags = [], []
    for node in nodes:
        text = node.get_text(' ', strip=True)
        if node.name == 'h2' or re.search('Recommandations générales|Numéros utiles', text, re.I):
            break
        if node.name.startswith('h') and 3 < len(text) < 95:
            tags.append(text)
        elif node.name == 'p' and 50 < len(text) and not re.search('Dernière actualisation|information toujours valable|Fil d.Ariane', text, re.I):
            paragraphs.append(text)
    if not paragraphs:
        paragraphs = [p.get_text(' ',strip=True) for p in article.select('.fr-prose p') if 60 < len(p.get_text()) and not re.search('actualisation|date du jour|Fil d.Ariane',p.get_text(),re.I)]
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ý])', paragraphs[0]) if paragraphs else []
    excerpt = ' '.join(sentences[:2])
    if len(excerpt) > 700:
        excerpt = sentences[0] if len(sentences[0]) <= 700 else ''
    return {'kind':'official_excerpt','language':'fr','scope':'country','text':excerpt,'topics':list(dict.fromkeys(tags))[:3]}


def french(item, form, refresh=False):
    key, name = item
    target = CACHE / f'fr-{key}.json'
    if target.exists() and not refresh:
        cached = json.loads(target.read_text())
        if cached.get('status') == 'ok':
            return cached
    try:
        payload = urlencode({**form,'select_pays':key}).encode()
        try:
            build_opener(NoRedirect).open(Request(INDEX, data=payload), timeout=25)
            raise ValueError('Country selector did not return a destination')
        except HTTPError as e:
            if e.code not in (301,302,303):
                raise
            destination = e.headers['Location']
        parsed = urlparse(destination)
        if parsed.hostname != 'www.diplomatie.gouv.fr' or '/information-par-pays/' not in parsed.path:
            raise ValueError('Unexpected country selector destination')
        slug = parsed.path.split('/information-par-pays/')[1].split('/')[0]
        url = BASE + '/fr/information-par-pays/' + slug + '/conseils-aux-voyageurs-securite'
        raw, final = fetch(url)
        soup = BeautifulSoup(raw, 'html.parser')
        article = soup.select_one('article.node--type-fiche-pays-article-cav')
        if not article or not any(h.get_text(' ',strip=True)=='Sécurité' for h in article.select('h2')):
            raise ValueError('No security advice article at destination')
        flag = article.select_one('.diplomatie--pays--drapeau-taxo img')
        flag_code = Path(flag['src']).stem.upper() if flag else ''
        pc = pycountry.countries.get(alpha_2=flag_code)
        iso = pc.alpha_3 if pc else {'XK':'XKX'}.get(flag_code)
        date = soup.select_one('.diplomatie--hdp-date--changed')
        urls = sorted(set(urljoin(BASE,x.get('src',x.get('href',''))) for x in article.select('img[src],a[href]') if '/cav/' in x.get('src',x.get('href','')) and re.search(r'\.(?:jpg|png|jpeg)(?:\?|$)',x.get('src',x.get('href','')),re.I)))
        context = text_context(article)
        context['source_url'] = final
        result = {'status':'ok','provider':'france_diplomatie','id':key,'slug':slug,'name':name,'iso3':iso,'flag_code':flag_code,'url':final,'checked_at':datetime.now(timezone.utc).isoformat(),'updated_label':date.get_text(' ',strip=True).replace('Date de mise à jour le :','').strip() if date else None,'page_sha256':hashlib.sha256(raw).hexdigest(),'map_urls':urls,'context':context}
        CACHE.mkdir(parents=True,exist_ok=True)
        (CACHE/f'fr-{key}.html').write_bytes(raw)
    except Exception as e:
        previous = json.loads(target.read_text()) if target.exists() else {}
        result = {**previous, 'refresh_error':str(e)} if previous.get('status')=='ok' else {'status':'error','provider':'france_diplomatie','id':key,'name':name,'error':str(e)}
    write(target,result)
    return result


def get_french(refresh=False):
    raw,_ = fetch(INDEX)
    soup = BeautifulSoup(raw,'html.parser')
    form = soup.select_one('form.fd-cav-select-pays-form')
    fields = {n['name']:n.get('value','') for n in form.select('input[name]')}
    items = [(o['value'],o.get_text(' ',strip=True)) for o in form.select('option[value]') if o['value']]
    region_urls = [urljoin(BASE,i['src']) for i in soup.select('img[src]') if '/cav/_carte' in i['src']]
    write(ROOT/'private/world/region-sources.json',region_urls)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(french,item,fields,refresh) for item in items]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
            if len(results)%20==0:print(f'French advice: {len(results)}/{len(items)} processed',flush=True)
    results.sort(key=lambda x:x['name'])
    write(ROOT/'private/world/french-sources.json',results)
    print('French advice:',sum(r['status']=='ok' for r in results),'ok;',sum(r['status']!='ok' for r in results),'errors',flush=True)
    return results


def uk(slug, refresh=False):
    target=CACHE/f'uk-{slug}.json'
    if target.exists() and not refresh:return json.loads(target.read_text())
    url='https://www.gov.uk/api/content/foreign-travel-advice/'+slug
    raw,_=fetch(url)
    data=json.loads(raw);detail=data['details']
    parts=detail.get('parts',[])
    safety=next((p for p in parts if p['slug']=='safety-and-security'),parts[0] if parts else {})
    soup=BeautifulSoup(safety.get('body',''),'html.parser')
    topics=[h.get_text(' ',strip=True) for h in soup.select('h2') if not re.search('UK Counter Terrorism|Staying safe',h.get_text())][:3]
    ps=[p.get_text(' ',strip=True) for p in soup.select('p') if len(p.get_text())>60 and not re.search('globally|global threat|UK Counter',p.get_text(),re.I)]
    sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',ps[0]) if ps else []
    result={'status':'ok','provider':'uk_fcdo','slug':slug,'name':data['title'].replace(' travel advice',''),'url':'https://www.gov.uk'+data['base_path'],'checked_at':datetime.now(timezone.utc).isoformat(),'updated_label':data['public_updated_at'][:10],'page_sha256':hashlib.sha256(raw).hexdigest(),'alert_status':detail.get('alert_status',[]),'context':{'kind':'official_excerpt','scope':'country','language':'en','text':' '.join(sentences[:2])[:700],'topics':topics,'source_url':'https://www.gov.uk'+data['base_path']+'/safety-and-security'}}
    result['advice_sha256']=hashlib.sha256(json.dumps({'parts':parts,'alerts':detail.get('alert_status',[])},sort_keys=True).encode()).hexdigest()
    write(target,result)
    (CACHE/f'uk-{slug}-api.json').write_bytes(raw)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');args=p.parse_args()
    get_french(args.refresh)

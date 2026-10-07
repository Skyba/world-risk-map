import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def store(value, scope):
    payload = encoded(value)
    digest = hashlib.sha256(payload).hexdigest()
    path = ROOT / ('private/objects' if scope == 'private' else 'data/objects') / (digest + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == payload
    else:
        path.write_bytes(payload)
    return {'sha256': digest, 'scope': scope, 'bytes': len(payload)}


def read_object(ref):
    if not re.fullmatch('[0-9a-f]{64}', ref['sha256']) or ref['scope'] not in ('private', 'public'):
        raise ValueError('Invalid object reference')
    path = ROOT / ('private/objects' if ref['scope'] == 'private' else 'data/objects') / (ref['sha256'] + '.json')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != ref['sha256']:
        raise ValueError('Object checksum mismatch: ' + path.name)
    return json.loads(payload)


def decode(ref):
    import topojson
    value = read_object(ref)
    if value['type'] == 'FeatureCollection':
        return value
    return json.loads(topojson.Topology(value).to_geojson(decimals=5))


def topology(fc):
    import topojson
    from shapely.geometry import shape
    t = topojson.Topology(fc, prequantize=100000000)
    result = t.to_dict()
    roundtrip = json.loads(t.to_geojson())
    if len(roundtrip['features']) != len(fc['features']):
        raise ValueError('Topology changed the feature count')
    for before, after in zip(fc['features'], roundtrip['features']):
        a, b = shape(before['geometry']), shape(after['geometry'])
        if not b.is_valid or a.hausdorff_distance(b) > .00001:
            raise ValueError('Topology geometry validation failed')
        if before['properties'] != after['properties']:
            raise ValueError('Topology changed feature attributes')
    return result


def collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def snapshot(input_dir, snapshot_date):
    date.fromisoformat(snapshot_date)
    source = load(input_dir / 'catalogue.json')
    result = {'schema_version': 1, 'snapshot_date': snapshot_date, 'cadence': 'manual_monthly', 'provider': 'France Diplomatie', 'countries': source['countries'], 'common': {}}
    for key in ('land', 'cities'):
        value = load(input_dir / (key + '.geojson'))
        result['common'][key] = store(topology(value) if key == 'land' else value, 'public')
    for slug, country in result['countries'].items():
        country['geometry'] = {}
        for lod in ('overview', 'detail'):
            path = input_dir / f'{slug}-{lod}.geojson'
            if not path.exists():
                continue
            scope = 'public' if country['rights']['status'] == 'cleared' and country['review']['status'] == 'approved' else 'private'
            country['geometry'][lod] = store(topology(load(path)), scope)
        extra = input_dir / f'{slug}-exceptions.geojson'
        if extra.exists():
            scope = 'public' if country['rights']['status'] == 'cleared' and country['review']['status'] == 'approved' else 'private'
            country['exceptions'] = store(load(extra), scope)
    result['display_metrics'] = source['display_metrics']
    path = ROOT / 'data/snapshots' / (snapshot_date + '.json')
    if path.exists() and encoded(load(path)) != encoded(result):
        raise ValueError('Snapshot is immutable; choose a new snapshot date instead of replacing history')
    write(path, result)
    write(ROOT / 'data/current.json', {'snapshot': snapshot_date})
    return result


def current(snapshot_date=None):
    snapshot_date = snapshot_date or load(ROOT / 'data/current.json')['snapshot']
    date.fromisoformat(snapshot_date)
    return load(ROOT / 'data/snapshots' / (snapshot_date + '.json'))


def public_blockers(s):
    blockers = []
    for slug, country in s['countries'].items():
        if country['display'].get('source_only'):
            continue
        if country['review']['status'] != 'approved':
            blockers.append(slug + ': geometry review pending')
        if country['rights']['status'] != 'cleared':
            blockers.append(slug + ': map reuse rights unresolved')
        for ref in list(country['geometry'].values()) + ([country['exceptions']] if country.get('exceptions') else []):
            if ref['scope'] != 'public':
                blockers.append(slug + ': candidate data is private')
    return list(dict.fromkeys(blockers))


def build(s, preview):
    if not preview:
        blockers = public_blockers(s)
        if blockers:
            raise ValueError('Public build withheld:\n' + '\n'.join(blockers))
    zones = {'overview': [], 'detail': []}
    cities = decode(s['common']['cities'])
    overlays, metrics = {}, {}
    target = ROOT / ('preview' if preview else 'dist')
    target.mkdir(exist_ok=True)
    for slug, country in s['countries'].items():
        for lod, ref in country['geometry'].items():
            zones[lod].extend(decode(ref)['features'])
        if country.get('exceptions'):
            cities['features'].extend(decode(country['exceptions'])['features'])
        metrics[slug] = dict(country['display'])
        metrics[slug]['retrieved_at'] = country['source']['retrieved_at']
        overlays[slug] = dict(country['image_overlay'])
        for key, suffix in [('url', '-aligned.jpg'), ('original_url', '.jpg'), ('comparison_url', '-comparison.png')]:
            media = ROOT / 'private/media' / (slug + suffix)
            if preview and media.exists():
                (target / 'media').mkdir(exist_ok=True)
                shutil.copyfile(media, target / 'media' / media.name)
                overlays[slug][key] = 'media/' + media.name
            else:
                overlays[slug][key] = country['source']['map_url']
    values = {'ZONES': collection(zones['overview']), 'DETAIL_ZONES': collection(zones['detail']), 'CITIES': cities, 'LAND': decode(s['common']['land']), 'OVERLAYS': overlays, 'METRICS': metrics, 'DISPLAY_METRICS': s['display_metrics'], 'SNAPSHOT_DATE': s['snapshot_date']}
    html = (ROOT / 'src/index.template.html').read_text()
    for key, value in values.items():
        html = html.replace('__' + key + '__', encoded(value).decode().replace('</', '<\\/'))
    if not preview:
        html = html.replace('Private sample', 'Monthly snapshot')
        # The public map links to source images; it does not redistribute them or rely on image CORS.
        html = html.replace('</style>', 'nav label,#source-panel{display:none!important}</style>')
        html = html.replace('Approximate, unapproved geometry.', 'Simplified advisory boundaries.')
        for slug, country in s['countries'].items():
            if country['display'].get('source_only'):
                html = html.replace(f'<button data-country="{slug}">', f'<button hidden disabled data-country="{slug}">')
    (target / 'index.html').write_text(html)
    return target / 'index.html'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src', 'href', 'data-src') and value:
                self.urls.append(value)


def fetch(url):
    if urlparse(url).hostname not in ('www.diplomatie.gouv.fr', 'diplomatie.gouv.fr'):
        raise ValueError('Unexpected source host: ' + url)
    req = Request(url, headers={'User-Agent': 'WorldRiskMap/0.1 (manual source review)'})
    with urlopen(req, timeout=30) as response:
        return response.read(), response.headers.get('Content-Type', '')


def check_sources(s, slugs):
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'snapshot': s['snapshot_date'], 'countries': {}, 'note': 'Read-only source check. Changed sources require extraction and human review. A page hash change may be unrelated boilerplate; it is not a risk-level change.'}
    for slug in slugs:
        country = s['countries'][slug]
        try:
            page, _ = fetch(country['source']['page_url'])
            parser = Links()
            parser.feed(page.decode('utf-8'))
            candidates = sorted(set(urljoin(country['source']['page_url'], u) for u in parser.urls if f'/cav/{slug}/' in u and re.search(r'\.(jpg|jpeg|png)(?:\?|$)', u, re.I)))
            if len(candidates) != 1:
                raise ValueError(f'Expected one current map; found {len(candidates)}. Inspect the page manually.')
            image, content_type = fetch(candidates[0])
            if not content_type.startswith('image/'):
                raise ValueError('Source map did not return an image')
            digest = hashlib.sha256(image).hexdigest()
            page_digest = hashlib.sha256(page).hexdigest()
            cache = ROOT / 'private/source-cache' / (digest + Path(urlparse(candidates[0]).path).suffix)
            cache.parent.mkdir(parents=True, exist_ok=True)
            if not cache.exists():
                cache.write_bytes(image)
            prior_page = country['source'].get('page_sha256')
            report['countries'][slug] = {'status': 'checked', 'map_url': candidates[0], 'map_sha256': digest, 'map_changed': digest != country['source']['map_sha256'], 'map_url_changed': candidates[0] != country['source']['map_url'], 'page_sha256': page_digest, 'page_changed': page_digest != prior_page if prior_page else None, 'text_review': 'baseline_needed' if not prior_page else 'check_diff' if page_digest != prior_page else 'unchanged_hash', 'cached_map': str(cache.relative_to(ROOT))}
        except Exception as exc:
            report['countries'][slug] = {'status': 'error', 'error': str(exc)}
    path = ROOT / 'private/updates' / (report['checked_at'][:10] + '.json')
    write(path, report)
    return report, path


def validate(s):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    count = 0
    for country in s['countries'].values():
        for ref in country['geometry'].values():
            fs = decode(ref)['features']
            if not all(shape(f['geometry']).is_valid for f in fs):
                raise ValueError('Invalid polygon')
            groups = [unary_union([shape(f['geometry']) for f in fs if f['properties']['risk'] == risk]) for risk in ('green', 'yellow', 'orange', 'red')]
            if sum(a.intersection(b).area for i, a in enumerate(groups) for b in groups[i+1:]) > 1e-10:
                raise ValueError('Risk polygons overlap after topology encoding')
            count += len(fs)
    return {'snapshot': s['snapshot_date'], 'polygon_features_validated': count, 'public_build_blockers': public_blockers(s)}


def main():
    parser = argparse.ArgumentParser(description='Local World Risk Map snapshots and source checks; never deploys or pushes.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot');p.add_argument('--input', type=Path, required=True);p.add_argument('--date', required=True)
    p = sub.add_parser('build');p.add_argument('--preview', action='store_true');p.add_argument('--snapshot')
    p = sub.add_parser('check-sources');p.add_argument('--country', action='append');p.add_argument('--snapshot')
    p = sub.add_parser('validate');p.add_argument('--snapshot')
    args = parser.parse_args()
    try:
        if args.command == 'snapshot':
            result = snapshot(args.input, args.date)
            print('Saved immutable snapshot:', result['snapshot_date'])
        elif args.command == 'build':
            print(build(current(args.snapshot), args.preview))
        elif args.command == 'validate':
            print(json.dumps(validate(current(args.snapshot)), indent=2))
        elif args.command == 'check-sources':
            s = current(args.snapshot)
            report, path = check_sources(s, args.country or list(s['countries']))
            print(path)
            print(json.dumps(report, indent=2))
            if any(c['status'] == 'error' for c in report['countries'].values()):
                return 1
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

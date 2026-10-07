import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import label, find_objects, distance_transform_edt, binary_dilation
from rasterio.features import shapes, rasterize
from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union, polygonize, transform
from shapely import coverage_is_valid, coverage_simplify, get_num_coordinates, set_precision
from pyproj import Transformer

root = Path(__file__).resolve().parent.parent
src = root / 'private/maps'
out = root / 'private/extraction'
cfg = json.loads((src / 'control-points.json').read_text())
raw = json.loads((out / 'experimental-zones.geojson').read_text())
places = json.loads((src / 'cities.geojson').read_text())['features']
lookup = {(f['properties']['adm0name'], f['properties']['name']): f for f in places}
country_names = {'gabon': 'Gabon', 'senegal': 'Senegal', 'tunisie': 'Tunisia', 'colombie': 'Colombia', 'indonesie': 'Indonesia', 'egypte': 'Egypt'}
iso_names = {cfg[n]['iso']: n for n in country_names}
risks = ['green', 'yellow', 'orange', 'red']
fwd = Transformer.from_crs(4326, 3857, always_xy=True).transform
inv = Transformer.from_crs(3857, 4326, always_xy=True).transform
area_transform = Transformer.from_crs(4326, 6933, always_xy=True).transform
report = {'purpose': 'Approximate display geometry; source extraction remains unchanged. Not approved advisory boundaries.', 'countries': {}, 'tolerances_source_pixels': {'overview': 3.5, 'detail': 2.5}, 'indonesia_tolerances_source_pixels': {'overview': 1.4, 'detail': .8}, 'method': 'Repair enclosed printing gaps <=320 pixels and <=8 pixels from classified colour; promote nine visually identified city callouts; simplify shared polygon coverage; clip to the same Natural Earth boundary as the basemap; round to five decimal places. Additional unclassified gaps are filled only inside the approximate civilian-restriction envelopes.'}
features = {'overview': [], 'detail': []}
exception_features = []

def collection(fs):
    return {'type': 'FeatureCollection', 'features': fs}

def polygonal(g):
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    parts = []
    for p in getattr(g, 'geoms', []):
        if p.geom_type == 'Polygon':
            parts.append(p)
        elif p.geom_type == 'MultiPolygon':
            parts.extend(p.geoms)
    return MultiPolygon(parts)

def compact_geometry(g):
    return mapping(set_precision(g, .00001))

# The same boundary geometry clips the advisory display and draws its basemap.
land = []
for f in json.loads((src / 'countries.geojson').read_text())['features']:
    p = f['properties']
    g = shape(f['geometry']).simplify(.025 if p['ADM0_A3'] in iso_names else .065, preserve_topology=True)
    land.append({'type': 'Feature', 'properties': {'name': p['NAME'], 'iso3': p['ADM0_A3']}, 'geometry': compact_geometry(g)})
country_shapes = {f['properties']['iso3']: shape(f['geometry']) for f in land}

# Only visually identified city callouts are promoted; small polygons are not assumed to be cities.
overrides = json.loads((src / 'display-overrides.json').read_text())
city_callouts = overrides['city_callouts']
egypt_closed = {int(k): v for k, v in overrides['egypt_closed'].items()}

for name, city_country in country_names.items():
    original = np.asarray(Image.open(src / f'{name}-classes.png'))
    mask = original.copy()
    cp = np.array(list(cfg[name]['gcps'].values()), float)
    ll = np.array([lookup[city_country, n]['geometry']['coordinates'] for n in cfg[name]['gcps']])
    target = np.column_stack(fwd(ll[:, 0], ll[:, 1]))
    co = np.linalg.lstsq(np.c_[cp, np.ones(len(cp))], target, rcond=None)[0]

    def pixel_geo(x, y, z=None):
        x = np.asarray(x) - .5
        y = np.asarray(y) - .5
        return inv(x * co[0, 0] + y * co[1, 0] + co[2, 0], x * co[0, 1] + y * co[1, 1] + co[2, 1])

    # Repair small enclosed printing gaps only, not coastal gaps or large missing regions.
    voids, _ = label(mask == 0)
    edge_ids = set(np.concatenate([voids[0], voids[-1], voids[:, 0], voids[:, -1]]))
    distance, nearest = distance_transform_edt(mask == 0, return_indices=True)
    repaired = 0
    for i, sl in enumerate(find_objects(voids), 1):
        if i in edge_ids:
            continue
        region = voids[sl] == i
        if region.sum() <= 320 and distance[sl][region].max() <= 8:
            view = mask[sl]
            view[region] = original[nearest[0][sl][region], nearest[1][sl][region]]
            repaired += int(region.sum())

    promoted = []
    if name == 'colombie':
        components, _ = label(mask == 2)
        for city, x, y, condition in city_callouts:
            component = int(components[y, x])
            region = components == component
            assert component and 10 < region.sum() < 250, (city, int(region.sum()))
            surround = binary_dilation(region, iterations=4) & ~region
            values = mask[surround]
            values = values[(values > 2)]
            replacement = int(np.bincount(values).argmax())
            mask[region] = replacement
            matched = lookup.get(('Colombia', city))
            coords = matched['geometry']['coordinates'] if matched else list(pixel_geo(x + .5, y + .5))
            point_id = f'COL-city-{len(exception_features)}'
            exception_features.append({'type': 'Feature', 'id': point_id, 'properties': {'id': point_id, 'country': name, 'name': city, 'risk': 'yellow', 'kind': 'city_exception', 'condition': condition, 'min_zoom': 4, 'priority': 0, 'position_source': 'Natural Earth' if matched else 'Approximate source-map position', 'source_pixel': [x, y], 'source_url': 'https://www.diplomatie.gouv.fr/fr/information-par-pays/colombie/conseils-aux-voyageurs-securite', 'map_date': '2026-05-27', 'approved_for_publication': False}, 'geometry': {'type': 'Point', 'coordinates': [round(float(v), 5) for v in coords]}})
            promoted.append(city)
        # This small pale symbol is a named tourist site, not an advisory city circle.
        artifact = int(components[595, 309])
        assert artifact and (components == artifact).sum() < 150
        mask[components == artifact] = 3

    hatch_repair_pixels = 0
    if name == 'egypte':
        for value, region in egypt_closed.items():
            footprint = rasterize([(Polygon(region['outline']).buffer(6), 1)], out_shape=mask.shape, dtype='uint8').astype(bool)
            eligible = footprint & ((mask == 0) | (mask == 4))
            hatch_repair_pixels += int(np.count_nonzero(eligible & (mask == 0)))
            mask[eligible] = value

    parts = [shape(g) for g, k in shapes(mask, mask=mask > 0)]
    partition, values = [], []
    for p in polygonize(unary_union([g.boundary for g in parts])):
        point = p.representative_point()
        k = int(mask[int(point.y), int(point.x)])
        if k:
            partition.append(p)
            values.append(k)
    assert coverage_is_valid(partition), name
    country = country_shapes[cfg[name]['iso']]
    stats = {'raw_vertices': sum(int(get_num_coordinates(shape(f['geometry']))) for f in raw['features'] if f['properties']['country'] == name), 'repaired_print_gap_pixels': repaired, 'promoted_city_exceptions': promoted, 'hatch_gap_pixels_recovered': hatch_repair_pixels, 'levels': {}}
    for lod, tolerance in report['tolerances_source_pixels'].items():
        if name == 'indonesie':
            tolerance = report['indonesia_tolerances_source_pixels'][lod]
        simplified = list(coverage_simplify(partition, tolerance, simplify_boundary=True))
        assert coverage_is_valid(simplified), (name, lod)
        roundtrip = rasterize(list(zip(simplified, values)), out_shape=mask.shape, dtype='uint8')
        fs, before_clip = [], []
        for i, (p, k) in enumerate(zip(simplified, values)):
            geo = transform(pixel_geo, p)
            before_clip.append(geo)
            clipped = polygonal(geo.intersection(country))
            if clipped.is_empty:
                continue
            clipped = set_precision(clipped, .00001)
            assert clipped.is_valid
            zone_id = f'{cfg[name]["iso"]}-{i}'
            props = {'country': name, 'iso3': cfg[name]['iso'], 'risk': risks[min(k, 4) - 1], 'zone_id': zone_id}
            if k > 4:
                props.update({'restriction': 'closed_to_civilians', 'restriction_name': egypt_closed[k]['name'], 'restriction_trace': 'Approximate manual source-image outline; unapproved'})
            fs.append({'type': 'Feature', 'id': zone_id, 'properties': props, 'geometry': mapping(clipped)})
        gs = [shape(f['geometry']) for f in fs]
        groups = [transform(area_transform, unary_union([shape(f['geometry']) for f in fs if f['properties']['risk'] == risk])) for risk in risks]
        overlap = sum(a.intersection(b).area for i, a in enumerate(groups) for b in groups[i + 1:]) / 1e6
        assert overlap < .000001, (name, lod, overlap)
        outside = unary_union(gs).difference(country.buffer(.00002)).area
        assert outside < 1e-9, (name, outside)
        changed = np.count_nonzero(roundtrip != mask)
        stats['levels'][lod] = {'tolerance_source_pixels': tolerance, 'features': len(fs), 'vertices': sum(int(get_num_coordinates(g)) for g in gs), 'inter_risk_overlap_km2': round(overlap, 9), 'valid_geometry': all(g.is_valid for g in gs), 'simplification_changed_classified_pixels_percent': round(100 * changed / max(1, np.count_nonzero(mask)), 3), 'trimmed_outside_basemap_km2': round(transform(area_transform, unary_union(before_clip).difference(country)).area / 1e6, 2)}
        features[lod].extend(fs)
    report['countries'][name] = stats

city_features = []
exception_names = {f['properties']['name'] for f in exception_features}
for f in sorted(places, key=lambda f: -f['properties']['pop_max']):
    p = f['properties']
    iso = p['adm0_a3']
    if iso not in iso_names and not p['adm0cap']:
        continue
    if iso == 'COL' and p['name'] in exception_names:
        continue
    if any(c['properties']['name'] == p['name'] and c['properties']['country_name'] == p['adm0name'] and sum((a-b)**2 for a,b in zip(c['geometry']['coordinates'], f['geometry']['coordinates'])) < .01 for c in city_features):
        continue
    threshold = 2 if p['adm0cap'] else 4 if p['pop_max'] >= 500000 else 5 if p['pop_max'] >= 100000 else 6
    city_features.append({'type': 'Feature', 'properties': {'id': str(p['ne_id']), 'name': 'Bogotá' if p['name'] == 'Bogota' else p['name'], 'country': iso_names.get(iso, ''), 'country_name': p['adm0name'], 'min_zoom': threshold, 'priority': threshold * 10000000 - p['pop_max'], 'kind': 'city', 'capital': bool(p['adm0cap'])}, 'geometry': {'type': 'Point', 'coordinates': [round(v, 5) for v in f['geometry']['coordinates']]}})

report['city_layer'] = {'ordinary_cities': len(city_features), 'city_exceptions': len(exception_features), 'unresolved_positions': [f['properties']['name'] for f in exception_features if f['properties']['position_source'] != 'Natural Earth'], 'semantics': 'Neutral city markers are named places, not advisory classifications; capitals use squares. Coloured city symbols have no implied radius or route corridor. Exception extraction is partial; connected yellow areas remain polygons.'}
report['city_layer']['capital_squares'] = sum(f['properties']['capital'] for f in city_features)
closed_features = [f for f in features['detail'] if f['properties'].get('restriction') == 'closed_to_civilians']
report['closed_to_civilians'] = {'regions': sorted({f['properties']['restriction_name'] for f in closed_features}), 'features': len(closed_features), 'source': cfg['egypte']['image_url'], 'method': 'Approximate manual hatch envelopes in source pixel coordinates, extended six pixels to join stripe ends. Only red and unclassified hatch gaps are relabelled; existing yellow/orange pixels are preserved. Risk and restriction share the same partition and zoom geometry.', 'approved_for_publication': False}
(out / 'display-restrictions.geojson').write_text(json.dumps(collection(closed_features), separators=(',', ':')))
for lod, fs in features.items():
    target = out / f'display-zones-{lod}.geojson'
    target.write_text(json.dumps(collection(fs), separators=(',', ':')))
    report[f'{lod}_bytes'] = target.stat().st_size
(out / 'display-cities.geojson').write_text(json.dumps(collection(city_features + exception_features), separators=(',', ':')))
(src / 'display-land.json').write_text(json.dumps(collection(land), separators=(',', ':')))
restrictions = json.loads((out / 'restrictions-review.json').read_text())
for restriction in restrictions:
    if restriction['country'] == 'egypte' and restriction['kind'] == 'closed_to_civilians':
        restriction.update({'geometry_status': 'two_approximate_candidate_regions', 'geometry_file': 'display-restrictions.geojson', 'remaining_review': 'Manual envelope positions and disputed southeastern boundary require geographic review.', 'approved_for_publication': False})
    if restriction['country'] == 'colombie' and restriction['kind'] == 'city_access_exception':
        restriction.update({'geometry_status': 'nine_candidate_points_with_access_notes', 'point_file': 'display-cities.geojson', 'remaining_review': 'Two map-derived city positions; connected yellow areas; completeness and exact city extents. Point symbols do not imply safe access routes.', 'approved_for_publication': False})
(out / 'restrictions-review.json').write_text(json.dumps(restrictions, indent=2))
report['raw_zone_bytes'] = (out / 'experimental-zones.geojson').stat().st_size
report['raw_viewer_bytes'] = 10147397
(out / 'display-test-results.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

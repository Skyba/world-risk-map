import copy
import json
from pathlib import Path
from shapely.geometry import shape, box, mapping

ROOT=Path(__file__).resolve().parent.parent


def countries():
    features=json.loads((ROOT/'private/maps/countries.geojson').read_text())['features']
    france=next(f for f in features if f['properties']['ADM0_A3']=='FRA')
    remaining=shape(france['geometry'])
    territories=[('GUF','French Guiana',[-55,2,-50,6]),('GLP','Guadeloupe',[-62,15.8,-60,17]),('MTQ','Martinique',[-62,14,-60,15.8]),('REU','Réunion',[54,-22,56,-20]),('MYT','Mayotte',[44,-14,46,-11])]
    for iso,name,bounds in territories:
        part=remaining.intersection(box(*bounds))
        if part.is_empty:continue
        row=copy.deepcopy(france)
        row['properties'].update({'ADM0_A3':iso,'ISO_A3':iso,'ISO_A3_EH':iso,'NAME':name,'NAME_EN':name,'NAME_LONG':name})
        row['geometry']=mapping(part)
        features.append(row)
        remaining=remaining.difference(part)
    france['geometry']=mapping(remaining)
    return features

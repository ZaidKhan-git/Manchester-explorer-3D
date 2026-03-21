import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON = os.path.join(DATA_DIR, 'accommodations.geojson')

with open(GEOJSON, 'r', encoding='utf-8') as f:
    geo = json.load(f)

fixed = 0
for feat in geo['features']:
    props = feat['properties']
    name = props.get('name')
    if name == 'Bridgewater Heights':
        # Bridgewater Heights (Student Castle) is a 33-story tower (109m)
        props['height'] = 109.0
        props['building_levels'] = '33'
        print(f"Fixed height for {name} to 109m")
        fixed += 1

if fixed:
    with open(GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geo, f, ensure_ascii=False, indent=2)
    print("✅ accommodations.geojson updated.")

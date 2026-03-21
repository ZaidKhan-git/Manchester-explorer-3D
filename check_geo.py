import json
import os

with open('data/accommodations.geojson', 'r', encoding='utf-8') as f:
    d = json.load(f)
    print("Coordinates:")
    for f in d['features']:
        name = f['properties']['name']
        if 'bridgewater' in name.lower() or 'artisan' in name.lower():
            p = f['properties']
            print(f"{name}:")
            print(f"  geometry_source = {p.get('geometry_source')}")
            print(f"  osm_id = {p.get('osm_id')}")
            print(f"  lat, lng = {p.get('lat')}, {p.get('lng')}")
            print(f"  height = {p.get('height')}")

"""
fix_snapped_coords.py
=====================
Patches accommodations.geojson so that every snapped building's
props.lat / props.lng match the centroid of its snapped polygon.
This eliminates the visual offset where colored extrusions appear
shifted vs the grey default Mapbox buildings.

Run:  python fix_snapped_coords.py
Then: python build_db_data.py
"""
import json, os

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON    = os.path.join(DATA_DIR, 'accommodations.geojson')

with open(GEOJSON, 'r', encoding='utf-8') as f:
    geo = json.load(f)

fixed = 0
for feat in geo['features']:
    p = feat['properties']
    if p.get('geometry_source') != 'snapped':
        continue
    coords = feat['geometry']['coordinates'][0]
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    centroid_lat = sum(lats) / len(lats)
    centroid_lng = sum(lngs) / len(lngs)

    old_lat = float(p.get('lat', 0))
    old_lng = float(p.get('lng', 0))
    dlat = abs(centroid_lat - old_lat)
    dlng = abs(centroid_lng - old_lng)
    offset_m = ((dlat**2 + dlng**2)**0.5) * 111000

    if offset_m > 1.0:
        p['lat'] = round(centroid_lat, 6)
        p['lng'] = round(centroid_lng, 6)
        print(f"  Fixed {p['name'][:40]:40s}  offset was {offset_m:.1f}m")
        fixed += 1

with open(GEOJSON, 'w', encoding='utf-8') as f:
    json.dump(geo, f, ensure_ascii=False, indent=2)

print(f"\n✅ Fixed {fixed} buildings. Now run: python build_db_data.py")

"""
fix_specific.py
===============
Fixes "IconInc The Ainscow", "Canvas Manchester", "Uit Canvas Manchester",
and "Artisan Heights" which snapped to extremely wrong sized buildings.

Logic:
Finds OSM buildings near the original lat/lng coordinates and scores them based
on matching an expected area footprint (around 800-1500 sqm for these buildings),
ignoring massive malls and tiny sheds.
"""
import json, math, os
import urllib.request, urllib.parse

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON = os.path.join(DATA_DIR, 'accommodations.geojson')
RAW_DATA = os.path.join(DATA_DIR, 'Manchester All Data.json')

TARGET_BUILDINGS = [
    'IconInc The Ainscow',
    'Artisan Heights',
    'Canvas Manchester',
    'Uit Canvas Manchester'
]

# Provide a manual expected area for typical high-rise student accommodations
EXPECTED_AREA_SQM = 1200.0  

def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def polygon_area_sq_m(ring, center_lat):
    n = len(ring)
    if n < 4: return 0
    cos_lat = math.cos(math.radians(center_lat))
    area = 0
    for i in range(n - 1):
        x1 = ring[i][0] * cos_lat * 111320
        y1 = ring[i][1] * 111320
        x2 = ring[i+1][0] * cos_lat * 111320
        y2 = ring[i+1][1] * 111320
        area += x1 * y2 - x2 * y1
    return abs(area) / 2

def overpass_request(lat, lng, radius=80):
    query = f"""
    [out:json][timeout:20];
    (
      nwr["building"](around:{radius},{lat},{lng});
    );
    out geom;
    """
    data = urllib.parse.urlencode({'data': query}).encode()
    url = 'https://overpass-api.de/api/interpreter'
    try:
        req = urllib.request.Request(url, data=data, headers={'User-Agent': 'Manchester3DMap/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"Overpass error: {e}")
        return None

def find_best_proxy(lat, lng):
    result = overpass_request(lat, lng)
    if not result or not result.get('elements'):
        return None

    candidates = []
    for el in result['elements']:
        raw = []
        if el.get('type') == 'way' and el.get('geometry'):
            raw = [[g['lon'], g['lat']] for g in el['geometry']]
        elif el.get('type') == 'relation' and el.get('members'):
            for m in el['members']:
                if m.get('role') == 'outer' and m.get('geometry'):
                    raw = [[g['lon'], g['lat']] for g in m['geometry']]
                    break

        if not raw or raw[0] != raw[-1]:
            continue

        c_lng = sum(g[0] for g in raw) / len(raw)
        c_lat = sum(g[1] for g in raw) / len(raw)
        dist = haversine(lat, lng, c_lat, c_lng)
        area = polygon_area_sq_m(raw, c_lat)

        # Ignore tiny sheds and massive structures like arenas / malls
        if area < 300 or area > 5000:
            continue

        # Score based on how close the area is to EXPECTED_AREA_SQM
        # The user said "matches 80% of the dimensions", so area should ideally be near EXPECTED_AREA
        area_diff = abs(area - EXPECTED_AREA_SQM) / EXPECTED_AREA_SQM
        
        candidates.append({
            'osm_id': f"{el.get('type')}/{el['id']}",
            'geometry': {'type': 'Polygon', 'coordinates': [raw]},
            'centroid': [c_lng, c_lat],
            'distance_m': dist,
            'area_sq_m': area,
            'area_diff': area_diff,
            'tags': el.get('tags', {})
        })

    if not candidates:
        return None

    # Sort primarily by how close the area is to the expected dimension (we want it within 80% tolerance)
    # Then by distance
    candidates.sort(key=lambda x: (x['area_diff'], x['distance_m']))
    return candidates[0]

def main():
    # 1. Load original unadulterated coordinates for these from Manchester All Data.json
    with open(RAW_DATA, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    orig_coords = {}
    for h in raw.get('data', {}).get('houses', []):
        t = h.get('title', '').strip()
        if t in TARGET_BUILDINGS:
            orig_coords[t] = (float(h.get('lat', 0)), float(h.get('lng', 0)))

    # 2. Update accommodations.geojson
    with open(GEOJSON, 'r', encoding='utf-8') as f:
        geo = json.load(f)

    for feat in geo['features']:
        props = feat['properties']
        name = props.get('name')
        if name in TARGET_BUILDINGS:
            base_lat, base_lng = orig_coords.get(name, (0,0))
            if base_lat == 0:
                continue

            print(f"Fixing {name}...")
            print(f"  Original coordinates: {base_lat:.5f}, {base_lng:.5f}")
            match = find_best_proxy(base_lat, base_lng)

            if match:
                feat['geometry'] = match['geometry']
                props['lng'] = round(match['centroid'][0], 6)
                props['lat'] = round(match['centroid'][1], 6)
                props['osm_id'] = match['osm_id']
                props['geometry_source'] = 'snapped'
                print(f"  ✓ Found better proxy: Area={match['area_sq_m']:.1f} sqm, Dist={match['distance_m']:.1f}m, OSM ID={match['osm_id']}")
            else:
                print("  ✗ No suitable building footprint found between 300-5000sqm.")
                # We can generate a perfect synthetic polygon (e.g. 35x35m) so it behaves well
                # 35m is roughly 0.0003 degrees in coords
                d = 0.00015
                synthetic = [
                    [base_lng - d, base_lat - d],
                    [base_lng + d, base_lat - d],
                    [base_lng + d, base_lat + d],
                    [base_lng - d, base_lat + d],
                    [base_lng - d, base_lat - d]
                ]
                feat['geometry'] = {'type': 'Polygon', 'coordinates': [synthetic]}
                props['geometry_source'] = 'generated' # Keep it generated so we know
                props['lng'] = base_lng
                props['lat'] = base_lat
                print("  ✓ Created synthetic proxy building rectangle.")

    with open(GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geo, f, ensure_ascii=False, indent=2)

    print("\n✅ accommodations.geojson updated.")

if __name__ == '__main__':
    main()

"""
resnap_smart.py
===============
Smarter re-snapping approach for student accommodations.

Problem: The previous snap_to_buildings.py picked the NEAREST building to
the geocoded lat/lng, but that often turned out to be a shed, pub, or
random house — not the actual accommodation.

Strategy:
1. For each snapped building, query Overpass for buildings tagged as:
   dormitory, apartments, residential, university, college, hotel, hostel
   in order of specificity. Pick the closest match by semantic tag.
2. If no semantically relevant building is found, pick the LARGEST
   building polygon nearby (by area) — student accommodations are usually
   the biggest structures on their block.
3. Also filter candidates by minimum polygon area to skip sheds/garages.

Usage:  python resnap_smart.py
Then:   python build_db_data.py
"""
import json, math, time, os, sys
import urllib.request, urllib.parse, urllib.error

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON    = os.path.join(DATA_DIR, 'accommodations.geojson')

OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://lz4.overpass-api.de/api/interpreter',
    'https://z.overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]

# Preferred building types (in priority order)
PREFERRED_TAGS = [
    'dormitory', 'apartments', 'residential', 
    'hotel', 'hostel', 'university', 'college',
]

SEARCH_RADIUS  = 100   # metres
MIN_AREA_SQ_M  = 100   # reject buildings smaller than 100 m²
POLITE_DELAY   = 3.0

# ── Utility ───────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def ring_centroid(coord_ring):
    lngs = [c[0] for c in coord_ring]
    lats = [c[1] for c in coord_ring]
    return sum(lats)/len(lats), sum(lngs)/len(lngs)

def close_ring(coords):
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords

def polygon_area_sq_m(ring, center_lat):
    """Approximate polygon area in square metres using the Shoelace formula."""
    n = len(ring)
    if n < 4:
        return 0
    # Convert lng/lat to metres relative to center
    cos_lat = math.cos(math.radians(center_lat))
    area = 0
    for i in range(n - 1):
        x1 = ring[i][0] * cos_lat * 111320
        y1 = ring[i][1] * 111320
        x2 = ring[i+1][0] * cos_lat * 111320
        y2 = ring[i+1][1] * 111320
        area += x1 * y2 - x2 * y1
    return abs(area) / 2

def calc_height(tags, fallback=30.0):
    h = tags.get('height', '')
    if h:
        try:
            return float(str(h).replace('m','').strip())
        except ValueError:
            pass
    lvl = tags.get('building:levels', '')
    if lvl:
        try:
            return max(8.0, float(lvl) * 3.5)
        except ValueError:
            pass
    return fallback

# ── Overpass ──────────────────────────────────────────────────────────────────

def overpass_request(query):
    data = urllib.parse.urlencode({'data': query}).encode()
    for attempt in range(3):
        for url in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=data,
                          headers={'Content-Type': 'application/x-www-form-urlencoded',
                                   'User-Agent': 'Manchester3DMapBuilder/1.0'})
                with urllib.request.urlopen(req, timeout=45) as r:
                    return json.loads(r.read().decode('utf-8'))
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    time.sleep(8)
                else:
                    pass
            except Exception:
                pass
        time.sleep(5)
    return None

def find_best_building(lat, lng, name=''):
    """
    Find the best building match near (lat, lng).
    Priority: semantic match > largest area > nearest.
    """
    query = f"""
[out:json][timeout:40];
(
  nwr["building"](around:{SEARCH_RADIUS},{lat},{lng});
);
out geom;
"""
    result = overpass_request(query)
    if not result or not result.get('elements'):
        return None

    candidates = []
    for el in result['elements']:
        raw = []
        if el.get('type') == 'way' and el.get('geometry'):
            raw = [[g['lon'], g['lat']] for g in el['geometry']]
        elif el.get('type') == 'relation' and el.get('members'):
            # Use the first outer way
            for m in el['members']:
                if m.get('role') == 'outer' and m.get('geometry'):
                    raw = [[g['lon'], g['lat']] for g in m['geometry']]
                    break

        if not raw:
            continue

        ring = close_ring(raw)
        if len(ring) < 4:
            continue

        c_lat, c_lng = ring_centroid(ring)
        dist = haversine(lat, lng, c_lat, c_lng)
        area = polygon_area_sq_m(ring, c_lat)

        # Skip tiny buildings (sheds, garages, phone booths)
        if area < MIN_AREA_SQ_M:
            continue

        tags = el.get('tags', {})
        building_type = tags.get('building', 'yes').lower()

        # Score: semantic match
        semantic_score = 0
        for i, pref in enumerate(PREFERRED_TAGS):
            if building_type == pref:
                semantic_score = len(PREFERRED_TAGS) - i
                break
        
        # Check if building name contains accommodation name keywords
        osm_name = (tags.get('name', '') or '').lower()
        name_lower = name.lower() if name else ''
        name_match = 0
        if osm_name and name_lower:
            # Check for word overlap
            name_words = set(name_lower.split())
            osm_words = set(osm_name.split())
            common = name_words & osm_words - {'the', 'a', 'student', 'accommodation', 'manchester'}
            if common:
                name_match = len(common) * 10

        candidates.append({
            'osm_id':       f"{el.get('type')}/{el['id']}",
            'geometry':     {'type': 'Polygon', 'coordinates': [ring]},
            'centroid':     [c_lng, c_lat],
            'distance_m':   round(dist, 1),
            'area_sq_m':    round(area, 1),
            'tags':         tags,
            'levels':       tags.get('building:levels', ''),
            'height':       tags.get('height', ''),
            'building_type': building_type,
            'score':        name_match * 100 + semantic_score * 1000 + area,  # name match > semantic > area
        })

    if not candidates:
        return None

    # Sort by score (highest wins) — name match > semantic > largest area
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    best = candidates[0]
    return best


def main():
    print('\n🔧  resnap_smart.py — Smart re-snapping of accommodations\n')

    with open(GEOJSON, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    features = geojson['features']
    fixed = 0
    skipped_osm = 0
    not_found = 0

    for i, feat in enumerate(features):
        props = feat['properties']
        name  = props.get('name', 'Unknown')
        lat   = float(props.get('lat', 0))
        lng   = float(props.get('lng', 0))
        src   = props.get('geometry_source', 'generated')

        print(f"[{i+1:02d}/{len(features)}] {name}")

        if src == 'osm':
            print(f"        ✓  already OSM, skipping.")
            skipped_osm += 1
            continue

        if lat == 0 or lng == 0:
            print(f"        ✗  no coordinates, skipping.")
            not_found += 1
            continue

        print(f"        ⟳  searching for best match near ({lat:.5f}, {lng:.5f})…")
        match = find_best_building(lat, lng, name)
        time.sleep(POLITE_DELAY)

        if match:
            # Apply the snap
            feat['geometry'] = match['geometry']
            
            tags   = match.get('tags', {})
            height = calc_height(tags, fallback=float(props.get('height', 30)))
            
            centroid = match.get('centroid')
            if centroid:
                props['lng'] = round(centroid[0], 6)
                props['lat'] = round(centroid[1], 6)
            
            props['osm_id']          = match['osm_id']
            props['geometry_source'] = 'snapped'
            props['height']          = height
            props['base_height']     = 0
            props['building_levels'] = match.get('levels', '')

            print(f"        ✓  → {match['osm_id']}  type={match['building_type']}  area={match['area_sq_m']}m²  dist={match['distance_m']}m  score={match['score']:.0f}")
            fixed += 1
        else:
            print(f"        ✗  no suitable building found within {SEARCH_RADIUS}m")
            not_found += 1

    # Write
    with open(GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"""
{'='*60}
  SUMMARY
{'='*60}
  Already had real OSM footprint : {skipped_osm}
  Re-snapped (smart)             : {fixed}
  No building found              : {not_found}
  TOTAL                          : {len(features)}
{'='*60}

✅ accommodations.geojson updated.
👉 Now run:  python build_db_data.py
""")

if __name__ == '__main__':
    main()

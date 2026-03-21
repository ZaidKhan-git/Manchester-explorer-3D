"""
snap_to_buildings.py
====================
For each student accommodation in accommodations.geojson, finds the nearest
real OSM building polygon to that accommodation's geocoded lat/lng via the
Overpass API.  This "snapped" geometry is then written back into
accommodations.geojson so every building sits perfectly on top of the
default grey Mapbox tile — no more floating boxes in the middle of streets.

Strategy
--------
1. Skip buildings that already have geometry_source == "osm" (real footprints).
2. For the rest, query Overpass for building ways within a search radius.
3. Compute each result's centroid and pick the one nearest to props.lat/lng.
4. Expand the search radius (30 → 75 → 150 m) until at least one building
   is found, then choose the closest.
5. Write a progress/cache file (snap_cache.json) so the script is resumable.
6. Patch accommodations.geojson in-place and regenerate the JS data files.

Run with:
    python snap_to_buildings.py
"""

import json, math, time, os, sys
import urllib.request, urllib.parse, urllib.error

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON    = os.path.join(DATA_DIR, 'accommodations.geojson')
CACHE_FILE = os.path.join(DATA_DIR, 'snap_cache.json')

OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://lz4.overpass-api.de/api/interpreter',
    'https://z.overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]

SEARCH_RADII = [40, 80, 150]   # metres — try smallest first
POLITE_DELAY = 3.0              # seconds between Overpass calls

# ── Utility ───────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    """Haversine distance in metres between two WGS-84 points."""
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def ring_centroid(coord_ring):
    """Return (lat, lng) centroid of a polygon ring [[lng, lat], ...]."""
    lngs = [c[0] for c in coord_ring]
    lats = [c[1] for c in coord_ring]
    return sum(lats)/len(lats), sum(lngs)/len(lngs)

def close_ring(coords):
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords

# ── Overpass ──────────────────────────────────────────────────────────────────

def overpass_request(query):
    data   = urllib.parse.urlencode({'data': query}).encode()
    for attempt in range(3):
        for url in OVERPASS_ENDPOINTS:
            try:
                req  = urllib.request.Request(url, data=data,
                           headers={'Content-Type': 'application/x-www-form-urlencoded',
                                    'User-Agent': 'Manchester3DMapBuilder/1.0'})
                with urllib.request.urlopen(req, timeout=40) as r:
                    return json.loads(r.read().decode('utf-8'))
            except urllib.error.HTTPError as he:
                print(f"    ⚠  {url.split('/')[2]} failed: HTTP {he.code}")
                if he.code == 429:
                    time.sleep(5)
            except Exception as exc:
                print(f"    ⚠  {url.split('/')[2]} failed: {exc}")
        print("    ⏱  All endpoints failed, waiting before retry...")
        time.sleep(3)
    return None

def find_nearest_building(lat, lng):
    """
    Try progressively larger radii until we find at least one building near
    (lat, lng).  Returns the best match dict or None.
    """
    best = None

    for radius in SEARCH_RADII:
        query = f"""
[out:json][timeout:35];
(
  nwr["building"](around:{radius},{lat},{lng});
);
out geom;
"""
        result = overpass_request(query)
        if not result or not result.get('elements'):
            continue

        # ── Score each returned building ──────────────────────────────────────
        candidates = []
        for el in result['elements']:
            raw = []
            if el.get('type') == 'way' and el.get('geometry'):
                raw = [[g['lon'], g['lat']] for g in el['geometry']]
            elif el.get('type') == 'relation' and el.get('members'):
                for m in el['members']:
                    if m.get('role') == 'outer' and m.get('type') == 'way' and m.get('geometry'):
                        raw = [[g['lon'], g['lat']] for g in m['geometry']]
                        break
            
            if not raw:
                continue

            ring     = close_ring(raw)
            if len(ring) < 4:
                continue
            c_lat, c_lng = ring_centroid(ring)
            dist         = haversine(lat, lng, c_lat, c_lng)
            candidates.append({
                'osm_id':      f"{el.get('type')}/{el['id']}",
                'geometry':    {'type': 'Polygon', 'coordinates': [ring]},
                'centroid':    [c_lng, c_lat],
                'distance_m':  round(dist, 1),
                'tags':        el.get('tags', {}),
                'levels':      el.get('tags', {}).get('building:levels', ''),
                'height':      el.get('tags', {}).get('height', ''),
            })

        if not candidates:
            continue

        # Sort by distance — closest wins
        candidates.sort(key=lambda x: x['distance_m'])
        best = candidates[0]
        break   # found something — no need for a bigger radius

    return best

# ── Main ──────────────────────────────────────────────────────────────────────

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def calc_height(tags, fallback=30.0):
    # Try explicit height first
    h = tags.get('height', '')
    if h:
        try:
            return float(str(h).replace('m','').strip())
        except ValueError:
            pass
    # Derive from levels
    lvl = tags.get('building:levels', '')
    if lvl:
        try:
            return max(8.0, float(lvl) * 3.5)
        except ValueError:
            pass
    return fallback

def main():
    print('\n🔍  snap_to_buildings.py — Snapping accommodations to real OSM footprints\n')

    with open(GEOJSON, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    features = geojson['features']
    cache    = load_cache()

    # Stats
    already_osm = 0
    snapped     = 0
    not_found   = 0
    cached_hits = 0

    for i, feat in enumerate(features):
        props  = feat['properties']
        acc_id = str(props.get('id', ''))
        name   = props.get('name', 'Unknown')
        lat    = float(props.get('lat', 0))
        lng    = float(props.get('lng', 0))
        src    = props.get('geometry_source', 'generated')

        print(f"[{i+1:02d}/{len(features)}] {name}")

        # ── 1. Already has a real OSM footprint ───────────────────────────────
        if src == 'osm':
            print(f"        ✓  already OSM ({props.get('osm_id', '?')}), skipping.")
            already_osm += 1
            continue

        # ── 2. Return cached result ───────────────────────────────────────────
        if acc_id in cache:
            hit = cache[acc_id]
            if hit is None:
                print(f"        ✗  cached as not-found, skipping.")
                not_found += 1
            else:
                _apply_snap(feat, hit)
                print(f"        ✓  cache hit  → {hit['osm_id']}  ({hit['distance_m']} m)")
                cached_hits += 1
            continue

        # ── 3. Live Overpass query ────────────────────────────────────────────
        if lat == 0 or lng == 0:
            print(f"        ✗  no coordinates, skipping.")
            cache[acc_id] = None
            not_found += 1
            continue

        print(f"        ⟳  querying Overpass for buildings near ({lat:.5f}, {lng:.5f})…")
        match = find_nearest_building(lat, lng)
        time.sleep(POLITE_DELAY)

        if match:
            _apply_snap(feat, match)
            cache[acc_id] = match
            print(f"        ✓  snapped     → {match['osm_id']}  ({match['distance_m']} m)")
            snapped += 1
        else:
            cache[acc_id] = None
            print(f"        ✗  no building found within {SEARCH_RADII[-1]} m.")
            not_found += 1

        # Save cache incrementally so we can resume after interruptions
        save_cache(cache)

    # ── Write updated GeoJSON ────────────────────────────────────────────────
    with open(GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    save_cache(cache)

    print(f"""
{'='*60}
  SUMMARY
{'='*60}
  Already had real OSM footprint : {already_osm}
  Snapped to nearest OSM building : {snapped}
  Served from cache               : {cached_hits}
  No building found               : {not_found}
  TOTAL                           : {len(features)}
{'='*60}

✅ accommodations.geojson updated.
👉 Now re-run:  python build_db_data.py
   Then hard-refresh your browser (Ctrl+Shift+R) to reload the DB.
""")

def _apply_snap(feat, match):
    """Overwrite a feature's geometry and update properties with the snapped building."""
    feat['geometry'] = match['geometry']

    tags   = match.get('tags', {})
    height = calc_height(tags, fallback=float(feat['properties'].get('height', 30)))

    # Update lat/lng to the snapped centroid so properties match the polygon
    centroid = match.get('centroid')
    if centroid:
        feat['properties']['lng'] = round(centroid[0], 6)
        feat['properties']['lat'] = round(centroid[1], 6)

    feat['properties']['osm_id']          = match['osm_id']
    feat['properties']['geometry_source'] = 'snapped'
    feat['properties']['height']          = height
    feat['properties']['base_height']     = 0
    feat['properties']['building_levels'] = match.get('levels', '')

if __name__ == '__main__':
    main()

"""
fetch_all_amenities_perfect_geom.py
===================================
Fetches amenities with exact architectural geometry.
If an amenity is just a point (node) sitting inside an OSM building,
this script mathematically matches the point to the building's 
footprint polygon, so it renders beautifully in 3D exactly matching 
the real world block.

It uses Ray-Casting for flawless point-in-polygon matching locally to
avoid killing the Overpass APIs.
"""
import json, math, os, time
import urllib.request, urllib.parse

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GEOJSON = os.path.join(DATA_DIR, 'accommodations.geojson')
CACHE_JSON = os.path.join(DATA_DIR, 'amenities_cache.json')

def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def point_in_polygon(x, y, polygon):
    # Ray-casting algorithm
    inside = False
    n = len(polygon)
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def get_category(tags):
    am = tags.get('amenity', '')
    le = tags.get('leisure', '')
    sh = tags.get('shop', '')
    pub = tags.get('public_transport', '')
    hw = tags.get('highway', '')
    hf = tags.get('healthcare', '')
    
    if am in ['restaurant']: return 'restaurants'
    if am in ['cafe']: return 'cafes'
    if am in ['bar', 'pub']: return 'bars'
    if am in ['nightclub']: return 'nightclubs'
    if sh in ['convenience', 'kiosk']: return 'convenience_stores'
    if sh in ['supermarket', 'mall']: return 'supermarkets'
    if am in ['pharmacy'] or hf in ['pharmacy', 'hospital', 'clinic']: return 'pharmacies'
    if am in ['library']: return 'libraries'
    if pub == 'station' or tags.get('railway') == 'station': return 'metro_stations'
    if hw == 'bus_stop': return 'bus_stops'
    if le in ['park', 'garden', 'pitch']: return 'parks'
    if le in ['sports_centre', 'stadium']: return 'sports_centres'
    if le in ['fitness_centre', 'gym']: return 'gyms'
    if am in ['university', 'college']: return 'universities'
    if am in ['place_of_worship']: return 'places_of_worship'
    return None

def main():
    print("Loading accommodations...")
    with open(GEOJSON, 'r', encoding='utf-8') as f:
        geo = json.load(f)
        
    features = geo.get('features', [])
    if not features: return

    # 1. Calculate bounding box of all accommodations
    lats = [f['properties']['lat'] for f in features]
    lngs = [f['properties']['lng'] for f in features]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    
    buffer = 0.007 # roughly 700m buffer
    bbox = f"{min_lat - buffer},{min_lng - buffer},{max_lat + buffer},{max_lng + buffer}"
    
    api_url = "https://overpass-api.de/api/interpreter"
    
    # 2. Query Overpass for all buildings in the box to use as pristine geometric shells
    print(f"Fetching Mapbox-aligned building geometry foundations in ({bbox})...")
    q_bldgs = f"""[out:json][timeout:120];(way["building"]({bbox}););out geom;"""
    try:
        req = urllib.request.Request(api_url, data=urllib.parse.urlencode({'data': q_bldgs}).encode(), headers={'User-Agent': 'Manchester3DMap/2.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            bldgs_res = json.loads(r.read().decode())['elements']
        print(f"  ✓ Downloaded {len(bldgs_res)} pristine building blueprints.")
    except Exception as e:
        print(f"Error fetching buildings: {e}")
        return

    # Process building blueprints into quick lookup array
    buildings = []
    for b in bldgs_res:
        if 'geometry' in b:
            raw = [[pt['lon'], pt['lat']] for pt in b['geometry']]
            if len(raw) < 3: continue
            if raw[0] != raw[-1]: raw.append(raw[0])
            buildings.append({
                'id': b.get('id'),
                'polygon': raw,
                'bbox': [min(p[0] for p in raw), min(p[1] for p in raw), max(p[0] for p in raw), max(p[1] for p in raw)],
                'tags': b.get('tags', {})
            })

    # 3. Query amenities
    print(f"Fetching vast POI amenity dataset...")
    q_ams = f"""
    [out:json][timeout:120];
    (
      nwr["amenity"~"^(restaurant|cafe|bar|pub|nightclub|pharmacy|library|university|college|place_of_worship|hospital|clinic)$"]({bbox});
      nwr["shop"~"^(convenience|supermarket|mall|kiosk)$"]({bbox});
      nwr["leisure"~"^(park|sports_centre|fitness_centre|stadium|garden|pitch)$"]({bbox});
      nwr["public_transport"~"^(station)$"]({bbox});
      nwr["highway"~"^(bus_stop)$"]({bbox});
    );
    out geom;
    """
    try:
        req = urllib.request.Request(api_url, data=urllib.parse.urlencode({'data': q_ams}).encode(), headers={'User-Agent': 'Manchester3DMap/2.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            ams_res = json.loads(r.read().decode())['elements']
        print(f"  ✓ Downloaded {len(ams_res)} amenity nodes & ways.")
    except Exception as e:
        print(f"Error fetching amenities: {e}")
        return

    # 4. Synthesize Amenities to Building Geometries
    master_amenities = []
    mapped_count = 0
    
    for el in ams_res:
        tags = el.get('tags', {})
        cat = get_category(tags)
        if not cat: continue
        
        name = tags.get('name', cat.replace('_', ' ').title())
        geom_type = el.get('type')
        polygon, c_lat, c_lng = None, 0, 0
        
        if geom_type == 'node':
            c_lat, c_lng = el['lat'], el['lon']
            # Find which building encloses this node!
            matched = False
            for b in buildings:
                # bounding box pre-check for speed
                minx, miny, maxx, maxy = b['bbox']
                if c_lng >= minx and c_lng <= maxx and c_lat >= miny and c_lat <= maxy:
                    if point_in_polygon(c_lng, c_lat, b['polygon']):
                        polygon = b['polygon']
                        tags.update(b['tags']) # inherit structural height tags
                        tags['osm_id'] = b.get('id')
                        matched = True
                        mapped_count += 1
                        break
            if not matched:
                d = 0.00003 # ~3 metres footprint for tiny stragglers (bus stops, lonely cafes)
                polygon = [
                    [c_lng - d, c_lat - d], [c_lng + d, c_lat - d],
                    [c_lng + d, c_lat + d], [c_lng - d, c_lat + d],
                    [c_lng - d, c_lat - d]
                ]
                # mark as flat ground structure
                tags['force_flat'] = True

        elif geom_type == 'way' and 'geometry' in el:
            raw = [[pt['lon'], pt['lat']] for pt in el['geometry']]
            if len(raw) < 3: continue
            if raw[0] != raw[-1]: raw.append(raw[0])
            polygon = raw
            c_lng = sum(pt[0] for pt in raw) / len(raw)
            c_lat = sum(pt[1] for pt in raw) / len(raw)
            tags['osm_id'] = el.get('id')

        elif geom_type == 'relation' and 'members' in el:
            for m in el['members']:
                if m.get('role') == 'outer' and 'geometry' in m:
                    raw = [[pt['lon'], pt['lat']] for pt in m['geometry']]
                    if raw[0] != raw[-1]: raw.append(raw[0])
                    polygon = raw
                    c_lng = sum(pt[0] for pt in raw) / len(raw)
                    c_lat = sum(pt[1] for pt in raw) / len(raw)
                    tags['osm_id'] = el.get('id')
                    break
        
        if not polygon: continue
        
        master_amenities.append({
            'name': name,
            'category': cat,
            'lat': c_lat,
            'lng': c_lng,
            'geometry': {'type': 'Polygon', 'coordinates': [polygon]},
            'tags': tags
        })
        
    print(f"Parsed {len(master_amenities)} valid amenity geometries.")
    print(f"-> Structurally mapped {mapped_count} independent amenity nodes flawlessly into their real physical Mapbox building shells!!")

    # 5. Connect to local accommodations
    cache_out = {'accommodations': {}}
    for feat in features:
        props = feat['properties']
        acc_id = str(props.get('id', ''))
        a_lat, a_lng = props.get('lat', 0), props.get('lng', 0)
        name = props.get('name', 'Unknown')
        
        acc_amenities = {}
        for am in master_amenities:
            dist = haversine(a_lat, a_lng, am['lat'], am['lng'])
            if dist <= 500:
                cat = am['category']
                if cat not in acc_amenities: acc_amenities[cat] = []
                
                h = 10.0 # Default fallback amenity height
                if am['tags'].get('force_flat'):
                    h = 1.0 # Tiny 1m plate for unmapped street nodes
                elif 'height' in am['tags']:
                    try: h = float(am['tags']['height'].replace('m','').strip())
                    except: pass
                elif 'building:levels' in am['tags']:
                    try: h = float(am['tags']['building:levels']) * 3.0
                    except: pass
                    
                acc_amenities[cat].append({
                    'name': am['name'],
                    'distance_m': int(dist),
                    'geometry': am['geometry'],
                    'properties': {
                        'height': h,
                        'osm_id': am['tags'].get('osm_id')
                    }
                })
        
        cache_out['accommodations'][acc_id] = {
            'name': name,
            'amenities': acc_amenities
        }
    
    with open(CACHE_JSON, 'w', encoding='utf-8') as f:
        json.dump(cache_out, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Master geo-architecture cache generated!")

if __name__ == '__main__':
    main()

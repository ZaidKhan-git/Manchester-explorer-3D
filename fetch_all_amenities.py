"""
fetch_all_amenities.py
======================
Fetches a wide range of amenities for all accommodations within a 500m radius.
To avoid smashing the Overpass API with 50 separate 500m-radius queries,
we execute ONE bounding-box query over the whole area, then calculate 
distances locally.
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

def get_category(tags):
    am = tags.get('amenity', '')
    le = tags.get('leisure', '')
    sh = tags.get('shop', '')
    pub = tags.get('public_transport', '')
    hw = tags.get('highway', '')
    
    if am in ['restaurant']: return 'restaurants'
    if am in ['cafe']: return 'cafes'
    if am in ['bar', 'pub']: return 'bars'
    if am in ['nightclub']: return 'nightclubs'
    if sh in ['convenience']: return 'convenience_stores'
    if sh in ['supermarket']: return 'supermarkets'
    if am in ['pharmacy']: return 'pharmacies'
    if am in ['library']: return 'libraries'
    if pub == 'station' or tags.get('railway') == 'station': return 'metro_stations'
    if hw == 'bus_stop': return 'bus_stops'
    if le in ['park']: return 'parks'
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
    
    # Add a ~500m buffer to the bounding box (~0.005 degrees)
    buffer = 0.006
    bbox = f"{min_lat - buffer},{min_lng - buffer},{max_lat + buffer},{max_lng + buffer}"
    
    # 2. Query Overpass for the whole bounding box
    print(f"Executing massive Overpass bounding-box query ({bbox})...")
    query = f"""
    [out:json][timeout:90];
    (
      nwr["amenity"~"^(restaurant|cafe|bar|pub|nightclub|pharmacy|library|university|college|place_of_worship)$"]({bbox});
      nwr["shop"~"^(convenience|supermarket)$"]({bbox});
      nwr["leisure"~"^(park|sports_centre|fitness_centre|stadium)$"]({bbox});
      nwr["public_transport"~"^(station)$"]({bbox});
      nwr["highway"~"^(bus_stop)$"]({bbox});
    );
    out geom;
    """
    
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    url = "https://overpass-api.de/api/interpreter"
    
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'Manchester3DMap/1.0'})
    
    try:
        start = time.time()
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
        print(f"Downloaded {len(result.get('elements', []))} features in {time.time()-start:.1f}s")
    except Exception as e:
        print(f"Overpass Error: {e}")
        return

    # 3. Parse downloaded amenities into a master list
    master_amenities = []
    
    for el in result.get('elements', []):
        tags = el.get('tags', {})
        cat = get_category(tags)
        if not cat: continue
        
        name = tags.get('name', '')
        if not name:
            name = cat.replace('_', ' ').title()
            
        geom_type = el.get('type')
        polygon = []
        c_lat, c_lng = 0, 0
        
        if geom_type == 'node':
            c_lat, c_lng = el['lat'], el['lon']
            d = 0.0001
            polygon = [
                [c_lng - d, c_lat - d], [c_lng + d, c_lat - d],
                [c_lng + d, c_lat + d], [c_lng - d, c_lat + d],
                [c_lng - d, c_lat - d]
            ]
        elif geom_type == 'way' and 'geometry' in el:
            raw = [[pt['lon'], pt['lat']] for pt in el['geometry']]
            if len(raw) < 3: continue
            if raw[0] != raw[-1]: raw.append(raw[0])
            polygon = raw
            c_lng = sum(pt[0] for pt in raw) / len(raw)
            c_lat = sum(pt[1] for pt in raw) / len(raw)
        elif geom_type == 'relation' and 'members' in el:
            for m in el['members']:
                if m.get('role') == 'outer' and 'geometry' in m:
                    raw = [[pt['lon'], pt['lat']] for pt in m['geometry']]
                    if raw[0] != raw[-1]: raw.append(raw[0])
                    polygon = raw
                    c_lng = sum(pt[0] for pt in raw) / len(raw)
                    c_lat = sum(pt[1] for pt in raw) / len(raw)
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
        
    print(f"Parsed {len(master_amenities)} valid amenity polygons from Overpass.")

    # 4. Map them to each accommodation within 500m
    cache_out = {'accommodations': {}}
    
    for feat in features:
        props = feat['properties']
        acc_id = str(props.get('id', ''))
        a_lat = props.get('lat', 0)
        a_lng = props.get('lng', 0)
        name = props.get('name', 'Unknown')
        
        acc_amenities = {}
        
        for am in master_amenities:
            dist = haversine(a_lat, a_lng, am['lat'], am['lng'])
            if dist <= 500:
                cat = am['category']
                if cat not in acc_amenities:
                    acc_amenities[cat] = []
                
                # Try to extract a height if available
                height = 7.0
                if 'height' in am['tags']:
                    try:
                        h_str = am['tags']['height'].replace('m','').strip()
                        height = float(h_str)
                    except: pass
                    
                acc_amenities[cat].append({
                    'name': am['name'],
                    'distance_m': int(dist),
                    'geometry': am['geometry'],
                    'properties': {
                        'height': height
                    }
                })
        
        total_found = sum(len(v) for v in acc_amenities.values())
        print(f"  {name}: {total_found} amenities within 500m")
        
        cache_out['accommodations'][acc_id] = {
            'name': name,
            'amenities': acc_amenities
        }
    
    with open(CACHE_JSON, 'w', encoding='utf-8') as f:
        json.dump(cache_out, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Created fresh amenities_cache.json with full 500m radius data!")
    print("👉 Next run: python build_db_data.py")

if __name__ == '__main__':
    main()

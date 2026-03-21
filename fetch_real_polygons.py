import urllib.request
import urllib.parse
import json
import os
import time

print("Fetching flawless native architectural footprints...")

accommodations = [
    {"name": "Chapter Spitalfields", "cat": "Student Accommodation", "lat": 51.5178, "lng": -0.0764},
    {"name": "King's College London", "cat": "College", "lat": 51.5115, "lng": -0.1165},
    {"name": "Urbanest Westminster", "cat": "Student Accommodation", "lat": 51.5015, "lng": -0.1156},
    {"name": "UCL Astor College", "cat": "Student Accommodation", "lat": 51.5222, "lng": -0.1384},
    {"name": "LSE Bankside House", "cat": "Student Accommodation", "lat": 51.5065, "lng": -0.0988},
    {"name": "QMUL Westfield Village", "cat": "Student Accommodation", "lat": 51.5235, "lng": -0.0416},
    {"name": "Imperial College Princes Gardens", "cat": "College", "lat": 51.5015, "lng": -0.1741},
    {"name": "King's College Stamford St", "cat": "Student Accommodation", "lat": 51.5052, "lng": -0.1085},
    {"name": "Chapter Islington", "cat": "Student Accommodation", "lat": 51.5432, "lng": -0.1165},
    {"name": "iQ Shoreditch", "cat": "Student Accommodation", "lat": 51.5262, "lng": -0.0863},
    {"name": "Scape Mile End", "cat": "Student Accommodation", "lat": 51.5228, "lng": -0.0381},
    {"name": "Unite Students Stratford ONE", "cat": "Student Accommodation", "lat": 51.5412, "lng": -0.0069},
    {"name": "Chapter South Bank", "cat": "Student Accommodation", "lat": 51.5048, "lng": -0.1012}
]

features = []
endpoints = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

for idx, acc in enumerate(accommodations):
    print(f"[{idx+1}/13] Mapping {acc['name']}...")
    
    query = f"""
    [out:json][timeout:10];
    (
      way["building"](around:35, {acc['lat']}, {acc['lng']});
    );
    out geom;
    """
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    
    response_data = None
    for url in endpoints:
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=12) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                break
        except Exception as e:
            print(f"  Mirror {url} failed: {e}")
            pass
            
    if response_data and 'elements' in response_data:
        # Find the way with the most geometry points to represent the complex building accurately
        best_way = None
        max_pts = 0
        for way in response_data['elements']:
            if way.get('type') == 'way' and 'geometry' in way:
                if len(way['geometry']) > max_pts:
                    max_pts = len(way['geometry'])
                    best_way = way
                    
        if best_way:
            coords = [[pt['lon'], pt['lat']] for pt in best_way['geometry']]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
                
            tags = best_way.get('tags', {})
            height = 30.0
            if 'height' in tags and tags['height'].replace('.', '', 1).isdigit():
                height = float(tags['height'])
            elif 'building:levels' in tags and tags['building:levels'].isdigit():
                height = float(tags['building:levels']) * 3.0
                
            features.append({
                "type": "Feature",
                "properties": {
                    "name": acc['name'], "category": acc['cat'],
                    "location": tags.get('addr:street', 'Central London'),
                    "height": height, "base_height": 0.5,
                    "commodities": ["Neighborhood scanner active! Click to deploy."],
                    "facilities": [], "transport": []
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]}
            })
            print(f"  -> Captured exact footprint ({len(coords)} coordinates).")
        else:
            print("  -> No precise building geometry found within radius.")
    else:
        print("  -> All mirrors failed to retrieve data for this location.")
        
    time.sleep(1)

if features:
    out_path = os.path.join(os.path.dirname(__file__), 'data.js')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("const accommodationsData = " + json.dumps({"type": "FeatureCollection", "features": features}, indent=4) + ";\n")
    print(f"\nCOMPLETED! Written {len(features)} precisely aligned organic geometries to data.js")
else:
    print("FATAL: Failed to capture any features.")

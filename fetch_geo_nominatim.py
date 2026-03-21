import urllib.request
import urllib.parse
import json
import os
import time

print("Accessing Nominatim API for exact mapping footprints...")

queries = [
    {"q": "Chapter Spitalfields, London", "cat": "Student Accommodation", "h": 110},
    {"q": "King's College London, Strand", "cat": "College", "h": 45},
    {"q": "Urbanest Westminster Bridge, London", "cat": "Student Accommodation", "h": 60},
    {"q": "Astor College, London", "cat": "Student Accommodation", "h": 35},
    {"q": "Bankside House, London", "cat": "Student Accommodation", "h": 25},
    {"q": "Westfield Village, Queen Mary, London", "cat": "Student Accommodation", "h": 20},
    {"q": "Stamford Street Apartments, London", "cat": "Student Accommodation", "h": 30},
    {"q": "Chapter Islington, London", "cat": "Student Accommodation", "h": 40},
    {"q": "iQ Shoreditch, London", "cat": "Student Accommodation", "h": 65},
    {"q": "Stratford ONE, Unite Students, London", "cat": "Student Accommodation", "h": 80},
    {"q": "LSE Rosebery Hall, London", "cat": "Student Accommodation", "h": 30},
    {"q": "LSE Passfield Hall, London", "cat": "Student Accommodation", "h": 30},
    {"q": "London School of Economics, London", "cat": "College", "h": 40}
]

features = []

for item in queries:
    print(f"Querying geometry for: {item['q']}")
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(item['q'])}&format=geojson&polygon_geojson=1&limit=1"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'LondonMapApp/1.0 (Integration Test)'})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data['features']:
                feat = data['features'][0]
                geom = feat.get('geometry')
                
                if geom['type'] == 'Polygon':
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "name": item['q'].split(',')[0], "category": item['cat'],
                            "location": "Central London", "height": item['h'],
                            "base_height": 0.5, "commodities": ["Neighborhood scanner active! Click to deploy."],
                            "facilities": [], "transport": []
                        },
                        "geometry": {"type": "Polygon", "coordinates": geom['coordinates']}
                    })
                    print("  -> SUCCESS: Authentic geometry polygon recorded.")
                elif geom['type'] == 'MultiPolygon':
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "name": item['q'].split(',')[0], "category": item['cat'],
                            "location": "Central London", "height": item['h'],
                            "base_height": 0.5, "commodities": ["Neighborhood scanner active! Click to deploy."],
                            "facilities": [], "transport": []
                        },
                        "geometry": {"type": "Polygon", "coordinates": geom['coordinates'][0]}
                    })
                    print("  -> SUCCESS: Authentic geometry recorded from MultiPolygon.")
                else:
                    print("  -> ERROR: Location found but no structural polygon footprint provided (mapped as point). Skipped to prevent blocky 3d misalignments.")
            else:
                print("  -> ERROR: Location completely unindexed under this string match.")
    except Exception as e:
        print(f"  -> NETWORK ERROR: {e}")
        
    time.sleep(1.2) # Rate limit exactly 1 per sec per Nominatim guidelines

out_path = os.path.join(os.path.dirname(__file__), 'data.js')
if features:
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("const accommodationsData = " + json.dumps({"type": "FeatureCollection", "features": features}, indent=4) + ";\n")
    print(f"\nWritten {len(features)} perfect structural matches to data.js.")
else:
    print("FATAL: No geometry polygons generated.")

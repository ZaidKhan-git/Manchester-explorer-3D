import urllib.request
import json
import os

print("Fetching targeted Student Accommodations and Colleges...")

query = """
[out:json][timeout:60];
(
  way["amenity"~"student_accommodation|college|university"](51.4500, -0.2000, 51.5600, 0.0500);
);
out geom;
"""

url = "http://overpass-api.de/api/interpreter"
req = urllib.request.Request(url, data=query.encode('utf-8'))

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        
        features = []
        for way in data.get('elements', []):
            if way.get('type') == 'way' and 'geometry' in way:
                coords = [[pt['lon'], pt['lat']] for pt in way['geometry']]
                if len(coords) < 3:
                    continue
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                
                tags = way.get('tags', {})
                name = tags.get('name', 'Unnamed Location')
                
                amenity = tags.get('amenity')
                category = 'Student Accommodation' if amenity == 'student_accommodation' else 'College'
                
                height = 25.0
                if tags.get('height') and tags.get('height').replace('.','',1).isdigit():
                    height = float(tags.get('height'))
                elif tags.get('building:levels') and tags.get('building:levels').isdigit():
                    height = float(tags.get('building:levels')) * 3.0
                
                feature = {
                    "type": "Feature",
                    "properties": {
                        "name": name,
                        "category": category,
                        "location": tags.get('addr:street', 'London'),
                        "height": height,
                        "base_height": 0.5,
                        "commodities": ["Click here to fetch neighborhood amenities!"],
                        "facilities": [],
                        "transport": []
                    },
                    "geometry": { "type": "Polygon", "coordinates": [coords] }
                }
                features.append(feature)
        
        out_path = os.path.join(os.path.dirname(__file__), 'data.js')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("const accommodationsData = " + json.dumps({"type": "FeatureCollection", "features": features}, indent=4) + ";\n")
            
        print(f"Success! Saved {len(features)} root locations to data.js")
except Exception as e:
    print(f"Error fetching data: {e}")

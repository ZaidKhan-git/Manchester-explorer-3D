import urllib.request, urllib.parse, json

def find_buildings(lat, lng, name, radius=30):
    query = f"""
    [out:json];
    (
      way["building"](around:{radius},{lat},{lng});
      relation["building"](around:{radius},{lat},{lng});
      node["building"](around:{radius},{lat},{lng});
      way["building:part"](around:{radius},{lat},{lng});
    );
    out tags qt;
    """
    url = f"https://overpass-api.de/api/interpreter?data={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'ManchesterMapCheck/1.0'})
    print(f"\n--- {name} ---")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            for el in data['elements']:
                tags = el.get('tags', {})
                b_type = tags.get('building', tags.get('building:part', ''))
                print(f"ID: {el['id']} | Type: {el['type']}/{b_type} | Name: {tags.get('name', '')}")
    except Exception as e:
        print("Error:", e)

find_buildings(53.473618, -2.240822, "Artisan Heights")
find_buildings(53.473478, -2.241862, "Bridgewater Heights")

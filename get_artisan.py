import urllib.request, urllib.parse, json

def find_buildings(lat, lng, name, radius=35):
    query = f"""
    [out:json];
    (
      way["building"](around:{radius},{lat},{lng});
      node["building"](around:{radius},{lat},{lng});
    );
    out tags qt;
    """
    url = f"https://z.overpass-api.de/api/interpreter?data={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'ManchesterMapCheck/1.0'})
    print(f"\n--- {name} ---")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            print([el['id'] for el in data.get('elements', [])])
    except Exception as e:
        print("Error:", e)

find_buildings(53.473618, -2.240822, "Artisan Heights")

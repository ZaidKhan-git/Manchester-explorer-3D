import json

with open('data/amenities_cache.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

summary = {}
for acc_id, acc in d.get('accommodations', {}).items():
    for k, v in acc.get('amenities', {}).items():
        if isinstance(v, list):
            summary[k] = summary.get(k, 0) + len(v)

print("Total elements per category in amenities_cache.json:")
for k, v in summary.items():
    print(f"  {k}: {v}")

with open('data/manchester_amenities.js', 'r', encoding='utf-8') as f:
    content = f.read()
    # It's a JS file starting with "const manchesterAmenitiesData = "
    json_str = content[content.find('{') : -2] # slice off semicolon and newline
    js_data = json.loads(json_str)

js_summary = {}
for acc_id, acc in js_data.items():
    for feat in acc.get('features', []):
        cat = feat['properties']['category']
        js_summary[cat] = js_summary.get(cat, 0) + 1

print("\nTotal elements per category exported to manchester_amenities.js:")
for k, v in js_summary.items():
    print(f"  {k}: {v}")

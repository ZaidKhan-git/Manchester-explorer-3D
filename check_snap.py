import json

with open('data/accommodations.geojson', 'r', encoding='utf-8') as f:
    geo = json.load(f)

lines = []
lines.append(f"{'ID':>10s}  {'Name':40s}  {'Source':8s}  {'OSM ID':25s}  {'Lat':>10s}  {'Lng':>10s}")
lines.append("-" * 120)

for feat in geo['features']:
    p = feat['properties']
    lines.append(f"{p.get('id','?'):>10s}  {p['name'][:40]:40s}  {p.get('geometry_source','?'):8s}  {p.get('osm_id','?'):25s}  {p.get('lat','?'):>10s}  {p.get('lng','?'):>10s}")

with open('snap_final_report.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Wrote {len(lines)} lines to snap_final_report.txt")

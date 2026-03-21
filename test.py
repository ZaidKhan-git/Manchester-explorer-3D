import urllib.request
import json
import urllib.parse

q="""
[out:json];
node["amenity"="cafe"](53.473,-2.241,53.474,-2.240)->.pts;
.pts out geom;
way(around.pts:0)["building"]->.bldgs;
.bldgs out geom;
"""
req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=urllib.parse.urlencode({'data':q}).encode())
try:
    print(len(json.loads(urllib.request.urlopen(req).read().decode())['elements']))
except Exception as e:
    print("Error:", e)

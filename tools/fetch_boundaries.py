#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국내 행정 경계(시·도, 시·군·구)를 받아 간략화해 저장한다.

    python3 tools/fetch_boundaries.py

출처: github.com/southkorea/southkorea-maps (통계청 SGIS 2018 기반, 공개 자료)
원본이 25MB라 지도에 그릴 때 눈에 띄지 않을 만큼만 점을 줄여 넣는다.
"""
import json, os, sys, urllib.request
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "data", "geo")
BASE = ("https://raw.githubusercontent.com/southkorea/southkorea-maps/"
        "master/kostat/2018/json/")
FILES = [("skorea-provinces-2018-geo.json",     "sido.json",   0.0012),
         ("skorea-municipalities-2018-geo.json","sigungu.json",0.0008)]

def main():
    os.makedirs(OUT, exist_ok=True)
    for src, dst, tol in FILES:
        raw = os.path.join("/tmp", src)
        if not os.path.exists(raw) or os.path.getsize(raw) < 10000:
            print(f"내려받는 중 {src} …")
            urllib.request.urlretrieve(BASE + src, raw)
        g = json.load(open(raw, encoding="utf-8"))
        feats = []
        for f in g["features"]:
            geom = shape(f["geometry"]).buffer(0).simplify(tol, preserve_topology=True)
            if geom.is_empty:
                continue
            name = f["properties"].get("name") or f["properties"].get("name_eng")
            feats.append({"type": "Feature",
                          "properties": {"name": name},
                          "geometry": mapping(geom)})
        path = os.path.join(OUT, dst)
        json.dump({"type": "FeatureCollection", "features": feats},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False,
                  separators=(",", ":"))
        print(f"{dst}: {len(feats)}개  "
              f"{os.path.getsize(raw)//1024}KB → {os.path.getsize(path)//1024}KB")

if __name__ == "__main__":
    main()

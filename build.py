#!/usr/bin/env python3
"""index.html + data/items.js + assets/maps/*.png 을 한 파일로 합칩니다.

    python3 build.py

결과물 '지역이해-암기퀴즈.html' 은 파일 하나만 있으면 어디서든 열립니다.
폴더 구조도, 인터넷도 필요 없습니다(글꼴만 있으면 더 예쁘게 보일 뿐).
데이터나 화면을 고친 뒤에는 이 스크립트를 다시 돌리세요.
"""
import base64, re, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(ROOT, "지역이해-암기퀴즈.html")

html  = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
items = open(os.path.join(ROOT, "data", "items.js"), encoding="utf-8").read()

paths = re.findall(r'image:\s*"(assets/maps/[^"]+)"', items)
if not paths:
    sys.exit("지도 경로를 찾지 못했습니다. data/items.js 의 MAPS 를 확인하세요.")
for p in paths:
    full = os.path.join(ROOT, p)
    uri = "data:image/png;base64," + base64.b64encode(open(full, "rb").read()).decode()
    items = items.replace(f'"{p}"', f'"{uri}"')

items = re.sub(r'if \(typeof module.*?\}\n?', '', items, flags=re.S)

single = html.replace('<script src="data/items.js"></script>', "<script>\n" + items + "\n</script>")
if 'src="data/items.js"' in single or "assets/maps/" in single:
    sys.exit("외부 파일 참조가 남아 있습니다.")

open(OUT, "w", encoding="utf-8").write(single)
print(f"{os.path.basename(OUT)} — {len(paths)}장의 지도 포함, {os.path.getsize(OUT):,} bytes")

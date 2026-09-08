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

# module.exports 줄 제거 (줄 전체를 지운다 — 예전에 정규식이 줄을 반쯤 잘라
# 문법 오류를 만든 적이 있어, 아래에서 node로 반드시 검사한다)
items = re.sub(r'^.*typeof module.*$', '', items, flags=re.M)

single = html.replace('<script src="data/items.js"></script>', "<script>\n" + items + "\n</script>")
if 'src="data/items.js"' in single or "assets/maps/" in single:
    sys.exit("외부 파일 참조가 남아 있습니다.")

# ── 합친 결과가 실제로 실행 가능한지 검사 ──────────────────────
import subprocess, tempfile, shutil
scripts = re.findall(r"<script>(.*?)</script>", single, flags=re.S)
if len(scripts) < 2:
    sys.exit("script 블록을 찾지 못했습니다.")
node = shutil.which("node") or shutil.which("bun")
if node:
    for n, code in enumerate(scripts, 1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(code); tmp = f.name
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        if r.returncode != 0:
            sys.exit(f"script 블록 {n}에 문법 오류가 있습니다:\n{r.stderr}")
    print(f"문법 검사 통과 (script 블록 {len(scripts)}개)")
else:
    print("경고: node/bun 이 없어 문법 검사를 건너뜁니다.")

for need in ("const ITEMS", "const UNITS", "const MAPS", "function home()"):
    if need not in single:
        sys.exit(f"'{need}' 가 결과물에 없습니다.")

open(OUT, "w", encoding="utf-8").write(single)
print(f"{os.path.basename(OUT)} — {len(paths)}장의 지도 포함, {os.path.getsize(OUT):,} bytes")

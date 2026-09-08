#!/usr/bin/env python3
"""학습지 PDF에서 지도를 추출한다.

    python3 tools/make_maps.py <학습지.pdf>

스캔 원본이 125dpi 컬러 JPEG이므로, 페이지를 다시 렌더링하지 않고
PDF에 박혀 있는 이미지를 그대로 꺼내 쓴다(그래야 화질 손실이 없다).
- 회색 종이 배경을 흰색으로 펴고 선을 진하게 한다
- 정답이 적혀 있는 손글씨는 좌표로 지정해 지운다
"""
import sys, io, os
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import pymupdf

PDF = sys.argv[1] if len(sys.argv) > 1 else sys.exit("PDF 경로를 넘겨주세요.")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "maps")
os.makedirs(OUT, exist_ok=True)

# (쪽 index, 이름, 자르기 비율 x0,y0,x1,y1, 배경정리 여부, 지울 손글씨 상자[자른 뒤 좌표])
MAPS = [
    (1,  "kr_admin",    (.13,.13,.92,.68), True,  []),
    (3,  "sudogwon",    (.095,.455,.44,.73), True,  []),
    (7,  "chungcheong", (.22,.168,.80,.375), True,  []),
    (10, "gangwon",     (.25,.157,.78,.40), True,  []),
    (13, "honam",       (.28,.277,.78,.57), True,  []),
    # 오대양 지도는 망점 인쇄라 배경을 펴면 오히려 뭉개진다 → 원본 질감 유지
    (16, "world_ocean", (.17,.135,.86,.36), False,
         [(98,90,130,118),     # 유럽
          (168,60,228,96),     # 우랄산맥(빨간 선 포함)
          (220,98,274,128),    # 아시아
          (88,144,152,176),    # 아프리카
          (276,230,342,260),   # 오세아니아
          (486,92,580,122),    # 북아메리카
          (566,203,634,234)]), # 남아메리카
    (17, "world_pen",   (.06,.16,.96,.435), True,
         [(0,26,80,92),        # 이탈리아반도·발칸반도 (여백)
          (106,46,204,76),     # 스칸디나비아 반도
          (10,158,74,188),     # 이베리아 반도
          (738,340,939,999)]), # 우하단 빨간 메모
    (20, "world_sea",   (.10,.163,.94,.45), True,  []),
]

def flatten(g):
    """종이 배경을 흰색으로 펴고 선을 진하게."""
    bg = g.filter(ImageFilter.MaxFilter(15))
    a, b = np.asarray(g, float), np.asarray(bg, float) + 1
    flat = np.clip(a / b * 255, 0, 255)
    out = np.clip((flat - 118.0) / (232.0 - 118.0) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(out).filter(ImageFilter.UnsharpMask(1.4, 110, 2))

def gentle(g):
    """망점 인쇄물: 배경을 펴지 않고 대비만 살짝."""
    a = np.asarray(g, float)
    return Image.fromarray(np.clip((a - 40) / (225 - 40) * 255, 0, 255).astype(np.uint8))

doc = pymupdf.open(PDF)
for pi, name, frac, do_flatten, erase in MAPS:
    info = doc.extract_image(doc[pi].get_images(full=True)[0][0])
    g = Image.open(io.BytesIO(info["image"])).convert("L")
    W, H = g.size
    g = (flatten if do_flatten else gentle)(g)
    x0, y0, x1, y1 = (int(W*frac[0]), int(H*frac[1]), int(W*frac[2]), int(H*frac[3]))
    im = g.crop((x0, y0, x1, y1))
    if erase:
        d = ImageDraw.Draw(im)
        for bx in erase:
            d.rectangle([bx[0], bx[1], min(bx[2], im.width), min(bx[3], im.height)], fill=255)
    im.save(os.path.join(OUT, name + ".png"), optimize=True)
    kb = os.path.getsize(os.path.join(OUT, name + ".png")) // 1024
    print(f"{name:14s} {im.width}×{im.height}  {kb}KB  손글씨 {len(erase)}곳 지움")

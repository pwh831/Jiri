#!/usr/bin/env python3
"""학습지 원본 PDF(디지털본)에서 퀴즈용 지도를 그대로 뽑아 assets/maps 에 쓴다.

    python3 tools/extract_maps.py <학습지 PDF 경로>

스캔본에서 뽑던 tools/make_maps.py 를 대신한다. 스캔본은 선이 뭉개지고
손글씨 정답이 비쳐 보여 지우는 보정이 필요했지만, 원본 PDF는 깨끗하다.

지도 번호(①②③…)가 이미지가 아니라 PDF 텍스트 레이어로 얹혀 있어서
이미지를 추출하지 않고 **그 영역을 통째로 렌더링**한다. 그래야 번호가 함께 나온다.
영역은 쪽을 그려 보고 눈으로 맞춘 값이다(PDF가 알려 주는 이미지 bbox 는
흰 여백까지 포함해 단원 제목줄이나 아래 표까지 끌고 들어온다).

예외가 하나 있다. 17개 시·도 지도는 학습지에 이름 적는 빈 네모와 지시선이
겹쳐 그려져 있어서 렌더링하면 지저분하다. 이것만 원본 이미지를 그대로 꺼낸다.
"""
import io
import os
import sys

import pymupdf
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "maps")
DPI = 300
MAXW = 1500          # 앱에서 이보다 크게 볼 일이 없다

# (이름, PDF 쪽(1부터), 학습지 쪽, 자를 영역 또는 None(=원본 이미지 추출), 회색조 여부, 설명)
MAPS = [
    ("kr_admin",    2, "2쪽",  None,                          True,  "우리나라 행정구역(17개 시·도)"),
    ("sudogwon",    4, "4쪽",  (60.7, 390.1, 271.9, 628.4),   True,  "수도권 1~13"),
    ("chungcheong", 8, "8쪽",  (169.0, 141.1, 425.9, 304.7),  True,  "충청권 1~18"),
    ("gangwon",    11, "11쪽", (185.8, 123.3, 409.0, 319.6),  True,  "강원권 1~13"),
    ("world_ocean", 22, "25쪽", (108.0, 108.0, 492.0, 297.0), False, "오대양 1~5"),
    ("world_pen",   23, "26쪽", (60.0, 143.0, 545.0, 382.0),  True,  "세계의 주요 반도와 섬 ①~⑳"),
    ("world_sea",   26, "29쪽", (70.0, 128.0, 532.0, 376.0),  True,  "세계의 주요 바다와 호수 ①~⑳"),
    ("world_range", 29, "32쪽", (100.5, 479.4, 494.4, 755.4), True,  "세계의 주요 산맥 ①~⑨"),
    ("world_river", 31, "34쪽", (125.0, 445.0, 525.0, 665.0), True,  "세계의 주요 하천 ①~⑭"),
]


def load(doc, page_no, rect, gray):
    page = doc[page_no - 1]
    if rect is None:                                   # 원본 이미지 그대로
        xref = page.get_images(full=True)[0][0]
        return Image.open(io.BytesIO(doc.extract_image(xref)["image"]))
    cs = pymupdf.csGRAY if gray else pymupdf.csRGB
    pix = page.get_pixmap(dpi=DPI, clip=pymupdf.Rect(*rect), colorspace=cs)
    mode = "L" if gray else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def main(pdf_path):
    doc = pymupdf.open(pdf_path)
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for name, page_no, sheet, rect, gray, label in MAPS:
        im = load(doc, page_no, rect, gray)
        if im.width > MAXW:
            im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
        if gray and im.mode != "L":
            im = im.convert("L")
        # 회색조 선화는 PNG 가 작고 선명하다. 색이 있는 지도(오대양)는 PNG 로 두면
        # 1.7MB 가 넘어 단일 파일 배포본이 무거워지므로 JPEG 로 저장한다.
        ext = "png" if gray else "jpg"
        path = os.path.join(OUT, f"{name}.{ext}")
        for stale in (".png", ".jpg"):                 # 형식이 바뀌면 옛 파일을 지운다
            old = os.path.join(OUT, name + stale)
            if stale != "." + ext and os.path.exists(old):
                os.remove(old)
        im.save(path, optimize=True, **({} if gray else {"quality": 82}))
        kb = os.path.getsize(path) // 1024
        total += kb
        print(f"  {name:12s} {sheet:>4s}  {im.width}x{im.height}  {kb:>4d}KB  {ext}  {label}")
    print(f"\n{len(MAPS)}장 · 합계 {total}KB → {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

#!/usr/bin/env python3
"""학습지 원본 PDF 의 빈칸 정답(흰 글씨)을 검은 글씨로 바꾼 '빈칸 채운 학습지'를 만든다.

    python3 tools/fill_blanks.py 원본.pdf 결과.pdf [--color 0,0,0]

한글(Hwp)로 만든 PDF 는 글자 덩어리마다 BT 바로 앞에서 색을 정한다
('1 G 1 g BT …' 가 흰 글씨). 그 자리의 색만 바꾸므로 흰 바탕·흰 상자 같은
도형(`1 g … re f`)은 그대로 두고, 글꼴·자리·크기도 원본 그대로 남는다.
"""
import argparse, re, sys
import pymupdf

WHITE_TEXT = re.compile(rb"1 G(\s+)1 g(\s+BT\b)")


def white_spans(doc):
    n = 0
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["color"] == 0xFFFFFF and s["text"].strip():
                        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--color", default="0,0,0", help="바꿀 색 r,g,b (0~1), 기본 검정")
    a = ap.parse_args()
    r, g, b = (float(x) for x in a.color.split(","))
    # 회색조면 G/g, 아니면 RG/rg 로 쓴다
    if r == g == b:
        rep = lambda m: b"%g G" % r + m.group(1) + b"%g g" % r + m.group(2)
    else:
        rep = lambda m: b"%g %g %g RG" % (r, g, b) + m.group(1) + b"%g %g %g rg" % (r, g, b) + m.group(2)

    doc = pymupdf.open(a.src)
    before = white_spans(doc)
    changed = 0
    for page in doc:
        for xref in page.get_contents():
            raw = doc.xref_stream(xref)
            new, k = WHITE_TEXT.subn(rep, raw)
            if k:
                doc.update_stream(xref, new)
                changed += k
    after = white_spans(doc)
    doc.save(a.out, garbage=3, deflate=True)
    print(f"흰 글씨 {before}조각 → 남은 흰 글씨 {after}조각 (색 바꾼 자리 {changed}곳) · {doc.page_count}쪽 → {a.out}")
    if after:
        sys.exit("흰 글씨가 남았습니다. 다른 색 지정 방식이 섞여 있는지 확인하세요.")


if __name__ == "__main__":
    main()

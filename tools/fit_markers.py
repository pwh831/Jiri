#!/usr/bin/env python3
"""17개 시·도 지도가 바뀌었을 때 marker 좌표를 옮겨 준다.

    python3 tools/fit_markers.py <옛 지도> <새 지도>            # 계산만
    python3 tools/fit_markers.py <옛 지도> <새 지도> --write    # items.js 반영

같은 지도 그림을 크기·여백만 달리해 실은 경우라면, 두 그림을 겹쳐 보고
배율과 이동량을 찾아내 손으로 찍어 둔 퍼센트 좌표를 그대로 옮길 수 있다.
이동량은 FFT 상호상관으로 한 번에 구하고, 배율만 훑는다.
"""
import argparse
import os
import re

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.js")


def ink(path):
    return (np.array(Image.open(path).convert("L")) < 200).astype(np.float32)


def best_shift(a, b):
    """b 를 a 에 맞추는 (dy, dx) 와 그때의 상관값. 두 배열 크기는 같아야 한다."""
    F = np.fft.rfft2(a) * np.conj(np.fft.rfft2(b))
    c = np.fft.irfft2(F, s=a.shape)
    idx = int(np.argmax(c))
    dy, dx = np.unravel_index(idx, c.shape)
    H, W = a.shape
    if dy > H // 2:
        dy -= H
    if dx > W // 2:
        dx -= W
    return dy, dx, float(c.max())


def register(old_path, new_path):
    O, N = ink(old_path), ink(new_path)
    H, W = N.shape
    best = None
    for s in np.arange(0.70, 1.45, 0.005):
        oh, ow = max(1, round(O.shape[0] * s)), max(1, round(O.shape[1] * s))
        if oh > H * 1.6 or ow > W * 1.6:
            continue
        r = np.array(Image.fromarray((O * 255).astype(np.uint8)).resize((ow, oh), Image.BILINEAR),
                     dtype=np.float32) / 255.0
        pad = np.zeros((H, W), np.float32)
        h, w = min(oh, H), min(ow, W)
        pad[:h, :w] = r[:h, :w]
        dy, dx, score = best_shift(N, pad)
        # 겹치는 잉크 양으로 다시 점수 매기기(상관값은 크기에 휘둘린다)
        m = np.roll(np.roll(pad, dy, axis=0), dx, axis=1)
        inter = float(np.sum((m > 0.3) & (N > 0.3)))
        union = float(np.sum((m > 0.3) | (N > 0.3)))
        iou = inter / union if union else 0.0
        if best is None or iou > best[0]:
            best = (iou, s, dy, dx)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    iou, s, dy, dx = register(a.old, a.new)
    oh, ow = Image.open(a.old).size[1], Image.open(a.old).size[0]
    nh, nw = Image.open(a.new).size[1], Image.open(a.new).size[0]
    print(f"겹침 IoU={iou:.3f}  배율={s:.3f}  이동=({dx},{dy})px  "
          f"옛 {ow}x{oh} → 새 {nw}x{nh}")

    def conv(x_pct, y_pct):
        x_old = x_pct / 100 * ow
        y_old = y_pct / 100 * oh
        return (round(100 * (x_old * s + dx) / nw, 1),
                round(100 * (y_old * s + dy) / nh, 1))

    src = open(ITEMS, encoding="utf-8").read()
    rows = []

    def sub(m):
        x, y = float(m.group(2)), float(m.group(4))
        X, Y = conv(x, y)
        rows.append((m.group(1).split('"')[1] if '"' in m.group(1) else "", x, y, X, Y))
        return m.group(1) + str(X) + m.group(3) + str(Y) + m.group(5)

    out = re.sub(r'(name:"[^"]+", aliases:\[[^\]]*\], marker:\{x:)([\d.]+)(,y:)([\d.]+)(\})', sub, src)
    for nm, x, y, X, Y in rows:
        print(f"  {nm:10s} {x},{y} → {X},{Y}")
    print(f"{len(rows)}개 마커")
    if a.write:
        open(ITEMS, "w", encoding="utf-8").write(out)
        print("data/items.js 에 반영했습니다.")


if __name__ == "__main__":
    main()

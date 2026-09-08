#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정답이 모두 적힌 지도를 PDF로 만든다 (굿노트 필기용).

    python3 tools/make_answer_maps.py

지도 데이터: Natural Earth / GSHHG 해안선 (public domain)
글자: 나눔고딕. PDF는 벡터라 확대해도 깨지지 않는다.
"""
import sys, os, re, json, textwrap
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42   # TrueType 내장 → 글자 검색·복사 가능
import koreanize_matplotlib                      # 한글 폰트 설정
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patheffects import withStroke
from mpl_toolkits.basemap import Basemap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from places import WORLD, KOREA

PAPER, INK, INK2, FAINT = "#FBF9F4", "#1F1B16", "#5C554A", "#8A8272"
WATER, MOSS, VERM, RULE  = "#33596B", "#4A6E44", "#B0512C", "#C9C1B0"
SEA, LAND                = "#EAF0F3", "#FFFFFF"

# ── 학습지 특징 불러오기 ──────────────────────────────────────
def load_features():
    src = open(os.path.join(ROOT, "data", "items.js"), encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'name:"([^"]+)", aliases:\[[^\]]*\],?\s*(?:marker:\{[^}]*\},)?\s*\n?\s*features:\[(.*?)\]\s*\}', src, re.S):
        out[m.group(1)] = re.findall(r'"([^"]+)"', m.group(2))
    return out
FEATS = load_features()

# ── 페이지 정의 ──────────────────────────────────────────────
# (지역키, 큰제목, 단원, 지도설정, 글자크기, 점크기)
PAGES = [
 ("peninsula",  "세계의 주요 반도",        "010", "world",       8.5, 22),
 ("island",     "세계의 주요 섬",          "010", "world",       8.5, 22),
 ("sea",        "세계의 주요 바다와 만",   "011", "world",       8.5, 22),
 ("lakestrait", "세계의 호수·해협과 오대양","009 · 011","world",  8.5, 22),
 ("sido",       "우리나라 17개 시·도",     "001", "kr_all",      9.0, 26),
 ("sudogwon",   "수도권",                  "002", "kr_sudo",     9.0, 26),
 ("chungcheong","충청 지방",               "003", "kr_chung",    9.0, 26),
 ("gangwon",    "강원 지방",               "004", "kr_gang",     9.0, 26),
 ("honam",      "호남 지방",               "005", "kr_honam",    8.5, 26),
]
# 지도 범위: (llcrnrlat, urcrnrlat, llcrnrlon, urcrnrlon, 해상도, 격자간격)
VIEWS = {
 "world":    (-58,  84, -178, 182, "l", 30),
 "kr_all":   (32.8, 38.8, 124.4, 130.4, "i", 1),
 "kr_sudo":  (36.80,38.00, 126.05,127.95, "h", 0.5),
 "kr_chung": (35.90,37.20, 125.95,128.70, "h", 0.5),
 "kr_gang":  (36.95,38.45, 127.00,129.55, "h", 0.5),
 "kr_honam": (34.15,36.20, 125.75,128.00, "h", 0.5),
}

def draw_base(ax, view):
    lat0, lat1, lon0, lon1, res, grid = VIEWS[view]
    m = Basemap(projection="mill" if view == "world" else "merc",
                llcrnrlat=lat0, urcrnrlat=lat1, llcrnrlon=lon0, urcrnrlon=lon1,
                resolution=res, ax=ax)
    m.drawmapboundary(fill_color=SEA, linewidth=0.6, color=INK)
    m.fillcontinents(color=LAND, lake_color=SEA)
    m.drawcoastlines(linewidth=0.35, color=INK)
    if view == "world":
        m.drawcountries(linewidth=0.25, color="#B9B2A4")
        m.drawparallels([-66.5,-23.5,0,23.5,66.5], linewidth=0.35, color="#C9C1B0",
                        dashes=[4,3], labels=[0,0,0,0])
    else:
        m.drawrivers(linewidth=0.4, color="#9FBECB")
        m.drawparallels([lat0+i*grid for i in range(int((lat1-lat0)/grid)+2)],
                        linewidth=0.25, color="#E2DDD0", dashes=[1,0], labels=[0,0,0,0])
        m.drawmeridians([lon0+i*grid for i in range(int((lon1-lon0)/grid)+2)],
                        linewidth=0.25, color="#E2DDD0", dashes=[1,0], labels=[0,0,0,0])
    return m

# 라벨을 점 주변 8방향으로 밀어 겹침을 피한다
OFFS = [(0,10),(0,-13),(12,4),(-12,4),(12,-9),(-12,-9),(0,22),(0,-25),
        (24,10),(-24,10),(24,-16),(-24,-16),(0,34),(0,-37)]

def place_labels(fig, ax, m, items, fs, ms):
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    placed = []
    order = sorted(items, key=lambda t: -t[1])          # 북쪽부터
    for name, lat, lon in order:
        x, y = m(lon, lat)
        ax.plot(x, y, "o", ms=4.2, mfc=VERM, mec="white", mew=0.9, zorder=5)
        best = None
        for dx, dy in OFFS:
            t = ax.annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                            ha="center", va="center", fontsize=fs, color=INK, zorder=6,
                            path_effects=[withStroke(linewidth=2.6, foreground=PAPER)])
            bb = t.get_window_extent(ren).expanded(1.06, 1.24)
            if not any(bb.overlaps(p) for p in placed):
                best = (t, bb, dx, dy); break
            t.remove()
        if best is None:
            dx, dy = 0, 46
            t = ax.annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                            ha="center", va="center", fontsize=fs, color=INK, zorder=6,
                            path_effects=[withStroke(linewidth=2.6, foreground=PAPER)])
            best = (t, t.get_window_extent(ren).expanded(1.06,1.24), dx, dy)
        t, bb, dx, dy = best
        placed.append(bb)
        if abs(dx) + abs(dy) > 16:                      # 멀리 밀린 라벨엔 지시선
            ax.annotate("", (x, y), textcoords="offset points", xytext=(dx*0.72, dy*0.72),
                        arrowprops=dict(arrowstyle="-", lw=0.5, color=FAINT,
                                        shrinkA=0, shrinkB=2), zorder=4)

def side_list(fig, items, x0, y0, w, unit_title, fs=6.6):
    """오른쪽에 이름 + 특징 목록. 칸을 넘치면 글자와 줄간격을 줄여 맞춘다."""
    entries = [(n, " · ".join(FEATS.get(n, []))) for n, _, _ in items]
    avail = y0 - 0.055

    def layout(cols, scale, measure_only):
        per = (len(entries) + cols - 1) // cols
        cw = w / cols
        f_name, f_body = (fs + 1.4) * scale, fs * scale
        l_name, l_body, l_gap = 0.0142 * scale, 0.0120 * scale, 0.0080 * scale
        worst = 0.0
        for c in range(cols):
            cx, y = x0 + c * cw, y0
            for name, body in entries[c * per:(c + 1) * per]:
                if not measure_only:
                    fig.text(cx, y, name, fontsize=f_name, weight="bold", color=INK, va="top")
                y -= l_name
                for ln in textwrap.wrap(body, width=max(18, int(cw * 152 / scale))) or [""]:
                    if not measure_only:
                        fig.text(cx, y, ln, fontsize=f_body, color=INK2, va="top")
                    y -= l_body
                y -= l_gap
            worst = max(worst, y0 - y)
        return worst

    for cols in (1, 2):
        need = layout(cols, 1.0, True)
        if need <= avail:
            layout(cols, 1.0, False); return
        scale = max(0.72, avail / need)
        if layout(cols, scale, True) <= avail:
            layout(cols, scale, False); return
    layout(2, 0.72, False)

def make_page(pdf, key, title, unit, view, fs, ms):
    items = (WORLD.get(key) or KOREA.get(key))
    fig = plt.figure(figsize=(11.69, 8.27))          # A4 가로
    fig.patch.set_facecolor(PAPER)
    # 머리글
    fig.text(0.045, 0.955, unit, fontsize=9.5, color=VERM, family="monospace", va="center")
    fig.text(0.085, 0.952, title, fontsize=19, weight="bold", color=INK, va="center")
    fig.text(0.955, 0.953, f"{len(items)}곳", fontsize=9, color=FAINT, ha="right", va="center")
    fig.add_artist(plt.Line2D([0.045,0.955],[0.928,0.928], color=INK, lw=1.3))
    fig.add_artist(plt.Line2D([0.045,0.955],[0.9235,0.9235], color=INK, lw=0.5))

    lat0, lat1, lon0, lon1, res, _ = VIEWS[view]
    probe = Basemap(projection="mill" if view == "world" else "merc",
                    llcrnrlat=lat0, urcrnrlat=lat1, llcrnrlon=lon0, urcrnrlon=lon1,
                    resolution=None)                      # 자료를 읽지 않아 즉시 끝난다
    band_y, band_h = 0.055, 0.85
    # 세로를 먼저 채우고, 너무 넓어지면 폭으로 제한한다 (오른쪽 목록 자리 확보)
    wide = min(0.62, band_h * (8.27 / 11.69) / probe.aspect)
    h = min(band_h, wide * (11.69 / 8.27) * probe.aspect)
    ax = fig.add_axes([0.045, band_y + (band_h - h) / 2, wide, h])
    ax.set_facecolor(SEA)
    m = draw_base(ax, view)
    place_labels(fig, ax, m, items, fs, ms)

    sx = 0.045 + wide + 0.035
    side_list(fig, items, sx, 0.885, 0.955 - sx, unit)
    fig.text(0.045, 0.022, "지도: Natural Earth · GSHHG (public domain)  |  2026 지역이해 암기",
             fontsize=6.4, color=FAINT)
    pdf.savefig(fig, facecolor=PAPER)
    plt.close(fig)

def main():
    out = os.path.join(ROOT, "docs", "지역이해-정답지도.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with PdfPages(out) as pdf:
        for key, title, unit, view, fs, ms in PAGES:
            make_page(pdf, key, title, unit, view, fs, ms)
            print(f"  {unit:9s} {title}")
        d = pdf.infodict()
        d["Title"] = "2026 지역이해 정답 지도"
        d["Subject"] = "학습지 항목 131곳을 지도 위에 표시한 정답본"
    print(f"\n{os.path.relpath(out, ROOT)}  {os.path.getsize(out)//1024}KB")

if __name__ == "__main__":
    main()

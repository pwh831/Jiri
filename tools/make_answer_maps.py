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
# 지명 구분용 4색. 종이(#FBF9F4) 위 대비 3:1 이상, 전 조합 정상시야 ΔE 15 이상.
# 색맹 조합(초록↔주황 ΔE 6.1)은 이름표가 항상 함께 붙어 있어 색만으로 구분하지 않는다.
LABEL_COLORS = ["#1E6FC4", "#C4551E", "#1B8A3E", "#B03070"]

# ── 학습지 특징 불러오기 ──────────────────────────────────────
def load_features():
    src = open(os.path.join(ROOT, "data", "items.js"), encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'name:"([^"]+)", aliases:\[[^\]]*\],?\s*(?:marker:\{[^}]*\},)?\s*\n?\s*features:\[(.*?)\]\s*\}', src, re.S):
        out[m.group(1)] = re.findall(r'"([^"]+)"', m.group(2))
    return out
FEATS = load_features()

# ── 국내 행정 경계 (통계청 SGIS 2018 기반, tools/fetch_boundaries.py 로 생성) ──
def load_geo(fn):
    p = os.path.join(ROOT, "data", "geo", fn)
    if not os.path.exists(p):
        print(f"  경고: {fn} 없음 — tools/fetch_boundaries.py 를 먼저 실행하세요")
        return []
    g = json.load(open(p, encoding="utf-8"))
    out = []
    for f in g["features"]:
        gm = f["geometry"]
        polys = gm["coordinates"] if gm["type"] == "MultiPolygon" else [gm["coordinates"]]
        out.append((f["properties"]["name"], polys))
    return out
SIDO, SIGUNGU = load_geo("sido.json"), load_geo("sigungu.json")

def draw_admin(ax, m, view):
    """시·군·구는 가는 선, 시·도는 굵은 선. 화면에 걸치는 것만 그린다."""
    lat0, lat1, lon0, lon1, _, _ = VIEWS[view]
    pad = 0.4
    def visible(ring):
        xs = [c[0] for c in ring]; ys = [c[1] for c in ring]
        return not (max(xs) < lon0-pad or min(xs) > lon1+pad or
                    max(ys) < lat0-pad or min(ys) > lat1+pad)
    for src, lw, ec, fc, z in ((SIGUNGU, 0.42, "#A69C8B", LAND, 1),
                               (SIDO,    1.00, "#4A443B", "none", 2)):
        for _, polys in src:
            for poly in polys:
                ring = poly[0]
                if len(ring) < 4 or not visible(ring):
                    continue
                xs, ys = m([c[0] for c in ring], [c[1] for c in ring])
                ax.fill(xs, ys, facecolor=fc, edgecolor=ec, linewidth=lw,
                        zorder=z, closed=True)

# ── 페이지 정의 ──────────────────────────────────────────────
# (지역키, 큰제목, 단원, 지도설정, 글자크기, 점크기)
# 쪽 하단에 덧붙일 학습지 본문 (특징표에 들어가지 않는 것)
NOTES = {
 "lakestrait": ("대륙의 경계 (25쪽)",
   "아시아 ↔ 아프리카  아덴만 · 홍해 · 수에즈 지협          "
   "아시아 ↔ 유럽  보스포루스 해협 · 캅카스 산맥 · 우랄 산맥\n"
   "북아메리카 ↔ 남아메리카  파나마 지협                     "
   "유럽 ↔ 아프리카  지브롤터 해협"),
}

PAGES = [
 ("peninsula",  "세계의 주요 반도",        "010", "world",       7.6, 22),
 ("island",     "세계의 주요 섬",          "010", "world",       7.6, 22),
 ("sea",        "세계의 주요 바다와 만",   "011", "world",       7.6, 22),
 ("lakestrait", "세계의 호수·해협과 오대양","009 · 011","world",  8.5, 22),
 ("sido",       "우리나라 17개 시·도",     "001", "kr_all",      8.4, 26),
 ("sudogwon",   "수도권",                  "002", "kr_sudo",     8.4, 26),
 ("chungcheong","충청 지방",               "003", "kr_chung",    8.4, 26),
 ("gangwon",    "강원 지방",               "004", "kr_gang",     8.4, 26),
 ("honam",      "호남 지방",               "005", "kr_honam",    7.9, 26),
]
# 지도 범위: (llcrnrlat, urcrnrlat, llcrnrlon, urcrnrlon, 해상도, 격자간격)
VIEWS = {
 "world":    (-58,  84, -178, 182, "l", 30),
 "kr_all":   (32.8, 38.8, 124.4, 130.4, "i", 1),
 "kr_sudo":  (36.78,38.02, 125.95,128.00, "h", 0.5),
 "kr_chung": (35.90,37.20, 125.95,128.70, "h", 0.5),
 "kr_gang":  (36.92,38.48, 126.90,129.65, "h", 0.5),
 "kr_honam": (34.15,36.20, 125.70,128.20, "h", 0.5),
}

def draw_base(ax, view):
    lat0, lat1, lon0, lon1, res, grid = VIEWS[view]
    m = Basemap(projection="mill" if view == "world" else "merc",
                llcrnrlat=lat0, urcrnrlat=lat1, llcrnrlon=lon0, urcrnrlon=lon1,
                resolution=res, ax=ax)
    m.drawmapboundary(fill_color=SEA, linewidth=0.6, color=INK)
    if view == "world":
        m.fillcontinents(color=LAND, lake_color=SEA)
        m.drawcoastlines(linewidth=0.35, color=INK)
    if view == "world":
        m.drawcountries(linewidth=0.25, color="#B9B2A4")
        m.drawparallels([-66.5,-23.5,0,23.5,66.5], linewidth=0.35, color="#C9C1B0",
                        dashes=[4,3], labels=[0,0,0,0])
    else:
        draw_admin(ax, m, view)                     # 시·군·구 + 시·도 경계
        m.drawcoastlines(linewidth=0.40, color="#6E655A", zorder=3)
        m.drawrivers(linewidth=0.4, color="#9FBECB", zorder=3)
        m.drawparallels([lat0+i*grid for i in range(int((lat1-lat0)/grid)+2)],
                        linewidth=0.25, color="#E2DDD0", dashes=[1,0], labels=[0,0,0,0])
        m.drawmeridians([lon0+i*grid for i in range(int((lon1-lon0)/grid)+2)],
                        linewidth=0.25, color="#E2DDD0", dashes=[1,0], labels=[0,0,0,0])
    return m

# 라벨을 점 주변 고리 모양으로 넓혀가며 겹치지 않는 자리를 찾는다
import math
def _candidates():
    out = [(0, 11), (0, -13)]
    for r in (13, 20, 28, 38, 50, 64, 80):
        for k in range(12):
            a = math.radians(90 + k * (360 / 12) * (1 if k % 2 else -1))
            out.append((round(r * math.cos(a) * 1.35), round(r * math.sin(a))))
    return out
OFFS = _candidates()

def place_labels(fig, ax, m, items, fs, ms):
    """이름표를 겹치지 않게 놓고, 가까운 것끼리 다른 색을 준다.
    점·이름표·지시선이 같은 색이라 어느 이름이 어느 점인지 바로 보인다."""
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    drawn, placed = [], []
    for name, lat, lon in sorted(items, key=lambda t: -t[1]):
        x, y = m(lon, lat)
        dot, = ax.plot(x, y, "o", ms=4.4, mfc=INK, mec="white", mew=0.9, zorder=6)
        chosen = None
        for dx, dy in OFFS:
            t = ax.annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                            ha="center", va="center", fontsize=fs, zorder=7,
                            path_effects=[withStroke(linewidth=2.8, foreground=PAPER)])
            bb = t.get_window_extent(ren).expanded(1.05, 1.30)
            if not any(bb.overlaps(q) for q in placed):
                chosen = (t, bb, dx, dy); break
            t.remove()
        if chosen is None:
            dx, dy = 0, 96
            t = ax.annotate(name, (x, y), textcoords="offset points", xytext=(dx, dy),
                            ha="center", va="center", fontsize=fs, zorder=7,
                            path_effects=[withStroke(linewidth=2.8, foreground=PAPER)])
            chosen = (t, t.get_window_extent(ren).expanded(1.05, 1.30), dx, dy)
        t, bb, dx, dy = chosen
        placed.append(bb)
        lead = None
        if abs(dx) + abs(dy) > 15:
            lead = ax.annotate("", (x, y), textcoords="offset points",
                               xytext=(dx * 0.70, dy * 0.70),
                               arrowprops=dict(arrowstyle="-", lw=0.7, shrinkA=0, shrinkB=2),
                               zorder=5)
        px, py = ax.transData.transform((x, y))
        drawn.append(dict(name=name, dot=dot, text=t, lead=lead, bb=bb, px=px, py=py))

    # 가까운 것끼리 충돌로 보고 4색으로 칠한다 (이웃끼리는 반드시 다른 색)
    R = 110.0
    n = len(drawn)
    adj = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = drawn[i], drawn[j]
            near = ((a["px"] - b["px"]) ** 2 + (a["py"] - b["py"]) ** 2) ** 0.5 < R
            if near or a["bb"].expanded(1.9, 2.4).overlaps(b["bb"]):
                adj[i].add(j); adj[j].add(i)
    color_of = [None] * n
    used = [0] * len(LABEL_COLORS)
    for i in sorted(range(n), key=lambda k: -len(adj[k])):        # 이웃 많은 것부터
        taken = {color_of[j] for j in adj[i] if color_of[j] is not None}
        free = [c for c in range(len(LABEL_COLORS)) if c not in taken]
        pick = min(free, key=lambda c: used[c]) if free else min(
            range(len(LABEL_COLORS)),
            key=lambda c: (sum(1 for j in adj[i] if color_of[j] == c), used[c]))
        color_of[i] = pick; used[pick] += 1

    out = {}
    for i, d in enumerate(drawn):
        col = LABEL_COLORS[color_of[i]]
        d["dot"].set_markerfacecolor(col)
        d["text"].set_color(col)
        if d["lead"] is not None:
            d["lead"].arrow_patch.set_color(col)
        out[d["name"]] = col
    return out

def bottom_list(fig, items, x0, y_top, w, y_bottom, fs=6.9, colors=None):
    """쪽 하단에 이름 + 특징 목록. 칸 수와 글자 크기를 자동으로 맞춘다."""
    entries = [(n, " · ".join(FEATS.get(n, []))) for n, _, _ in items]
    avail = y_top - y_bottom

    def layout(cols, scale, measure_only):
        per = (len(entries) + cols - 1) // cols
        cw = w / cols
        gutter = 0.018
        f_name, f_body = (fs + 1.3) * scale, fs * scale
        l_name, l_body, l_gap = 0.0128 * scale, 0.0108 * scale, 0.0072 * scale
        wrap = max(16, int((cw - gutter - 0.011) * 118 / scale))
        worst = 0.0
        for c in range(cols):
            cx, y = x0 + c * cw, y_top
            for name, body in entries[c * per:(c + 1) * per]:
                if not measure_only:
                    col = (colors or {}).get(name)
                    if col:
                        fig.text(cx, y - 0.0026, "\u25cf", fontsize=f_name * 0.62,
                                 color=col, va="top")
                    fig.text(cx + 0.011, y, name, fontsize=f_name, weight="bold",
                             color=INK, va="top")
                y -= l_name
                for ln in textwrap.wrap(body, width=wrap) or [""]:
                    if not measure_only:
                        fig.text(cx + 0.011, y, ln, fontsize=f_body, color=INK2, va="top")
                    y -= l_body
                y -= l_gap
            worst = max(worst, y_top - y)
        return worst

    for cols in (2, 3, 4):
        if layout(cols, 1.0, True) <= avail:
            layout(cols, 1.0, False); return
        scale = max(0.74, avail / layout(cols, 1.0, True))
        if layout(cols, scale, True) <= avail:
            layout(cols, scale, False); return
    layout(4, 0.74, False)

def make_page(pdf, key, title, unit, view, fs, ms):
    items = (WORLD.get(key) or KOREA.get(key))
    PW, PH = 8.27, 11.69                              # A4 세로
    fig = plt.figure(figsize=(PW, PH))
    fig.patch.set_facecolor(PAPER)

    # 머리글
    fig.text(0.045, 0.972, unit, fontsize=9.5, color=VERM, family="monospace", va="center")
    tx = 0.105 + (0.038 if len(unit) > 4 else 0)      # "009 · 011" 처럼 긴 단원 번호 자리 확보
    fig.text(tx, 0.9695, title, fontsize=19, weight="bold", color=INK, va="center")
    fig.text(0.955, 0.9705, f"{len(items)}곳", fontsize=9, color=FAINT, ha="right", va="center")
    fig.add_artist(plt.Line2D([0.045,0.955],[0.9555,0.9555], color=INK, lw=1.3))
    fig.add_artist(plt.Line2D([0.045,0.955],[0.9525,0.9525], color=INK, lw=0.5))

    # 지도 — 위쪽 띠를 세로로 먼저 채우고 넘치면 폭으로 제한
    lat0, lat1, lon0, lon1, res, _ = VIEWS[view]
    probe = Basemap(projection="mill" if view == "world" else "merc",
                    llcrnrlat=lat0, urcrnrlat=lat1, llcrnrlon=lon0, urcrnrlon=lon1,
                    resolution=None)
    top, max_h, max_w = 0.935, 0.505, 0.91
    wide = min(max_w, max_h * (PH / PW) / probe.aspect)
    h = wide * (PW / PH) * probe.aspect
    ax = fig.add_axes([0.045 + (max_w - wide) / 2, top - h, wide, h])
    ax.set_facecolor(SEA)
    m = draw_base(ax, view)
    colors = place_labels(fig, ax, m, items, fs, ms)

    # 구분선 + 하단 특징
    div = top - h - 0.024                              # 구분선을 지도 바로 아래에
    fig.add_artist(plt.Line2D([0.045,0.955],[div,div], color=RULE, lw=0.8))
    fig.text(0.045, div - 0.009, "지역별 특징", fontsize=8, weight="bold", color=INK2, va="top")
    fig.text(0.955, div - 0.009, "학습지 본문 기준 (각주 제외)", fontsize=6.6, color=FAINT,
             ha="right", va="top")
    note = NOTES.get(key)
    floor = 0.042
    if note:
        fig.add_artist(plt.Line2D([0.045,0.955],[0.104,0.104], color=RULE, lw=0.6))
        fig.text(0.045, 0.094, note[0], fontsize=7.2, weight="bold", color=INK2, va="top")
        y = 0.079
        for ln in note[1].split("\n"):
            fig.text(0.045, y, ln, fontsize=6.9, color=INK2, va="top")
            y -= 0.0125
        floor = 0.118
    bottom_list(fig, items, 0.045, div - 0.030, 0.91, floor, colors=colors)

    fig.text(0.045, 0.021, "지도: Natural Earth · GSHHG (public domain) · 국내 행정경계 통계청 SGIS  |  2026 지역이해 암기",
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

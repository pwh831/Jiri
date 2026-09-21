#!/usr/bin/env python3
"""시험 범위(학습지 1~11쪽, 23~34쪽)만 추린 요약 PDF를 만든다.

    python3 tools/make_summary.py            # docs/지역이해-요약.pdf
    python3 tools/make_summary.py --open x.pdf

data/items.js 에서 exam:false 가 아닌 단원만 뽑아 단원 → 갈래 → 항목 순으로 싣는다.
지도가 있는 갈래는 지도를 먼저 싣고 번호별 목록을 붙인다.
각주(notes)는 시험 범위가 아니라 넣지 않는다.

HTML 을 만들어 크로미움으로 인쇄한다. 글자가 벡터로 남아 굿노트에서
확대해도 깨지지 않고 검색도 된다.
"""
import argparse
import base64
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTDIR = "/usr/local/lib/python3.11/dist-packages/koreanize_matplotlib/fonts"
CHROME = "/opt/pw-browsers/chromium"

# 단원별 학습지 쪽
SHEET = {"001": "1~2쪽", "002": "3~5쪽", "003": "5~8쪽", "004": "9~11쪽",
         "009": "23~25쪽", "010": "26~28쪽", "011": "29~31쪽", "012": "32~34쪽"}

# 지도를 통째로 실을 갈래(같은 지도를 쓰는 갈래가 여럿이면 첫 갈래에만)
NOTE = {
    "river": "하천별 설명은 학습지 35쪽부터라 시험 범위 밖입니다. 이름과 위치만 외우면 됩니다.",
}


def dump_data():
    """node 로 items.js 를 읽어 JSON 으로 받는다(파싱을 두 번 구현하지 않기 위해)."""
    js = r'''
const fs=require("fs"),vm=require("vm");const ctx={};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],"utf8")+";globalThis._D={UNITS,CATS,MAPS,ITEMS,GROUPS};",ctx);
const D=ctx._D;
process.stdout.write(JSON.stringify({
  units: D.UNITS.filter(u=>u.exam!==false).map(u=>({
    no:u.no, title:u.title, area:u.area,
    cats: u.cats.map(k=>{
      const c=D.CATS.find(x=>x.key===k);
      const items=D.ITEMS.filter(i=>i.category===k);
      const map=items.find(i=>i.map);
      return {key:k, label:c.label, mapKey: map?map.map:null,
              items: items.map(i=>({num:i.num??null, name:i.name, features:i.features||[]}))};
    })
  })),
  maps: D.MAPS,
  groups: (typeof D.GROUPS==="undefined"?[]:D.GROUPS).map(g=>({
    label:g.label, why:g.why,
    members:g.members.map(id=>{const i=D.ITEMS.find(x=>x.id===id); return i?i.name:id;})})),
}));
'''
    p = os.path.join(ROOT, "tools", "_dump.js")
    open(p, "w", encoding="utf-8").write(js)
    try:
        out = subprocess.run(["node", p, os.path.join(ROOT, "data", "items.js")],
                             capture_output=True, text=True, check=True).stdout
    finally:
        os.remove(p)
    return json.loads(out)


def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def subset_font(path, text):
    """쓰는 글자만 남긴 woff2 를 만들어 data URI 로 돌려준다.

    나눔고딕 원본은 4.7MB 인 데다 길이가 0인 TSI 표(VTT 힌팅 찌꺼기)가 들어 있어
    크로미움의 폰트 검사기(OTS)가 통째로 거부한다("TSI3: zero-length table").
    부분집합을 뜨면 그 표들이 떨어져 나가면서 용량도 수십분의 일로 준다.
    (woff2 로 줄이면 더 작지만 brotli 가 없는 환경이 있어 ttf 로 둔다.)
    """
    from fontTools import subset as fsub

    opts = fsub.Options(desubroutinize=True, layout_features=["*"], notdef_outline=True)
    opts.drop_tables += ["TSI0", "TSI1", "TSI2", "TSI3", "TSI5"]
    font = fsub.load_font(path, opts)
    sub = fsub.Subsetter(options=opts)
    sub.populate(text=text)
    sub.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    font.close()
    return "data:font/ttf;base64," + base64.b64encode(buf.getvalue()).decode()


def font_face(name, file, weight, text):
    uri = subset_font(os.path.join(FONTDIR, file), text)
    return (f"@font-face{{font-family:'{name}';font-weight:{weight};font-style:normal;"
            f"src:url('{uri}') format('truetype')}}")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def all_text(data):
    """문서에 실제로 들어갈 글자를 모두 모은다(폰트 부분집합용)."""
    out = ["지역 이해 · 시험 범위 요약 2026학년도 2학기 학습지 본문만 추렸습니다 "
           "단원 항목 개 각주는 밖이라 뺐습니다 쪽 지방 행정 구역 대지역 명 설정 이유 "
           "0123456789~·()%°→ ·"]
    for u in data["units"]:
        out.append(u["no"] + u["title"] + SHEET.get(u["no"], ""))
        for c in u["cats"]:
            out.append(c["label"] + NOTE.get(c["key"], ""))
            for it in c["items"]:
                out.append(it["name"] + "".join(it["features"]) + str(it["num"] or ""))
    out.append("속성으로 묶어 보기 같은 을 가진 곳끼리 모았습니다 세로로 외우면 짧아집니다 곳")
    for g in data.get("groups", []):
        out.append(g["label"] + g["why"] + "".join(g["members"]))
    return "".join(out)


def build_html(data):
    maps = data["maps"]
    text = all_text(data)
    fonts = "".join([
        font_face("Nanum", "NanumGothic.ttf", 400, text),
        font_face("Nanum", "NanumGothicBold.ttf", 700, text),
        font_face("Nanum", "NanumGothicExtraBold.ttf", 800, text),
    ])

    css = """
    :root{--ink:#1B1713;--ink2:#4A443B;--faint:#8A8272;--rule:#D9D2C4;--rule2:#BFB7A6;
          --verm:#A8491F;--water:#2E5568;--tint:#F4F1E9}
    *{box-sizing:border-box}
    @page{size:A4;margin:12mm 13mm 11mm}
    body{margin:0;font-family:'Nanum',sans-serif;color:var(--ink);
         font-size:8.6pt;line-height:1.45;-webkit-font-smoothing:antialiased}

    /* 표지 블록 */
    .cover{border-top:2.5pt solid var(--ink);border-bottom:.8pt solid var(--ink);
           padding:9pt 0 10pt;margin-bottom:13pt}
    .cover h1{margin:0 0 3pt;font-size:19pt;font-weight:800;letter-spacing:-.4pt}
    .cover .sub{font-size:9pt;color:var(--ink2)}
    .cover .scope{margin-top:8pt;display:flex;gap:7pt;flex-wrap:wrap}
    .cover .scope span{border:.6pt solid var(--rule2);border-radius:2pt;padding:2.5pt 7pt;
           font-size:8pt;color:var(--ink2);background:var(--tint)}
    .cover .scope b{color:var(--verm);font-weight:700}

    /* 단원 */
    .unit{break-inside:auto}
    .unit + .unit{margin-top:15pt}
    .uhead{display:flex;align-items:baseline;gap:8pt;border-bottom:1.4pt solid var(--ink);
           padding-bottom:4pt;margin-bottom:9pt;break-after:avoid}
    .uno{font-size:8.5pt;font-weight:800;color:#fff;background:var(--ink);
         padding:2pt 6pt;border-radius:2pt;letter-spacing:.3pt}
    .utitle{font-size:13pt;font-weight:800;letter-spacing:-.3pt}
    .upage{margin-left:auto;font-size:7.8pt;color:var(--faint)}

    /* 구분점: 특징과 특징 사이 */
    s{text-decoration:none;color:var(--rule2);padding:0 2.5pt}

    /* 갈래 */
    .cat{margin-bottom:10pt}
    .clabel{display:flex;align-items:center;gap:6pt;margin-bottom:5pt;break-after:avoid}
    .clabel b{font-size:9.2pt;font-weight:700;color:var(--water)}
    .clabel i{flex:1;height:.6pt;background:var(--rule);display:block}
    .clabel em{font-style:normal;font-size:7.5pt;color:var(--faint)}
    .note{font-size:7.6pt;color:var(--verm);margin:-2pt 0 5pt;padding-left:1pt}

    /* 지도 */
    .map{border:.7pt solid var(--rule2);padding:4pt;margin-bottom:7pt;background:#fff;
         break-inside:avoid}
    .map img{display:block;width:100%}

    /* 항목 목록 */
    .list{column-count:2;column-gap:11pt;column-rule:.5pt solid var(--rule)}
    .list.one{column-count:1}
    .row{break-inside:avoid;margin-bottom:4.5pt;padding-left:14pt;text-indent:-14pt}
    .row .n{display:inline-block;min-width:11pt;font-size:7.6pt;font-weight:700;
            color:var(--verm);text-indent:0}
    .row .nm{font-weight:700}
    .row .ft{color:var(--ink2)}
    .row .ft s{text-decoration:none;color:var(--rule2);padding:0 2pt}

    /* 이름만 있는 목록(하천) */
    .names{column-count:4;column-gap:9pt;font-size:8.4pt}
    .names div{break-inside:avoid;margin-bottom:2.5pt}
    .names .n{font-weight:700;color:var(--verm);font-size:7.6pt;margin-right:3pt}

    /* 전통 구분 표 */
    table{width:100%;border-collapse:collapse;font-size:8.2pt}
    tr{break-inside:avoid}
    thead{display:table-header-group}
    th,td{border:.5pt solid var(--rule2);padding:3pt 5pt;text-align:left;vertical-align:top}
    th{background:var(--tint);font-weight:700;font-size:7.8pt;color:var(--ink2)}
    td.k{font-weight:700;white-space:nowrap}
    .trad td:nth-child(2),.trad td:nth-child(3){white-space:nowrap}
    .trad col.a{width:52pt}.trad col.b{width:92pt}.trad col.c{width:92pt}

    /* 속성 묶음 */
    .grp{break-inside:avoid;margin-bottom:7pt;padding-left:8pt;border-left:1.6pt solid var(--verm)}
    .grp .gl{font-weight:700;font-size:9pt}
    .grp .gm{font-weight:700;color:var(--water);margin:1.5pt 0 1pt}
    .grp .gw{font-size:7.9pt;color:var(--ink2);line-height:1.4}

    /* 개념 표 */
    .defs{width:100%;border-collapse:collapse;font-size:8.4pt}
    .defs td{border:0;border-bottom:.5pt solid var(--rule);padding:3.5pt 0;vertical-align:top}
    .defs td.k{width:74pt;font-weight:700;padding-right:7pt;white-space:nowrap}
    """

    def row(it, show_num=True):
        n = f'<span class="n">{it["num"]}</span>' if (show_num and it["num"]) else ""
        ft = "<s>·</s>".join(esc(f) for f in it["features"])
        ft = f' <span class="ft">{ft}</span>' if ft else ""
        return f'<div class="row">{n}<span class="nm">{esc(it["name"])}</span>{ft}</div>'

    out = []
    for u in data["units"]:
        out.append('<section class="unit">')
        out.append(f'<div class="uhead"><span class="uno">{u["no"]}</span>'
                   f'<span class="utitle">{esc(u["title"])}</span>'
                   f'<span class="upage">학습지 {SHEET.get(u["no"], "")}</span></div>')
        drawn = set()
        for c in u["cats"]:
            items = c["items"]
            out.append('<div class="cat">')
            out.append(f'<div class="clabel"><b>{esc(c["label"])}</b><i></i>'
                       f'<em>{len(items)}항목</em></div>')
            if c["key"] in NOTE:
                out.append(f'<div class="note">{esc(NOTE[c["key"]])}</div>')
            mk = c["mapKey"]
            if mk and mk not in drawn:
                drawn.add(mk)
                path = os.path.join(ROOT, maps[mk]["image"])
                mime = "image/jpeg" if path.endswith(".jpg") else "image/png"
                out.append(f'<div class="map"><img src="{b64(path, mime)}"></div>')

            if c["key"] == "tradition":
                out.append('<table class="trad"><col class="a"><col class="b"><col class="c"><col>'
                           '<thead><tr><th>지방</th><th>행정 구역</th><th>대지역</th>'
                           '<th>지역명 설정 이유</th></tr></thead>')
                for it in items:
                    f = it["features"] + ["", "", ""]
                    g = lambda s: s.replace("행정 구역으로는 ", "").replace("대지역 구분으로는 ", "")
                    out.append(f'<tr><td class="k">{esc(it["name"])}</td><td>{esc(g(f[0]))}</td>'
                               f'<td>{esc(g(f[1]))}</td><td>{esc(" · ".join(f[2:]).strip(" ·"))}</td></tr>')
                out.append("</table>")
            elif c["key"] == "term":
                out.append('<table class="defs">')
                for it in items:
                    out.append(f'<tr><td class="k">{esc(it["name"])}</td>'
                               f'<td>{"<s>·</s>".join(esc(x) for x in it["features"])}</td></tr>')
                out.append("</table>")
            elif all(not it["features"] for it in items):
                out.append('<div class="names">')
                for it in items:
                    out.append(f'<div><span class="n">{it["num"]}</span>{esc(it["name"])}</div>')
                out.append("</div>")
            else:
                one = max((len(" ".join(i["features"])) for i in items), default=0) > 110
                out.append(f'<div class="list{" one" if one else ""}">')
                out.extend(row(it) for it in items)
                out.append("</div>")
            out.append("</div>")
        out.append("</section>")

    groups = data.get("groups", [])
    if groups:
        out.append('<section class="unit" style="break-before:page">')
        out.append('<div class="uhead"><span class="uno">부록</span>'
                   '<span class="utitle">속성으로 묶어 보기</span>'
                   f'<span class="upage">{len(groups)}묶음</span></div>')
        out.append('<div class="note" style="margin-bottom:8pt">'
                   '지역마다 특징을 붙여 외우면 "이 특징을 가진 곳이 또 어디냐"를 못 맞힙니다. '
                   '기출이 묻는 방향이 대체로 그쪽이라, 같은 속성을 가진 곳끼리 모았습니다.</div>')
        out.append('<div class="list">')
        for g in groups:
            out.append(f'<div class="grp"><div class="gl">{esc(g["label"])} '
                       f'<span style="color:var(--faint);font-weight:400">{len(g["members"])}곳</span></div>'
                       f'<div class="gm">{esc(" · ".join(g["members"]))}</div>'
                       f'<div class="gw">{esc(g["why"])}</div></div>')
        out.append("</div></section>")

    n_items = sum(len(c["items"]) for u in data["units"] for c in u["cats"])
    cover = (f'<div class="cover"><h1>지역 이해 · 시험 범위 요약</h1>'
             f'<div class="sub">2026학년도 2학기 · 학습지 본문만 추렸습니다</div>'
             f'<div class="scope"><span>범위 <b>학습지 1~11쪽 · 23~34쪽</b></span>'
             f'<span>단원 <b>{len(data["units"])}개</b></span>'
             f'<span>항목 <b>{n_items}개</b></span>'
             f'<span>각주는 범위 밖이라 뺐습니다</span></div></div>')

    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{fonts}{css}</style></head><body>{cover}{"".join(out)}</body></html>')


def render_pdf(html_path, out):
    """크로미움 헤드리스로 인쇄한다. playwright 없이 브라우저 실행 파일만 쓴다."""
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=20000",
           f"--print-to-pdf={out}", "file://" + html_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.exists(out):
        sys.exit("PDF 렌더 실패:\n" + r.stdout + r.stderr)


def stamp_footer(pdf_path, label):
    """쪽 번호와 꼬리말을 찍는다(크로미움 기본 꼬리말은 URL·날짜가 박혀 쓸 수 없다)."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    font = os.path.join(FONTDIR, "NanumGothic.ttf")
    for n, page in enumerate(doc, 1):
        w, h = page.rect.width, page.rect.height
        y = h - 20
        page.insert_text((37, y), label, fontfile=font, fontname="NG",
                         fontsize=7, color=(0.54, 0.51, 0.45))
        num = str(n)
        page.insert_text((w - 37 - len(num) * 4.2, y), num, fontfile=font, fontname="NG",
                         fontsize=7, color=(0.54, 0.51, 0.45))
    # 크로미움이 글꼴을 통으로 심어 파일이 두 배가 넘게 커진다. 다시 저장하며 정리한다.
    try:
        doc.subset_fonts(verbose=False)
    except Exception:
        pass
    tmp = pdf_path + ".tmp"
    doc.save(tmp, garbage=4, deflate=True, clean=True)
    doc.close()
    os.replace(tmp, pdf_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "지역이해-요약.pdf"))
    a = ap.parse_args()

    data = dump_data()
    html = build_html(data)
    tmp = os.path.join(ROOT, "docs", "_summary.html")
    open(tmp, "w", encoding="utf-8").write(html)
    try:
        render_pdf(tmp, a.out)
    finally:
        os.remove(tmp)
    stamp_footer(a.out, "2026 지역 이해 · 시험 범위 요약 (학습지 1~11쪽, 23~34쪽)")

    import pymupdf
    pages = pymupdf.open(a.out).page_count
    kb = os.path.getsize(a.out) // 1024
    n = sum(len(c["items"]) for u in data["units"] for c in u["cats"])
    print(f"{os.path.relpath(a.out, ROOT)}  {pages}쪽  {kb}KB  ·  "
          f"{len(data['units'])}단원 {n}항목")


if __name__ == "__main__":
    main()

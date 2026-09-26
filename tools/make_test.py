#!/usr/bin/env python3
"""학습지 전수 점검 시험지를 만든다 — PDF 와 웹이 같은 문항을 쓴다.

    python3 tools/make_test.py                    # data/sheet.js + docs/지역이해-점검시험.pdf
    python3 tools/make_test.py --src 원본.pdf     # 원본에서 빈칸 정답을 다시 뽑은 뒤 생성

시험 범위(학습지 1~11쪽, 23~34쪽, 각주 포함)의 모든 문장을 한 번씩 싣는다.
항목 하나가 카드 하나다. 카드마다
  · 이름 칸 — 지도 번호나 설명을 보고 지명·용어를 쓴다(개관 주제는 이름을 보여 준다)
  · 빈칸   — 문장 속 핵심어를 비운다
빈칸은 **선생님이 학습지에서 비워 둔 자리**를 먼저 쓴다. 원본 PDF 에는 그 답이
흰 글씨로 들어 있어(인쇄하면 안 보인다) 그대로 뽑을 수 있다 → data/blanks.json.
학습지 빈칸이 걸리지 않는 문장은 숫자를 비우고, 그것도 없으면 문장을 단서로만 둔다.

결과 data/sheet.js 는 웹(index.html)이 읽고, 같은 내용으로 PDF 를 인쇄한다.
"""
import argparse, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_summary import b64, font_face, esc, render_pdf, stamp_footer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLANKS = os.path.join(ROOT, "data", "blanks.json")
OUTJS = os.path.join(ROOT, "data", "sheet.js")

# 원본 PDF 쪽 → 학습지 쪽. 원본은 12~22쪽 사이가 줄어 있어 20쪽부터 +3 이 된다.
PDF_PAGES = list(range(1, 12)) + list(range(20, 32))
def sheet_page(pdf_page):
    return pdf_page if pdf_page <= 11 else pdf_page + 3

# 단원 → 학습지 쪽
UNIT_PAGES = {"001": range(1, 3), "002": range(3, 6), "003": range(5, 9), "004": range(9, 12),
              "009": range(23, 26), "010": range(26, 29), "011": range(29, 32), "012": range(32, 35)}
UNIT_LABEL = {"001": "1~2쪽", "002": "3~5쪽", "003": "5~8쪽", "004": "9~11쪽",
              "009": "23~25쪽", "010": "26~28쪽", "011": "29~31쪽", "012": "32~34쪽"}

MAXBLANK = 3          # 한 문장에 비우는 최대 칸 수
MASK = "○○"           # 이름 칸이 있는 카드에서 본문에 나온 이름을 가리는 표시


# ── 원본에서 빈칸 정답 뽑기 ─────────────────────────────────────
def extract_blanks(src):
    import pymupdf
    doc = pymupdf.open(src)
    out, text = {}, {}
    for p in PDF_PAGES:
        text[str(sheet_page(p))] = "".join(doc[p - 1].get_text().split())
        spans = []
        for b in doc[p - 1].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["color"] == 0xFFFFFF and s["text"].strip():
                        spans.append(s["text"].strip())
        out[str(sheet_page(p))] = spans
    data = {"blanks": out, "text": text}
    json.dump(data, open(BLANKS, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return data


# ── 데이터 ─────────────────────────────────────────────────────
def dump_items():
    js = r'''
const fs=require("fs"),vm=require("vm");const ctx={};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],"utf8")+";globalThis._D={UNITS,CATS,MAPS,ITEMS};",ctx);
const D=ctx._D, cin=k=>{const c=D.CATS.find(x=>x.key===k);return c&&c.exam!==false;};
process.stdout.write(JSON.stringify({
  maps: D.MAPS,
  units: D.UNITS.filter(u=>u.exam!==false).map(u=>({no:u.no,title:u.title,
    cats:u.cats.filter(cin).map(k=>({key:k,label:D.CATS.find(c=>c.key===k).label,
      items:D.ITEMS.filter(i=>i.category===k).map(i=>({id:i.id,name:i.name,aliases:i.aliases||[],
        map:i.map||null,num:i.num??null,marker:i.marker||null,features:i.features||[],notes:i.notes||[]}))}))}))
}));'''
    p = os.path.join(ROOT, "tools", "_dump_test.js")
    open(p, "w", encoding="utf-8").write(js)
    try:
        out = subprocess.run(["node", p, os.path.join(ROOT, "data", "items.js")],
                             capture_output=True, text=True, check=True).stdout
    finally:
        os.remove(p)
    return json.loads(out)


# ── 빈칸 고르기 ───────────────────────────────────────────────
HANGUL = re.compile(r"[가-힣]")
NOTE_TAG = re.compile(r"\s*\((각주\s*\d+(?:[·,]\s*\d+)*)\)\s*$")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:만\s*명|만\s*km²|만|억\s*년|억|천|%p|%|km²|km|m|°C|°|년대|년|해리|개국|개|배|명|위)?")


def cand_list(spans):
    """한 쪽의 빈칸 정답을 {후보 문자열: 학습지에 나온 횟수} 로 바꾼다."""
    raw = list(spans)
    # 줄바꿈으로 쪼개진 답('수도권 공' + '장 총량제')을 이어 붙인 것도 후보로 둔다.
    # 이어 붙인 후보는 JOINED 에 적어 두고, 낱말 한가운데서 시작하면 쓰지 않는다.
    for a, b in zip(spans, spans[1:]):
        for j in (a + b, a + " " + b):
            raw.append(j)
            JOINED.add(j.strip(" ()•·."))
    out = {}
    for s in raw:
        for piece in re.split(r"[,›>]", s):
            piece = piece.strip(" •·.\u00a0")
            if piece.count("(") > piece.count(")"):
                piece = piece.lstrip("( ") if piece.startswith("(") else piece + ")"
            if piece.count(")") > piece.count("("):
                piece = piece.rstrip(") ")
            core = re.sub(r"\s", "", piece)
            toks = piece.split()
            if len(toks) > 1 and (len(toks[-1]) == 1 or len(toks[0]) == 1) and piece not in JOINED:
                continue          # '수도권 공' 처럼 줄 끝에서 잘린 조각
            if 2 <= len(core) <= 16 and not core.isdigit() or (core.isdigit() and len(core) >= 2):
                out[piece] = out.get(piece, 0) + 1
    return out


JOINED = set()
PARTICLE = set("은는이가을를의에와과도로으만및")


def trigrams(s):
    s = re.sub(r"\s", "", s)
    return {s[i:i + 3] for i in range(len(s) - 2)}


def page_of(line, texts):
    """문장이 학습지 몇 쪽에 있는지 — 세 글자 조각이 가장 많이 겹치는 쪽."""
    g = trigrams(line)
    if not g:
        return None
    best, score = None, 0
    for pg, t in texts.items():
        n = sum(1 for x in g if x in t)
        if n > score:
            best, score = pg, n
    return best if score >= max(2, len(g) * 0.3) else None


def flex(s):
    """띄어쓰기가 달라도 맞도록 글자 사이에 \\s* 를 넣은 정규식."""
    chars = [c for c in s if not c.isspace()]
    return r"\s*".join(re.escape(c) for c in chars)


def choose(text, cands, used, names=()):
    """문장에서 비울 구간 [(시작, 끝)] 을 고른다.

    cands 는 그 문장이 있는 쪽의 빈칸 정답과 횟수. 학습지에 한 번 나온 빈칸을
    엉뚱한 문장에서까지 비우지 않도록 쪽마다 (횟수 × 2) 번까지만 쓴다."""
    taken = []
    def free(a, b):
        return all(b <= x or a >= y for x, y in taken)
    for c in sorted(cands, key=lambda s: -len(re.sub(r"\s", "", s))):
        if len(taken) >= MAXBLANK:
            break
        if used.get(c, 0) >= cands[c] * (1 if len(re.sub(r"\s", "", c)) <= 2 else 2):
            continue
        core = re.sub(r"\s", "", c)
        for m in re.finditer(flex(c), text):
            a, b = m.span()
            if MASK in text[a:b]:
                continue
            if c in JOINED and a > 0 and HANGUL.match(text[a - 1]):
                continue          # '통해 페르시아만' 에 걸린 '해 페르시아만'
            # '몽블' 처럼 낱말이 잘린 빈칸은 낱말 끝까지 늘린다(조사는 남긴다)
            ext = 0
            while (b + ext < len(text) and ext < 4 and HANGUL.match(text[b + ext])
                   and HANGUL.match(text[b - 1]) and text[b + ext] not in PARTICLE):
                ext += 1
            b += ext
            # 두 글자짜리가 낱말 한가운데 걸리면(예: '기업'도시 안의 '기업'도 아닌 '중기업') 건너뛴다
            if len(core) < 3 and a > 0 and HANGUL.match(text[a - 1]) and not text[a - 1] in "의과와는은이가을를":
                continue
            if free(a, b):
                taken.append((a, b))
                used[c] = used.get(c, 0) + 1
                break
    if not taken and names:
        for n in names:
            m = re.search(flex(n), text)
            if m and MASK not in m.group(0):
                taken.append(m.span())
                break
    if not taken:
        for m in NUM.finditer(text):
            a, b = m.span()
            tok = text[a:b].strip()
            b = a + len(tok)
            digits = re.sub(r"\D", "", tok)
            if tok == digits and len(digits) < 2:
                continue
            if len(tok) < 2:
                continue
            taken.append((a, b))
            break
    return sorted(taken)


def masks_for(it):
    names = [it["name"]] + it["aliases"]
    out = set()
    for n in names:
        n = re.sub(r"\(.*?\)", "", n).strip()
        if len(n) >= 2:
            out.add(n)
        for suf in ("특별자치도", "특별자치시", "광역시", "특별시", " 지방", "시", "군", "도"):
            if n.endswith(suf) and len(n) - len(suf) >= 2 and not n.endswith("반도"):
                out.add(n[: -len(suf)].strip())
                break
    return sorted(out, key=len, reverse=True)


def mask(text, it):
    for n in masks_for(it):
        text = re.sub(flex(n), MASK, text)
    return text


def shows_name(cat):
    return cat.endswith("_ov")


def build(data, blanks):
    texts, spans = blanks["text"], blanks["blanks"]
    cands_of = {pg: cand_list(sp) for pg, sp in spans.items()}
    # 학습지 빈칸이 안 걸리는 문장은 범위 안 다른 항목의 이름(지명·용어)을 비운다
    allnames = set()
    for u in data["units"]:
        for c in u["cats"]:
            if shows_name(c["key"]):
                continue
            for it in c["items"]:
                for n in [it["name"]] + it["aliases"]:
                    n = re.sub(r"\(.*?\)", "", n).strip()
                    if len(re.sub(r"\s", "", n)) >= 3:
                        allnames.add(n)
    allnames = sorted(allnames, key=lambda x: -len(x))
    used_of = {pg: {} for pg in spans}
    units = []
    stat = {"cards": 0, "lines": 0, "blanks": 0, "sheet_blanks": 0, "num_blanks": 0, "bare": 0, "names": 0}
    for u in data["units"]:
        home = {str(p) for p in UNIT_PAGES[u["no"]]}
        unit_texts = {pg: t for pg, t in texts.items() if pg in home}
        cards = []
        seq = {}
        for c in u["cats"]:
            for it in c["items"]:
                hide = not shows_name(c["key"])
                n = len(cards) + 1
                if it["map"] == "kr_admin":          # 번호 없는 지도 → 시험지에서 번호를 새로 붙인다
                    seq["kr_admin"] = seq.get("kr_admin", 0) + 1
                    mapnum = seq["kr_admin"]
                else:
                    mapnum = it["num"] if it["map"] else None
                lines, answers = [], []
                for kind, src in [("f", s) for s in it["features"]] + [("n", s) for s in it["notes"]]:
                    tag = None
                    m = NOTE_TAG.search(src)
                    if m:
                        tag = m.group(1).replace(" ", " ")
                        src = src[: m.start()]
                    text = mask(src, it) if hide else src
                    pg = page_of(src, texts)
                    own = set(masks_for(it))
                    names = [n for n in allnames if n not in own]
                    spans = choose(text, cands_of.get(pg, {}) if pg else {}, used_of.setdefault(pg, {}), names)
                    parts, at = [], 0
                    for a, b in spans:
                        if a > at:
                            parts.append(text[at:a])
                        parts.append(len(answers))
                        answers.append(text[a:b])
                        at = b
                    if at < len(text):
                        parts.append(text[at:])
                    line = {"k": kind, "p": parts}
                    if tag:
                        line["tag"] = tag
                    lines.append(line)
                    stat["lines"] += 1
                    if not spans:
                        stat["bare"] += 1
                stat["blanks"] += len(answers)
                stat["names"] += 1 if hide else 0
                card = {"id": f'{u["no"]}-{n:02d}', "item": it["id"], "cat": c["key"],
                        "hide": hide, "lines": lines, "ans": answers}
                if not hide:
                    card["title"] = it["name"]
                if it["map"]:
                    card["map"] = it["map"]
                    card["mnum"] = mapnum
                cards.append(card)
        stat["cards"] += len(cards)
        units.append({"no": u["no"], "title": u["title"], "pages": UNIT_LABEL[u["no"]], "cards": cards})
    return units, stat


def write_js(units):
    body = json.dumps(units, ensure_ascii=False, separators=(",", ":"))
    open(OUTJS, "w", encoding="utf-8").write(
        "/* 학습지 전수 점검 시험지 — tools/make_test.py 가 만든다. 손으로 고치지 말 것.\n"
        " * 항목 하나 = 카드 하나. hide:true 면 이름을 맞혀야 하고, lines[].p 의 숫자는 ans 의 빈칸 번호다.\n"
        " * PDF(docs/지역이해-점검시험.pdf)와 문항·번호가 같다. */\n"
        f"const SHEET = {body};\n"
        'if (typeof module !== "undefined") { module.exports = { SHEET }; }\n')


# ── PDF ───────────────────────────────────────────────────────
CIRC = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
def circ(n):
    return CIRC[n] if n < len(CIRC) else f"({n + 1})"


def html_doc(units, data, stat):
    maps = data["maps"]
    byid = {it["id"]: it for u in data["units"] for c in u["cats"] for it in c["items"]}

    texts = ["학습지 전수 점검 시험지 정답 이름 지도 번호 각주 빈칸 점수 카드 쪽 문제 단원 개 "
             "본문 문장 한 번씩 모두 실었습니다 채점 맞은 수 표시 뒤쪽 풀이 방법 사용법 웹 같은 번호 "
             "0123456789/()~·—○①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳ ·:.,%"]
    for u in units:
        texts.append(u["title"] + u["pages"])
        for cd in u["cards"]:
            it = byid[cd["item"]]
            texts.append(it["name"] + "".join(it["aliases"]) + cd.get("title", ""))
            for ln in cd["lines"]:
                texts.append("".join(p for p in ln["p"] if isinstance(p, str)) + ln.get("tag", ""))
            texts.append("".join(cd["ans"]))
    text = "".join(texts)
    fonts = "".join([font_face("Nanum", "NanumGothic.ttf", 400, text),
                     font_face("Nanum", "NanumGothicBold.ttf", 700, text),
                     font_face("Nanum", "NanumGothicExtraBold.ttf", 800, text)])
    css = """
    :root{--ink:#1B1713;--ink2:#4A443B;--faint:#8A8272;--rule:#D9D2C4;--rule2:#BFB7A6;
          --verm:#A8491F;--water:#2E5568;--tint:#F4F1E9}
    *{box-sizing:border-box}
    @page{size:A4;margin:12mm 12mm 11mm}
    body{margin:0;font-family:'Nanum',sans-serif;color:var(--ink);font-size:8.7pt;line-height:1.5}
    .cover{border-top:2.5pt solid var(--ink);border-bottom:.8pt solid var(--ink);padding:9pt 0 10pt;margin-bottom:10pt}
    .cover h1{margin:0 0 3pt;font-size:19pt;font-weight:800;letter-spacing:-.4pt}
    .cover .sub{font-size:9pt;color:var(--ink2)}
    .cover .scope{margin-top:8pt;display:flex;gap:6pt;flex-wrap:wrap}
    .cover .scope span{border:.6pt solid var(--rule2);border-radius:2pt;padding:2.5pt 7pt;font-size:8pt;
          color:var(--ink2);background:var(--tint)}
    .cover .scope b{color:var(--verm)}
    .how{font-size:8pt;color:var(--ink2);margin:0 0 12pt;padding:6pt 9pt;border-left:1.6pt solid var(--verm);background:var(--tint)}
    .how b{color:var(--ink)}
    .unit + .unit{break-before:page}
    .uhead{display:flex;align-items:baseline;gap:8pt;border-bottom:1.4pt solid var(--ink);padding-bottom:4pt;
          margin-bottom:8pt;break-after:avoid}
    .uno{font-size:8.5pt;font-weight:800;color:#fff;background:var(--ink);padding:2pt 6pt;border-radius:2pt}
    .utitle{font-size:13pt;font-weight:800;letter-spacing:-.3pt}
    .upage{margin-left:auto;font-size:7.8pt;color:var(--faint)}
    .score{font-size:8pt;color:var(--ink2);border:.6pt solid var(--rule2);padding:1.5pt 6pt;border-radius:2pt;margin-left:6pt}
    .map{border:.7pt solid var(--rule2);padding:4pt;margin:0 0 8pt;background:#fff;break-inside:avoid}
    .map .in{position:relative;width:fit-content;margin:0 auto}
    .map img{display:block;max-width:100%;max-height:118mm}
    .map .pin{position:absolute;transform:translate(-50%,-50%);width:13pt;height:13pt;border-radius:50%;
          background:var(--verm);color:#fff;font-size:7pt;font-weight:800;display:grid;place-items:center;
          border:1pt solid #fff}
    .map .cap{font-size:7.5pt;color:var(--faint);margin-top:3pt}
    .cards{column-count:2;column-gap:10pt;column-rule:.5pt solid var(--rule)}
    .card{break-inside:avoid;margin:0 0 7pt;padding:0 0 6pt;border-bottom:.5pt dotted var(--rule2)}
    .ch{display:flex;align-items:center;gap:5pt;margin-bottom:2.5pt}
    .cid{font-size:7.4pt;font-weight:800;color:var(--verm);min-width:14pt}
    .mref{font-size:7pt;font-weight:700;color:var(--water);border:.6pt solid var(--water);border-radius:6pt;padding:0 4pt}
    .nm{flex:1;border-bottom:.8pt solid var(--ink);height:12pt;position:relative}
    .nm i{position:absolute;left:0;bottom:1pt;font-style:normal;font-size:6.6pt;color:var(--faint)}
    .ttl{font-weight:800;font-size:9pt}
    .ln{padding-left:9pt;text-indent:-9pt;margin-top:1.6pt;color:var(--ink)}
    .ln::before{content:'•';color:var(--rule2);display:inline-block;width:9pt;text-indent:0}
    .ln.n{color:var(--ink2);font-size:8.1pt}
    .ln .tg{font-size:6.4pt;font-weight:700;color:var(--verm);border:.5pt solid var(--verm);border-radius:2pt;
          padding:0 2.5pt;margin-right:3pt;vertical-align:.8pt;text-indent:0}
    .bl{display:inline-block;border-bottom:.8pt solid var(--ink);min-width:30pt;text-indent:0;
          padding:0 2pt;height:11pt;vertical-align:-2pt;position:relative}
    .bl b{position:absolute;left:1pt;top:-1pt;font-size:6.8pt;font-weight:700;color:var(--verm)}
    .ans .unit + .unit{break-before:auto;margin-top:12pt}
    .ak{column-count:2;column-gap:12pt;column-rule:.5pt solid var(--rule);font-size:8pt}
    .ak div{break-inside:avoid;margin-bottom:3.2pt;padding-left:20pt;text-indent:-20pt}
    .ak .cid{display:inline-block;width:20pt;text-indent:0}
    .ak .an{font-weight:800}
    .ak .x{color:var(--ink2)}
    .ak .x b{color:var(--verm);font-weight:700}
    """

    def blank_w(ans):
        n = len(re.sub(r"\s", "", ans))
        return max(34, min(150, 12 + n * 8.5))

    def line_html(ln, ans):
        out = []
        for p in ln["p"]:
            if isinstance(p, int):
                out.append(f'<span class="bl" style="min-width:{blank_w(ans[p]):.0f}pt"><b>{circ(p)}</b></span>')
            else:
                out.append(esc(p))
        tg = f'<span class="tg">{esc(ln["tag"])}</span>' if ln.get("tag") else ""
        cls = "ln n" if ln["k"] == "n" else "ln"
        if ln["k"] == "n" and not tg:
            tg = '<span class="tg">각주</span>'
        return f'<div class="{cls}">{tg}{"".join(out)}</div>'

    def map_html(key, cards):
        m = maps[key]
        path = os.path.join(ROOT, m["image"])
        mime = "image/jpeg" if path.endswith(".jpg") else "image/png"
        pins = ""
        if not m.get("labeled"):
            for cd in cards:
                it = byid[cd["item"]]
                if cd.get("map") == key and it.get("marker"):
                    pins += (f'<span class="pin" style="left:{it["marker"]["x"]}%;top:{it["marker"]["y"]}%">'
                             f'{cd["mnum"]}</span>')
        return (f'<div class="map"><div class="in"><img src="{b64(path, mime)}">{pins}</div>'
                f'<div class="cap">{esc(m["title"])}</div></div>')

    body = []
    n_cards = stat["cards"]; n_bl = stat["blanks"]; n_nm = stat["names"]
    body.append(
        '<div class="cover"><h1>지역 이해 · 학습지 전수 점검</h1>'
        '<div class="sub">2026학년도 2학기 · 시험 범위 학습지의 본문과 각주를 한 문장도 빼지 않고 실었습니다</div>'
        f'<div class="scope"><span>범위 <b>학습지 1~11쪽 · 23~34쪽</b></span>'
        f'<span>카드 <b>{n_cards}</b>장</span><span>이름 칸 <b>{n_nm}</b></span>'
        f'<span>빈칸 <b>{n_bl}</b></span><span>문장 <b>{stat["lines"]}</b>줄</span></div></div>'
        '<div class="how"><b>푸는 법</b> — 카드 하나가 학습지 항목 하나입니다. '
        '<b>밑줄 칸</b>에는 지도 번호와 설명을 보고 지명·용어를 쓰고, <b>①②③ 칸</b>에는 빠진 말을 씁니다. '
        '본문에 나온 이름은 ○○로 가렸습니다. 빈칸은 선생님이 학습지에서 비워 둔 자리를 먼저 골랐습니다. '
        '정답은 맨 뒤에 있고, 웹 앱의 <b>전수 점검</b>도 같은 번호·같은 문항입니다.</div>')

    for u in units:
        total = sum(len(cd["ans"]) + (1 if cd["hide"] else 0) for cd in u["cards"])
        body.append('<section class="unit">')
        body.append(f'<div class="uhead"><span class="uno">{u["no"]}</span><span class="utitle">{esc(u["title"])}</span>'
                    f'<span class="upage">학습지 {u["pages"]}<span class="score">점수 &nbsp;&nbsp;&nbsp;&nbsp; / {total}</span></span></div>')
        seen = []
        for cd in u["cards"]:
            if cd.get("map") and cd["map"] not in seen:
                seen.append(cd["map"])
        for k in seen:
            body.append(map_html(k, u["cards"]))
        body.append('<div class="cards">')
        for cd in u["cards"]:
            num = cd["id"].split("-")[1]
            mref = f'<span class="mref">지도 {cd["mnum"]}</span>' if cd.get("map") else ""
            if cd["hide"]:
                head = f'<span class="cid">{num}</span>{mref}<span class="nm"></span>'
            else:
                head = f'<span class="cid">{num}</span><span class="ttl">{esc(cd["title"])}</span>'
            body.append(f'<div class="card"><div class="ch">{head}</div>'
                        + "".join(line_html(ln, cd["ans"]) for ln in cd["lines"]) + "</div>")
        body.append("</div></section>")

    # 정답
    body.append('<div class="ans" style="break-before:page">')
    body.append('<div class="cover" style="margin-bottom:8pt"><h1>정답</h1>'
                '<div class="sub">카드 번호 · 이름 · 빈칸 순서. 채점할 때 옆 장을 가리고 보세요.</div></div>')
    for u in units:
        body.append('<section class="unit">')
        body.append(f'<div class="uhead"><span class="uno">{u["no"]}</span><span class="utitle">{esc(u["title"])}</span></div>')
        body.append('<div class="ak">')
        for cd in u["cards"]:
            it = byid[cd["item"]]
            num = cd["id"].split("-")[1]
            nm = f'<span class="an">{esc(it["name"])}</span>' if cd["hide"] else f'<span class="an" style="font-weight:400;color:var(--faint)">{esc(it["name"])}</span>'
            xs = " ".join(f'<b>{circ(i)}</b> {esc(a)}' for i, a in enumerate(cd["ans"]))
            body.append(f'<div><span class="cid">{num}</span>{nm} <span class="x">{xs}</span></div>')
        body.append("</div></section>")
    body.append("</div>")

    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{fonts}{css}</style></head>'
            f'<body>{"".join(body)}</body></html>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="학습지 원본 PDF — 주면 빈칸 정답을 다시 뽑는다")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "지역이해-점검시험.pdf"))
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()

    if a.src:
        blanks = extract_blanks(a.src)
    elif os.path.exists(BLANKS):
        blanks = json.load(open(BLANKS, encoding="utf-8"))
        if "text" not in blanks:
            sys.exit("data/blanks.json 이 옛 형식입니다. --src 로 다시 뽑아 주세요.")
    else:
        sys.exit("data/blanks.json 이 없습니다. --src 로 학습지 원본 PDF 를 주세요.")

    data = dump_items()
    units, stat = build(data, blanks)
    write_js(units)
    print(f"data/sheet.js  카드 {stat['cards']} · 이름 칸 {stat['names']} · 빈칸 {stat['blanks']} · "
          f"문장 {stat['lines']}(빈칸 없는 문장 {stat['bare']})")
    if a.no_pdf:
        return

    html = html_doc(units, data, stat)
    tmp = os.path.join(ROOT, "docs", "_test.html")
    open(tmp, "w", encoding="utf-8").write(html)
    try:
        render_pdf(tmp, a.out)
    finally:
        os.remove(tmp)
    stamp_footer(a.out, "2026 지역 이해 · 학습지 전수 점검 (학습지 1~11쪽, 23~34쪽 · 각주 포함)")
    import pymupdf
    print(f"{os.path.relpath(a.out, ROOT)}  {pymupdf.open(a.out).page_count}쪽  {os.path.getsize(a.out)//1024}KB")


if __name__ == "__main__":
    main()

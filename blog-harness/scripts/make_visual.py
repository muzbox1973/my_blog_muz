#!/usr/bin/env python3
"""기사용 썸네일·인포그래픽을 스티커(assets/stickers)로 꾸며 PNG로 만든다 (blog-seo-aeo-harness 5단계).

사용법:
    python3 make_visual.py visual-plan.json                          # visuals/ 에 PNG·HTML·리포트 생성
    python3 make_visual.py visual-plan.json --package article-package.md   # 숫자 대조까지 (권장)
    python3 make_visual.py visual-plan.json --only thumbnail          # 한 장만 다시
    python3 make_visual.py --list                                     # 스티커 목록 보기

비율: 썸네일은 계획의 thumbnail_format(square 1080×1080 / landscape 1280×720, 사람이 고름),
      본문 인포그래픽은 항상 가로형 1280×720.
결과: visuals/<id>.png, visuals/<id>.html(단독 실행 가능), visuals/visuals-report.json
      FAIL이 하나라도 있으면 종료코드 1.
렌더에는 Python Playwright(Chromium)가 필요하다. 없으면 HTML만 만들고 RENDER FAIL을 낸다.
그 외에는 표준 라이브러리만 사용한다.
"""
import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STK_DIR = os.path.normpath(os.environ.get("HARNESS_STICKERS") or os.path.join(HERE, "..", "assets", "stickers"))
# 스티커는 원본 크기와 상관없이 '화면에 보일 크기(긴 변, px)'로 배치한다 → 사용자 스티커 규격이 달라도 같은 모양
DEFAULT_BOX = {"prop": 120, "marker": 56, "arrow": 96, "bubble": 140, "card": 260, "tape": 120, "label": 150, "character": 380}

THEMES = {
    "cream": dict(bg="#fbf6ea", bg2="#f1e6cc", ink="#1f2633", title="#1f2633", sub="#5b6475",
                  accent="#f2b632", accent2="#9fd3b0", card="#fffdf7", line="#23272f", soft="#f6dfa4"),
    "sky":   dict(bg="#eaf3fd", bg2="#cfe2f8", ink="#152238", title="#152238", sub="#4c5d78",
                  accent="#f2b632", accent2="#9cc7f2", card="#ffffff", line="#1d2433", soft="#c4dcf6"),
    "mint":  dict(bg="#e9f6ee", bg2="#cbe9d6", ink="#17302a", title="#17302a", sub="#4d6a60",
                  accent="#f2b632", accent2="#8fd0ae", card="#ffffff", line="#1f2b27", soft="#bfe3cd"),
    "navy":  dict(bg="#1f2a44", bg2="#2d3d63", ink="#1f2633", title="#ffffff", sub="#cfd8ea",
                  accent="#ffcf4a", accent2="#8fd0ae", card="#fffdf7", line="#0f1420", soft="#3a4d7a"),
}
FONT = ('"Pretendard","Noto Sans KR","Noto Sans CJK KR","Malgun Gothic",'
        '"Apple SD Gothic Neo",sans-serif')
TYPES = ("thumbnail", "steps", "compare", "checklist", "keypoint", "stats")


# ---------------------------------------------------------------- 공통
class Report:
    def __init__(self):
        self.items = []

    def add(self, level, img, code, msg):
        self.items.append({"level": level, "image": img, "code": code, "msg": msg})

    @property
    def failed(self):
        return any(i["level"] == "FAIL" for i in self.items)


def load_catalog():
    with open(os.path.join(STK_DIR, "stickers.json"), encoding="utf-8") as f:
        cat = json.load(f)
    return {s["id"]: s for s in cat["stickers"]}


_URI = {}


def uri(sid, cat):
    if sid not in _URI:
        with open(os.path.join(STK_DIR, cat[sid]["file"]), "rb") as f:
            _URI[sid] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    return _URI[sid]


def esc(s):
    return html.escape(str(s or ""))


def with_highlight(text, hl, tape_uri):
    """제목 속 강조어 밑에 테이프 스티커를 형광펜처럼 깐다."""
    t = esc(text)
    if hl and esc(hl) in t:
        h = esc(hl)
        t = t.replace(h, f'<span class="hl" style="background-image:url({tape_uri})">{h}</span>', 1)
    return t.replace("\\n", "<br>").replace("\n", "<br>")


class Ctx:
    """이미지 한 장을 만드는 동안 스티커 사용을 기록한다."""

    def __init__(self, cat, rep, img_id):
        self.cat, self.rep, self.id = cat, rep, img_id
        self.used = []

    def fit(self, sid, box=None, width=None, height=None):
        """표시 크기 → 배율. box=긴 변, width/height=그 변 기준 (여러 개면 가장 작은 배율)."""
        s = self.cat.get(sid)
        if not s:
            return 1.0
        cands = []
        if box:
            cands.append(box / max(s["w"], s["h"]))
        if width:
            cands.append(width / s["w"])
        if height:
            cands.append(height / s["h"])
        return min(cands) if cands else 1.0

    def stk(self, sid, x, y, scale=1.0, rot=0, cls="", z=3, extra_style="", box=None):
        """스티커 <img>. x,y는 왼쪽 위 좌표(px). 문자열이면 CSS 그대로 사용. box를 주면 긴 변을 그 크기로."""
        if sid not in self.cat:
            self.rep.add("FAIL", self.id, "STICKER_ID", f"없는 스티커 id: {sid}")
            return ""
        s = self.cat[sid]
        if box:
            scale = self.fit(sid, box=box)
        w, h = round(s["w"] * scale), round(s["h"] * scale)
        self.used.append({"id": sid, "scale": round(scale, 2), "kind": s["kind"]})
        if scale > s["max_scale"] + 1e-6:
            self.rep.add("WARN", self.id, "STICKER_SCALE",
                         f"{sid} 원본({s['w']}×{s['h']})을 {scale:.2f}배 확대 (권장 {s['max_scale']}배 이하, 흐려짐) — 더 큰 원본을 넣거나 표시 크기를 줄일 것")
        pos = ""
        for k, v in (("left", x), ("top", y)):
            if isinstance(v, str):
                pos += f"{v};" if ":" in v else f"{k}:{v};"
            elif v is not None:
                pos += f"{k}:{v}px;"
        return (f'<img class="stk {s["kind"]} {cls}" data-sid="{sid}" src="{uri(sid, self.cat)}" '
                f'style="{pos}width:{w}px;height:{h}px;transform:rotate({rot}deg);z-index:{z};{extra_style}" alt="">')

    def size(self, sid, scale):
        s = self.cat.get(sid, {"w": 0, "h": 0})
        return round(s["w"] * scale), round(s["h"] * scale)

    def char_scale(self, sid, target_h, max_w=None):
        """캐릭터: 목표 높이에 맞추되 너무 넓으면 폭 기준. 원본이 작으면 max_scale까지만 키운다(흐림 방지)."""
        s = self.cat.get(sid)
        if not s:
            return 1.0
        sc = target_h / s["h"]
        if max_w:
            sc = min(sc, max_w / s["w"])
        return min(sc, s["max_scale"])

    def char_bottom(self, sid):
        """상반신(아래가 잘린) 스티커는 아랫선에 붙이고, 전신·떠 있는 스티커는 조금 띄운다."""
        return "bottom:0" if self.cat.get(sid, {}).get("bottom_cut", True) else "bottom:24px"


def base_css(th, W):
    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:{th['bg']}}}
body{{font-family:{FONT};color:{th['ink']};-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:anywhere}}
.canvas{{position:relative;width:{W}px;overflow:hidden;background:
  radial-gradient(circle at 6% 10%, {th['bg2']}33 0 90px, transparent 91px),
  radial-gradient(circle at 88% 92%, {th['bg2']}66 0 180px, transparent 181px),
  {th['bg']}}}
.stk{{position:absolute;pointer-events:none;filter:drop-shadow(0 3px 0 rgba(0,0,0,.10))}}
.stk.character{{filter:none}}
.hl{{background-repeat:no-repeat;background-size:104% 58%;background-position:-2% 92%;padding:0 .06em}}
.fit{{overflow:hidden}}
.card{{position:relative;background:{th['card']};border:3px solid {th['line']};border-radius:22px;color:{th['ink']}}}
.pill{{display:inline-block;border:3px solid {th['line']};border-radius:999px;font-weight:800;color:{th['ink']}}}
.kicker{{font-size:26px;font-weight:800;color:{th['sub']};letter-spacing:.02em}}
.h1{{font-weight:900;letter-spacing:-.02em;line-height:1.18;color:{th['title']}}}
.sub{{font-weight:600;color:{th['sub']};line-height:1.45}}
.body{{flex:1;min-height:0;overflow:hidden;margin-top:18px;padding:22px 4px 6px;display:flex;align-items:center}}
.footer2{{font-size:18px;color:{th['sub']};display:flex;justify-content:space-between;gap:24px;padding-top:8px}}
.bubble{{position:absolute;display:flex;align-items:center;justify-content:center;z-index:6}}
.bubble img{{position:absolute;inset:0;width:100%;height:100%}}
.bubble span{{position:relative;font-weight:900;color:#1f2633;padding-bottom:12%;white-space:nowrap}}
"""


def bubble_scale(c, b, width):
    """말풍선은 표시 폭으로 크기를 정한다 (size로 배수 조정)."""
    return c.fit(b["sticker"], width=width * b.get("size", 1.0))


def bubble_html(c, b, x, y, scale):
    sid = b["sticker"]
    if sid not in c.cat:
        c.rep.add("FAIL", c.id, "STICKER_ID", f"없는 스티커 id: {sid}")
        return ""
    w, h = c.size(sid, scale)
    c.used.append({"id": sid, "scale": round(scale, 2), "kind": "bubble"})
    if scale > c.cat[sid]["max_scale"] + 1e-6:
        c.rep.add("WARN", c.id, "STICKER_SCALE", f"{sid} 말풍선 {scale:.2f}배 확대 (흐려짐) — size를 줄이거나 더 큰 원본 사용")
    text = b.get("text", "")
    if len(text) > 10:
        c.rep.add("WARN", c.id, "BUBBLE_TEXT", f"말풍선 글자 {len(text)}자 (10자 이하 권장)")
    fs = max(18, min(34, int(w / max(len(text), 2) * 0.95)))
    pos = "".join((v if isinstance(v, str) else f"{k}:{round(v)}px") + ";" for k, v in (("left", x), ("top", y)))
    return (f'<div class="bubble" style="{pos}width:{w}px;height:{h}px">'
            f'<img src="{uri(sid, c.cat)}" alt=""><span class="txt inbubble" style="font-size:{fs}px">{esc(text)}</span></div>')


def props_list(sp):
    out = []
    for p in sp.get("props", []) or []:
        out.append(p if isinstance(p, dict) else {"id": p})
    return out


def prop_html(c, p, slots):
    sid = p.get("id")
    slot = p.get("slot")
    if slot not in slots:
        used = getattr(c, "_slots", set())
        slot = next((s for s in slots if s not in used), list(slots)[0])
    c._slots = getattr(c, "_slots", set()) | {slot}
    x, y = p.get("x", slots[slot][0]), p.get("y", slots[slot][1])
    kind = c.cat.get(sid, {}).get("kind", "prop")
    if "scale" in p:  # 예전 방식(원본 배율) 호환
        return c.stk(sid, x, y, p["scale"], p.get("rot", -6), z=p.get("z", 3))
    box = p.get("box") or DEFAULT_BOX.get(kind, 120) * p.get("size", 1.0)
    return c.stk(sid, x, y, rot=p.get("rot", -6), z=p.get("z", 3), box=box)


# ---------------------------------------------------------------- 유형별
# 썸네일: 정사각형(1080×1080) 또는 가로형(1280×720) — 사람이 고른 비율 (thumbnail_format)
# 본문 이미지·인포그래픽: 모두 가로형 1280×720
THUMB_FORMATS = {"square": (1080, 1080), "landscape": (1280, 720)}
LW, LH = 1280, 720
ITEM_LIMITS = {"steps": (2, 4), "checklist": (2, 6), "stats": (1, 4)}


def thumb_format(sp, plan):
    return sp.get("format") or plan.get("thumbnail_format")


def build_thumbnail(c, sp, th):
    fmt = sp.get("_format") or "landscape"
    W, H = THUMB_FORMATS.get(fmt, THUMB_FORMATS["landscape"])
    sq = fmt == "square"
    tape_id = sp.get("tape", "tape-yellow")
    tape = uri(tape_id, c.cat) if tape_id in c.cat else ""
    ch = sp.get("character", "char-pointing-idea")
    circle = 620 if sq else 640
    parts = [f'<div class="canvas" style="height:{H}px">',
             f'<div style="position:absolute;right:-70px;bottom:-150px;width:{circle}px;height:{circle}px;border-radius:50%;'
             f'background:{th["soft"]};opacity:.75"></div>']
    # 글자 영역: 가로형은 왼쪽 세로 가운데, 정사각형은 위쪽
    if sq:
        parts.append('<div style="position:absolute;left:80px;top:96px;width:920px;z-index:4">')
    else:
        parts.append('<div style="position:absolute;left:76px;top:0;bottom:0;width:700px;display:flex;'
                     'flex-direction:column;justify-content:center;z-index:4">')
    if sp.get("badge"):
        parts.append(f'<div><span class="pill txt" style="font-size:{32 if sq else 30}px;padding:6px 24px;'
                     f'background:{th["accent2"]};margin-bottom:24px">{esc(sp["badge"])}</span></div>')
    # 제목은 \n으로 나눈 각 줄이 한 줄에 들어가야 한다 → 넘치면 글자를 줄이고, 최소 크기에서도 넘치면 FAIL
    parts.append(f'<div class="h1 fit txt" data-max="{108 if sq else 100}" data-min="60" '
                 f'style="max-height:{280 if sq else 360}px;margin-top:6px;white-space:nowrap">'
                 f'{with_highlight(sp.get("title", ""), sp.get("highlight"), tape)}</div>')
    if sp.get("subtitle") and not sq:
        parts.append(f'<div class="sub fit txt" data-max="36" data-min="24" style="margin-top:24px;'
                     f'max-height:110px;font-weight:700">{esc(sp["subtitle"])}</div>')
    parts.append("</div>")
    # 캐릭터 (아래 가장자리에 붙임)
    cw = chh = 0
    right = 50 if sq else 40
    if ch:
        sc = c.char_scale(ch, sp.get("character_height", 470 if sq else 560), max_w=540 if sq else 520)
        cw, chh = c.size(ch, sc)
        parts.append(c.stk(ch, f"right:{right}px", c.char_bottom(ch), sc, z=3))
    cx = W - right - cw
    b = sp.get("bubble")
    bub_left = W
    if b and b.get("sticker") and sq:
        bub_left = W - (right + cw * 0.78) - c.size(b["sticker"], bubble_scale(c, b, 145))[0]
    if sq and sp.get("subtitle"):  # 정사각형: 부제는 왼쪽 아래 테이프 카드 (말풍선·캐릭터를 피해서)
        card_w = max(min(cx - 80 - 30, bub_left - 80 - 24), 360)
        parts.append(f'<div class="card" style="position:absolute;left:80px;bottom:170px;width:{card_w}px;'
                     f'padding:34px 34px 30px;z-index:4">'
                     + c.stk(sp.get("subtitle_tape", "tape-blue"), "-16px", "-22px", rot=-8, z=6, box=88)
                     + f'<div class="sub fit txt" data-max="42" data-min="26" style="max-height:120px;font-weight:800;'
                       f'color:{th["ink"]}">{esc(sp["subtitle"])}</div></div>')
    b = sp.get("bubble")
    if b and b.get("sticker"):
        bs = bubble_scale(c, b, 145)
        bw, bh = c.size(b["sticker"], bs)
        if sq:  # 얼굴 왼쪽 옆
            parts.append(bubble_html(c, b, f"right:{round(right + cw * 0.78)}px", f"bottom:{round(chh * 0.66)}px", bs))
        else:
            parts.append(bubble_html(c, b, max(cx - bw * 0.45, 700), max(H - chh - bh * 0.35, 16), bs))
    if sq:
        slots = {"bl": (96, H - 140), "gap": (cx - 120, H - 150), "tm": (cx + cw * 0.25, H - chh - 120), "tr": (W - 150, H - chh - 150)}
    else:
        slots = {"tr": (W - 150, 26), "tm": (cx + cw * 0.15, 20), "gap": (cx - 120, H - 190), "bl": (40, H - 130)}
    for p in props_list(sp):
        parts.append(prop_html(c, p, slots))
    parts.append("</div>")
    return W, H, "".join(parts)


def land_frame(c, sp, th, default_char, body, slots_extra=None):
    """가로형 1280×720 공통 틀: 위쪽 제목(전체 폭) + 왼쪽 본문 칸 + 오른쪽 아래 캐릭터 + 출처 줄.
    본문 칸(.fit data-box)은 em 단위로 짜여 있어, 넘치면 글자 크기를 통째로 줄인다."""
    tape_id = sp.get("tape", "tape-yellow")
    tape = uri(tape_id, c.cat) if tape_id in c.cat else ""
    ch = sp.get("character", default_char)
    cw = chh = 0
    side = []
    if ch:
        b = sp.get("bubble")
        sc = c.char_scale(ch, sp.get("character_height", 380), max_w=420)
        cw, chh = c.size(ch, sc)
        side.append(c.stk(ch, "right:28px", c.char_bottom(ch), sc, z=2))
        if b and b.get("sticker"):  # 얼굴 왼쪽 옆
            bs = bubble_scale(c, b, 120)
            side.append(bubble_html(c, b, f"right:{round(28 + cw * 0.74)}px", f"bottom:{round(chh * 0.70)}px", bs))
    col_w = LW - 64 - (cw + 28 + 30 if ch else 64)
    hd = []
    if sp.get("kicker"):
        hd.append(f'<div class="kicker txt" style="font-size:22px;margin-bottom:8px">{esc(sp["kicker"])}</div>')
    hd.append(f'<div class="h1 fit txt" data-max="56" data-min="34" style="max-height:140px">'
              f'{with_highlight(sp.get("title", ""), sp.get("highlight"), tape)}</div>')
    if sp.get("subtitle"):
        hd.append(f'<div class="sub fit txt" data-max="26" data-min="20" style="margin-top:8px;max-height:40px;white-space:nowrap">'
                  f'{esc(sp["subtitle"])}</div>')
    src, brand = sp.get("source") or "", sp.get("brand") or ""
    foot = (f'<div class="footer2"><span class="txt">{esc("출처: " + src) if src else ""}</span>'
            f'<span class="txt" style="font-weight:800">{esc(brand)}</span></div>') if (src or brand) else ""
    parts = [f'<div class="canvas" style="height:{LH}px">',
             f'<div style="position:absolute;right:-90px;bottom:-170px;width:560px;height:560px;border-radius:50%;'
             f'background:{th["soft"]};opacity:.55"></div>',
             '<div style="position:absolute;left:64px;top:40px;bottom:22px;right:64px;display:flex;flex-direction:column;z-index:4">',
             f'<div style="max-width:{LW - 128 - (cw * 0.35 if ch else 0):.0f}px">{"".join(hd)}</div>',
             f'<div class="fit body" data-box="1" data-max="36" data-min="18" style="width:{col_w}px">{body}</div>',
             f'<div style="width:{col_w}px">{foot}</div>',
             "</div>"]
    parts += side
    slots = {"tr": (LW - 150, 26), "tm": (LW - 28 - cw * 0.75, LH - chh - 120)}
    slots.update(slots_extra or {})
    for p in props_list(sp):
        parts.append(prop_html(c, p, slots))
    parts.append("</div>")
    return LW, LH, "".join(parts)


def num_badge(i, th):
    return (f'<div class="txt" style="width:1.75em;height:1.75em;border-radius:50%;border:3px solid {th["line"]};'
            f'background:{th["accent"]};display:flex;align-items:center;justify-content:center;font-size:1.05em;'
            f'font-weight:900;flex:none">{i}</div>')


def build_steps(c, sp, th):
    items = sp.get("items", [])
    tapes = ["tape-yellow", "tape-blue"]
    arrow = sp.get("arrow", "arrow-curve-blue")
    n = max(len(items), 1)
    b = [f'<div style="display:grid;grid-template-columns:repeat({n},1fr);gap:1.25em;width:100%">']
    for i, it in enumerate(items, 1):
        b.append('<div class="card" style="padding:1.05em .85em 1em">')
        b.append(c.stk(tapes[i % 2], "-14px", "-20px", rot=-9, z=5, box=70))
        b.append(num_badge(i, th))
        b.append(f'<div class="txt" style="font-size:1.02em;font-weight:800;line-height:1.3;margin-top:.55em">{esc(it.get("title", ""))}</div>')
        if it.get("text"):
            b.append(f'<div class="txt sub" style="font-size:.78em;margin-top:.4em">{esc(it["text"])}</div>')
        if i < len(items):  # 다음 카드로 가는 화살표 (카드 사이 틈에)
            b.append(c.stk(arrow, "calc(100% - 10px)", "40%", rot=38, z=6, box=52))
        b.append("</div>")
    b.append("</div>")
    return land_frame(c, sp, th, "char-explain", "".join(b))


def build_compare(c, sp, th):
    L, R = sp.get("left", {}), sp.get("right", {})
    b = ['<div style="width:100%"><div style="display:grid;grid-template-columns:1fr 1fr;gap:1.1em;padding-top:.9em">']
    for side, col in ((L, th["accent2"]), (R, th["accent"])):
        b.append('<div class="card" style="padding:1.35em .95em .6em">')
        b.append(f'<div style="position:absolute;left:0;right:0;top:-.95em;text-align:center"><span class="pill txt" '
                 f'style="font-size:.95em;padding:.15em .9em;background:{col}">{esc(side.get("label", ""))}</span></div>')
        for pt in side.get("points", []):
            b.append(f'<div class="txt" style="display:flex;gap:.4em;font-size:.8em;line-height:1.45;padding:.38em 0;'
                     f'border-bottom:2px dashed {th["bg2"]}"><b>•</b><span>{esc(pt)}</span></div>')
        b.append("</div>")
    b.append("</div>")
    if sp.get("verdict"):
        b.append(f'<div class="card" style="margin-top:.8em;padding:.6em .9em .6em 3.2em;background:{th["soft"]}">')
        b.append(c.stk(sp.get("verdict_icon", "bulb"), "14px", "calc(50% - 30px)", rot=-6, z=5, box=60))
        b.append(f'<div class="txt" style="font-size:.84em;font-weight:800;line-height:1.4">{esc(sp["verdict"])}</div></div>')
    b.append("</div>")
    return land_frame(c, sp, th, "char-crossed-arms", "".join(b))


def build_checklist(c, sp, th):
    items = sp.get("items", [])
    cols = 1 if len(items) <= 3 else 2
    b = [f'<div class="card" style="width:100%;padding:.5em 1.1em;display:grid;grid-template-columns:repeat({cols},1fr);column-gap:1.4em">']
    for it in items:
        b.append(f'<div style="display:flex;gap:.6em;align-items:flex-start;padding:.55em 0;border-bottom:2px dashed {th["bg2"]}">'
                 f'<div style="flex:none;width:1.35em;height:1.35em;border-radius:.3em;background:#5aa469;border:3px solid {th["line"]};'
                 f'color:#fff;font-size:.95em;font-weight:900;display:flex;align-items:center;justify-content:center">✓</div>'
                 f'<div class="txt" style="font-size:.84em;line-height:1.45;font-weight:600">{esc(it)}</div></div>')
    b.append("</div>")
    return land_frame(c, sp, th, "char-thumbsup", "".join(b))


def build_keypoint(c, sp, th):
    b = ['<div class="card" style="width:100%;padding:1.5em 1.5em 1.3em;margin-top:.6em">',
         c.stk(sp.get("tape", "tape-yellow"), "calc(50% - 56px)", "-24px", rot=-3, z=6, box=112),
         f'<div class="txt" style="font-size:1.55em;font-weight:900;line-height:1.3;letter-spacing:-.02em">{esc(sp.get("point", sp.get("title", "")))}</div>']
    if sp.get("text"):
        b.append(f'<div class="txt sub" style="font-size:.9em;margin-top:.6em">{esc(sp["text"])}</div>')
    b.append("</div>")
    sp2 = dict(sp)
    if sp.get("point"):  # point가 있으면 제목은 머리말, point는 카드
        pass
    else:  # 제목을 카드에 크게 → 머리말에는 kicker만
        sp2["title"] = sp.get("kicker", "핵심 포인트")
        sp2["kicker"] = None
    return land_frame(c, sp2, th, "char-pointing-idea", "".join(b))


def build_stats(c, sp, th):
    items = sp.get("items", [])
    for it in items:
        if not str(it.get("source", "")).strip():
            c.rep.add("FAIL", c.id, "STAT_SOURCE", f"수치 '{it.get('value')}'에 출처(source) 없음")
    cols = len(items) if len(items) <= 3 else 2
    b = [f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:.8em;width:100%">']
    for it in items:
        b.append('<div class="card" style="padding:.7em .9em">'
                 f'<div class="txt" style="font-size:1.75em;font-weight:900;line-height:1.1;letter-spacing:-.02em">{esc(it.get("value", ""))}</div>'
                 f'<div class="txt" style="font-size:.8em;font-weight:700;margin-top:.35em;line-height:1.35">{esc(it.get("label", ""))}</div>'
                 f'<div class="txt sub" style="font-size:.64em;margin-top:.35em">출처: {esc(it.get("source", ""))}</div></div>')
    b.append("</div>")
    return land_frame(c, sp, th, sp.get("character", "char-explain"), "".join(b))


BUILDERS = {"thumbnail": build_thumbnail, "steps": build_steps, "compare": build_compare,
            "checklist": build_checklist, "keypoint": build_keypoint, "stats": build_stats}

# 렌더 후 브라우저 안에서 실행: 글자 크기 맞추기 → 넘침·겹침 측정
MEASURE_JS = r"""
() => {
  // 줄 상자 높이(offsetHeight)로 판정: 한글 글꼴의 위아래 여백 때문에 scrollHeight는 실제보다 크게 나온다
  // data-box 칸(인포그래픽 본문)은 높이가 고정된 상자라 scrollHeight로 판정
  const over = el => { if (el.dataset.box) return el.scrollHeight > el.clientHeight + 4 || el.scrollWidth > el.clientWidth + 2;
    const mh = +el.dataset.mh || 0; return (mh && el.offsetHeight > mh + 1) || el.scrollWidth > el.clientWidth + 2; };
  document.querySelectorAll('.fit').forEach(el => {
    if (!el.dataset.box && !el.dataset.mh) { el.dataset.mh = parseFloat(getComputedStyle(el).maxHeight) || 0; el.style.maxHeight = 'none'; }
    let mx = +el.dataset.max || 0, mn = +el.dataset.min || 0;
    if (!mx) return;
    let s = mx; el.style.fontSize = s + 'px';
    while (over(el) && s > mn) { s -= 2; el.style.fontSize = s + 'px'; }
    el.dataset.final = s;
  });
  const out = {overflow: [], overlap: [], fonts: [], minFont: 99};
  document.querySelectorAll('.fit').forEach(el => { if (over(el)) out.overflow.push((el.innerText || '').replace(/\n/g, ' / ').slice(0, 30)); });
  const shrink = (r, k) => ({l: r.left + r.width * k, r: r.right - r.width * k, t: r.top + r.height * k, b: r.bottom - r.height * k});
  const stks = [...document.querySelectorAll('img.stk')].filter(s => !s.classList.contains('marker'))
                 .map(s => ({sid: s.dataset.sid, r: shrink(s.getBoundingClientRect(), s.classList.contains('character') ? 0.14 : 0.10)}))
                 .concat([...document.querySelectorAll('.bubble')].map(s => ({sid: 'bubble', r: shrink(s.getBoundingClientRect(), 0.10)})));
  document.querySelectorAll('.txt:not(.inbubble)').forEach(el => {
    const rg = document.createRange(); rg.selectNodeContents(el);
    const rects = [...rg.getClientRects()].filter(r => r.width > 2 && r.height > 2);
    const fs = parseFloat(getComputedStyle(el).fontSize); if (fs < out.minFont) out.minFont = fs;
    let area = 0, hit = 0, who = new Set();
    rects.forEach(r => { area += r.width * r.height;
      stks.forEach(s => { const w = Math.min(r.right, s.r.r) - Math.max(r.left, s.r.l), h = Math.min(r.bottom, s.r.b) - Math.max(r.top, s.r.t);
        if (w > 0 && h > 0) { hit += w * h; who.add(s.sid); } }); });
    if (hit > 0) out.overlap.push({text: (el.innerText || '').slice(0, 24), ratio: hit / Math.max(area, 1), stickers: [...who]});
  });
  const c = document.querySelector('.canvas').getBoundingClientRect();
  out.height = Math.round(c.height);
  return out;
}
"""


def page_html(W, H, body, th, title):
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<meta name="viewport" content="width={W}"><style>{base_css(th, W)}</style></head>'
            f'<body>{body}</body></html>')


def numbers_in(s):
    return re.findall(r"\d+(?:[.,]\d+)?", s or "")


def collect_text(sp):
    keys = ("title", "subtitle", "badge", "kicker", "text", "verdict", "point")
    out = [str(sp.get(k, "")) for k in keys]
    for it in sp.get("items", []) or []:
        out += [str(v) for v in (it.values() if isinstance(it, dict) else [it])
                if not isinstance(v, (dict, list))]
    for side in ("left", "right"):
        d = sp.get(side) or {}
        out += [str(d.get("label", ""))] + [str(x) for x in d.get("points", [])]
    if sp.get("bubble"):
        out.append(str(sp["bubble"].get("text", "")))
    return out


def lint_plan(plan, cat, rep, package_text):
    imgs = plan.get("images", [])
    if not any(i.get("type") == "thumbnail" for i in imgs):
        rep.add("FAIL", "-", "THUMBNAIL", "썸네일(type: thumbnail)이 계획에 없음")
    for sp in imgs:
        if sp.get("type") == "thumbnail":
            f = thumb_format(sp, plan)
            if f not in THUMB_FORMATS:
                rep.add("FAIL", sp.get("id") or "thumbnail", "THUMB_FORMAT",
                        "썸네일 비율 미지정 — 사람에게 정사각형(square)·가로형(landscape) 중 물어 thumbnail_format에 기록"
                        if not f else f"알 수 없는 썸네일 비율 '{f}' (square 또는 landscape)")
        elif sp.get("format") and sp.get("format") != "landscape":
            rep.add("WARN", sp.get("id") or sp.get("type"), "BODY_FORMAT", "본문 이미지는 항상 가로형(1280×720) — format 무시")
        lim = ITEM_LIMITS.get(sp.get("type"))
        if lim and not lim[0] <= len(sp.get("items") or []) <= lim[1]:
            rep.add("WARN", sp.get("id") or sp.get("type"), "ITEMS",
                    f"항목 {len(sp.get('items') or [])}개 (가로형 권장 {lim[0]}~{lim[1]}개)")
        if sp.get("type") == "compare":
            for sd in ("left", "right"):
                if len((sp.get(sd) or {}).get("points", [])) > 4:
                    rep.add("WARN", sp.get("id") or "compare", "ITEMS", f"{sd} 항목 4개 초과 (가로형 권장 2~4개)")
    poses = {}
    for sp in imgs:
        iid = sp.get("id") or sp.get("type")
        if sp.get("type") not in TYPES:
            rep.add("FAIL", iid, "TYPE", f"알 수 없는 type '{sp.get('type')}' (가능: {', '.join(TYPES)})")
            continue
        if not str(sp.get("alt", "")).strip():
            rep.add("FAIL", iid, "ALT", "alt 문구 없음")
        elif ("스티커" in sp["alt"] or "캐릭터" in sp["alt"]) and len(sp["alt"]) < 25:
            rep.add("WARN", iid, "ALT", "alt가 장식(스티커·캐릭터)만 설명함 — 이미지가 전달하는 정보를 쓸 것")
        chars = [sp.get("character")] if sp.get("character") else []
        props = props_list(sp)
        if len(props) > 3:
            rep.add("FAIL", iid, "PROPS", f"소품 스티커 {len(props)}개 (최대 3개)")
        for p in props:
            if cat.get(p.get("id"), {}).get("kind") == "character":
                chars.append(p["id"])
        if len(chars) > 1:
            rep.add("FAIL", iid, "CHARACTERS", f"캐릭터 {len(chars)}명 (이미지 1장에 최대 1명)")
        for ch in chars:
            if ch in cat and cat[ch]["kind"] != "character":
                rep.add("FAIL", iid, "CHARACTER_KIND", f"{ch}는 캐릭터 스티커가 아님")
            poses[ch] = poses.get(ch, 0) + 1
        bsid = (sp.get("bubble") or {}).get("sticker")
        if bsid and (sp.get("bubble") or {}).get("text") and cat.get(bsid, {}).get("text_inside") is False:
            rep.add("WARN", iid, "BUBBLE_TEXT", f"{bsid}는 안에 그림이 있어 글자를 넣기 부적합 — 글자 없이 쓰거나 빈 말풍선 사용")
        for sid in [p.get("id") for p in props] + [(sp.get("bubble") or {}).get("sticker")]:
            if sid and cat.get(sid, {}).get("has_text") and not sp.get("text_sticker_ok"):
                rep.add("WARN", iid, "TEXT_STICKER",
                        f"{sid}에는 글자가 박혀 있음 — 주제가 맞을 때만 쓰고 text_sticker_ok: true로 표시")
        for t in collect_text(sp) + [str(sp.get("source", ""))] + [str((i or {}).get("source", "")) for i in (sp.get("items") or []) if isinstance(i, dict)]:
            m = re.search(r"근거#\d+|\[(확인 필요|경험 보강 필요|근거 보강 필요|사람 확인)", t)
            if m:
                rep.add("FAIL", iid, "TEMP_MARKER", f"이미지에 내부 표식 '{m.group(0)}' — 실제 출처명·확정 문구로 바꿀 것")
        if package_text is not None:
            pkg_nums = set(numbers_in(package_text))
            for t in collect_text(sp):
                for n in numbers_in(t):
                    if n not in pkg_nums and not (sp.get("type") == "steps" and n.isdigit() and int(n) <= 10 and t.strip() == n):
                        rep.add("FAIL", iid, "NEW_NUMBER", f"기사 패키지에 없는 숫자 '{n}' ({t[:24]})")
    for ch, n in poses.items():
        if n > 2:
            rep.add("WARN", "-", "POSE_REPEAT", f"{ch} 포즈를 {n}번 사용 (기사당 2번 이하 권장)")


def korean_font_ok():
    try:
        out = subprocess.run(["fc-list", ":lang=ko", "family"], capture_output=True, text=True, timeout=10).stdout
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return None  # 확인 불가 (Windows·macOS는 대개 기본 한글 글꼴 있음)


def render(jobs, rep):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        rep.add("FAIL", "-", "RENDER", "Python Playwright 없음 — HTML만 생성. "
                "`pip install playwright` 후 `python -m playwright install chromium` 필요")
        return
    with sync_playwright() as p:
        try:
            br = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            rep.add("FAIL", "-", "RENDER", f"Chromium 실행 실패 — HTML만 생성 ({str(e)[:120]})")
            return
        for j in jobs:
            pg = br.new_page(viewport={"width": j["W"], "height": j["H"] or 900}, device_scale_factor=1)
            pg.set_content(j["html"], wait_until="load")
            try:
                pg.evaluate("document.fonts.ready.then(()=>1)")
            except Exception:  # noqa: BLE001
                pass
            m = pg.evaluate(MEASURE_JS)
            # 맞춘 글자 크기를 HTML에도 반영해 저장
            with open(j["html_path"], "w", encoding="utf-8") as f:
                f.write("<!doctype html>" + pg.evaluate("document.documentElement.outerHTML"))
            if j["H"]:
                pg.screenshot(path=j["png"], clip={"x": 0, "y": 0, "width": j["W"], "height": j["H"]})
            else:
                pg.locator(".canvas").screenshot(path=j["png"])
            pg.close()
            iid = j["id"]
            for t in m["overflow"]:
                rep.add("FAIL", iid, "TEXT_OVERFLOW", f"글자가 상자를 넘침: '{t}' — 글을 줄이거나 나눌 것")
            for o in m["overlap"]:
                lv = "FAIL" if o["ratio"] > 0.04 else "WARN"
                rep.add(lv, iid, "STICKER_OVER_TEXT",
                        f"{', '.join(o['stickers'])}가 글자 '{o['text']}'를 {o['ratio']:.0%} 가림 — 위치·크기 조정")
            if m["minFont"] < 17:
                rep.add("WARN", iid, "SMALL_TEXT", f"가장 작은 글자 {m['minFont']:.0f}px (모바일에서 읽기 어려움)")
            j["height"] = m["height"]
        br.close()


def main():
    ap = argparse.ArgumentParser(description="스티커로 꾸민 썸네일·인포그래픽 생성")
    ap.add_argument("plan", nargs="?", help="visual-plan.json")
    ap.add_argument("--package", help="article-package.md (숫자 대조용)")
    ap.add_argument("--out", help="출력 폴더 (기본: 계획 파일 옆 visuals/)")
    ap.add_argument("--only", action="append", help="이 id만 다시 만들기 (여러 번 지정 가능)")
    ap.add_argument("--list", action="store_true", help="스티커 목록 출력")
    a = ap.parse_args()
    cat = load_catalog()
    if a.list:
        kinds = {}
        for s in cat.values():
            kinds.setdefault(s["kind"], []).append(s)
        for k, ss in kinds.items():
            print(f"\n[{k}]")
            for s in ss:
                t = " (글자 박힘)" if s["has_text"] else ""
                print(f"  {s['id']:<22} {s['w']}x{s['h']}  {s['use_when']}{t}  | 피할 때: {s['avoid']}")
        print(f"\n미리보기: {os.path.join(STK_DIR, '_preview.png')}")
        return
    if not a.plan:
        print(__doc__)
        sys.exit(2)
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.plan)), "visuals")
    os.makedirs(out, exist_ok=True)
    rep = Report()
    pkg = None
    if a.package:
        with open(a.package, encoding="utf-8") as f:
            raw = f.read()
        # 기사 내용 섹션만 대조 (목차 번호·JSON-LD·슬러그 제외)
        secs = re.findall(r"<!--\s*BEGIN:(\w+)\s*-->(.*?)<!--\s*END:\1\s*-->", raw, re.S)
        pkg = "\n".join(body for name, body in secs if name not in ("jsonld", "slug", "visuals")) if secs else raw
    lint_plan(plan, cat, rep, pkg)
    if korean_font_ok() is False:
        rep.add("FAIL", "-", "FONT", "한글 글꼴 없음 — 글자가 네모로 깨짐. fonts-noto-cjk 설치 필요")
    th = THEMES.get(plan.get("theme", "cream"), THEMES["cream"])
    jobs, usage = [], {}
    for sp in plan.get("images", []):
        iid = sp.get("id") or sp.get("type")
        if a.only and iid not in a.only:
            continue
        if sp.get("type") not in BUILDERS:
            continue
        sth = THEMES.get(sp.get("theme", plan.get("theme", "cream")), th)
        for k in ("source", "brand"):
            sp.setdefault(k, plan.get(k))
        c = Ctx(cat, rep, iid)
        if sp["type"] == "thumbnail":
            sp["_format"] = thumb_format(sp, plan) if thumb_format(sp, plan) in THUMB_FORMATS else "landscape"
        W, H, body = BUILDERS[sp["type"]](c, sp, sth)
        hp = os.path.join(out, f"{iid}.html")
        doc = page_html(W, H, body, sth, sp.get("title", iid))
        with open(hp, "w", encoding="utf-8") as f:
            f.write(doc)
        jobs.append({"id": iid, "W": W, "H": H, "html": doc, "html_path": hp, "png": os.path.join(out, f"{iid}.png")})
        usage[iid] = {"type": sp["type"], "file": f"visuals/{iid}.png", "alt": sp.get("alt", ""),
                      "format": sp.get("_format", "landscape"), "stickers": c.used, "size": [W, H]}
    render(jobs, rep)
    for j in jobs:
        if "height" in j:
            usage[j["id"]]["size"] = [j["W"], j["H"] or j["height"]]
        if not os.path.exists(j["png"]):
            usage[j["id"]]["file"] = None
    report = {"images": usage, "checks": rep.items,
              "summary": {lv: sum(1 for i in rep.items if i["level"] == lv) for lv in ("FAIL", "WARN")}}
    with open(os.path.join(out, "visuals-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    for it in sorted(rep.items, key=lambda x: x["level"] != "FAIL"):
        print(f"[{it['level']}] {it['image']} {it['code']}: {it['msg']}")
    for iid, u in usage.items():
        ids = ", ".join(f"{s['id']}×{s['scale']}" for s in u["stickers"])
        print(f"[OK] {iid}: {u['file'] or '(PNG 없음)'} {u['size'][0]}x{u['size'][1]} | 스티커: {ids}")
    print(f"\n요약: FAIL {report['summary']['FAIL']} / WARN {report['summary']['WARN']} → "
          + ("수정 필요" if rep.failed else "이미지 점검 통과"))
    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()

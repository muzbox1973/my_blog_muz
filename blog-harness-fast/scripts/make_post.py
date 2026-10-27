#!/usr/bin/env python3
"""기사 패키지 → 블로그에 그대로 붙여 넣는 '인라인 스타일 HTML' + 제목·해시태그 + 복사 버튼 미리보기.

사용법:
    python3 make_post.py article-package.md                    # 초안 (남은 표식은 노란색으로 표시)
    python3 make_post.py article-package.md --final --png      # 발행본 (표식·로컬 이미지 경로가 남으면 FAIL)
    python3 make_post.py article-package.md --h2 highlight     # H2 스타일: badge(기본) · highlight · band

만드는 파일 (패키지와 같은 폴더):
    post-google.html     워드프레스 '사용자 정의 HTML' 블록·티스토리 HTML 모드에 붙여 넣는 본문 (맨 앞에 대표 썸네일)
                         (<style>·<script>·class 없이 모든 스타일을 style 속성에 넣음, 이미지는 저장소 주소)
    titles-hashtags.md   추천 제목·제목 후보·메타설명·슬러그·해시태그·태그·대표 썸네일 주소 (따로 제공)
    preview.html         복사 버튼이 있는 미리보기 (HTML 코드 복사 / 서식째 복사 / 제목·해시태그 복사)
    preview.png          (--png) 구글판 미리보기 전체 캡처
이미지 주소: 같은 폴더의 assets-urls.json(repo_sync.py가 만듦) → 없으면 로컬 경로(초안 WARN, --final FAIL).
종료코드: 0 / 1(FAIL 있음). 렌더(--png) 외에는 표준 라이브러리만 사용한다.
"""
import argparse
import base64
import html
import json
import os
import re
import struct
import sys
from pathlib import Path
from _local_paths import contained_path

MARKER_RE = r"\[(?:확인 필요|경험 보강 필요|근거 보강 필요|사람 확인)[^\]]*\]"
EXCLUDED_H2 = ("자주 묻는 질문", "FAQ", "마무리", "정리", "결론", "참고")

PALETTES = {
    "cream": dict(ink="#1f2633", text="#2b2f36", sub="#5b6475", accent="#f2b632", accent_dark="#a8740a",
                  soft="#fff1c9", tint="#fffaf0", line="#ece3cf", link="#1f6feb"),
    "sky":   dict(ink="#152238", text="#26303f", sub="#4c5d78", accent="#3d7be0", accent_dark="#2858a8",
                  soft="#dcebfd", tint="#f3f8ff", line="#d6e4f5", link="#1f6feb"),
    "mint":  dict(ink="#17302a", text="#24332e", sub="#4d6a60", accent="#2f9e6e", accent_dark="#217552",
                  soft="#d9f2e4", tint="#f2fbf6", line="#d3eadc", link="#17795a"),
    "navy":  dict(ink="#1f2a44", text="#2a3245", sub="#55607a", accent="#ffb92e", accent_dark="#a87500",
                  soft="#fff0cf", tint="#f5f7fb", line="#dfe4ee", link="#2a5bd7"),
}


class Rep:
    def __init__(self):
        self.items = []

    def add(self, lv, code, msg):
        self.items.append((lv, code, msg))

    @property
    def failed(self):
        return any(lv == "FAIL" for lv, _, _ in self.items)


def esc(s):
    return html.escape(str(s or ""), quote=False)


def attr(s):
    return html.escape(str(s or ""), quote=True)


def sections(text):
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"<!--\s*BEGIN:(\w+)\s*-->(.*?)<!--\s*END:\1\s*-->", text, re.S)}


def png_size(path):
    """PNG·WebP 가로세로 크기 (표준 라이브러리만 사용)."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            kind = head[12:16]
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", head[26:30])
                return (w & 0x3FFF, h & 0x3FFF)
            if kind == b"VP8L":
                b = struct.unpack("<I", head[21:25])[0]
                return ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
            if kind == b"VP8X":
                return (int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1)
    except (OSError, struct.error):
        pass
    return None


# ------------------------------------------------------------------ 이미지 주소
class Assets:
    def __init__(self, base, rep, final):
        self.base, self.rep, self.final = base, rep, final
        p = os.path.join(base, "assets-urls.json")
        self.map = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        self.files = self.map.get("files", {})
        self.local_used = []
        self.missing = []
        fails = (self.map.get("check") or {}).get("fail") or []
        if fails:
            rep.add("WARN", "URL_CHECK", f"저장소 주소 확인 실패 {len(fails)}건 — 공개 저장소인지 확인 (repo_sync.py)")
        if not self.map:
            rep.add("FAIL" if final else "WARN", "NO_URLS",
                    "assets-urls.json 없음 — 이미지가 로컬 경로라 블로그에 붙이면 안 보임. repo_sync.py publish 먼저")

    def url(self, rel):
        rel = rel.strip()
        if re.match(r"^https?://", rel):
            return rel
        key = os.path.normpath(rel).replace(os.sep, "/")
        if not os.path.exists(contained_path(self.base, key)):
            self.missing.append(key)
        if key in self.files:
            return self.files[key]
        self.local_used.append(key)
        return key

    def data_uri(self, rel):
        p = contained_path(self.base, rel)
        if not os.path.exists(p):
            return None
        ext = os.path.splitext(p)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "gif": "gif"}.get(ext, "png")
        return f"data:image/{mime};base64," + base64.b64encode(open(p, "rb").read()).decode()


# ------------------------------------------------------------------ 인라인 스타일
class Style:
    def __init__(self, pal, h2):
        self.p, self.h2kind, self.n = pal, h2, 0

    def wrap(self, inner):
        p = self.p
        return (f'<div style="max-width:760px;margin:0 auto;font-size:17px;line-height:1.85;color:{p["text"]};'
                f'word-break:keep-all;overflow-wrap:break-word;">\n{inner}\n</div>')

    def h2(self, text_html, raw):
        p = self.p
        special = next((x for x in EXCLUDED_H2 if x in raw), None)
        if special:
            label = "Q&amp;A" if special in ("자주 묻는 질문", "FAQ") else "정리" if special in ("마무리", "정리", "결론") else "참고"
        else:
            self.n += 1
            label = f"{self.n:02d}"
        if self.h2kind == "highlight":
            kicker = label if special else f"POINT {label}"
            return (f'<h2 style="margin:56px 0 18px;font-size:25px;line-height:1.45;font-weight:800;color:{p["ink"]};letter-spacing:-0.01em;">'
                    f'<span style="display:block;margin-bottom:6px;font-size:13px;font-weight:800;letter-spacing:0.14em;color:{p["accent_dark"]};">{kicker}</span>'
                    f'<span style="background:linear-gradient(transparent 58%,{p["soft"]} 58%);padding:0 4px;">{text_html}</span></h2>')
        if self.h2kind == "band":
            return (f'<h2 style="margin:56px 0 22px;padding:18px 22px;font-size:23px;line-height:1.45;font-weight:800;color:#ffffff;'
                    f'background:{p["ink"]};border-radius:14px;box-shadow:0 6px 0 {p["accent"]};letter-spacing:-0.01em;">'
                    f'<span style="margin-right:12px;color:{p["accent"]};font-weight:900;">{label}</span>{text_html}</h2>')
        # badge (기본): 번호 배지 + 왼쪽 굵은 선 + 은은한 그라데이션
        return (f'<h2 style="margin:56px 0 20px;padding:15px 20px 15px 18px;font-size:24px;line-height:1.45;font-weight:800;'
                f'color:{p["ink"]};background:linear-gradient(90deg,{p["soft"]} 0%,{p["tint"]} 65%,rgba(255,255,255,0) 100%);'
                f'border-left:6px solid {p["accent"]};border-radius:0 14px 14px 0;letter-spacing:-0.01em;">'
                f'<span style="display:inline-block;margin-right:12px;padding:2px 11px;border-radius:999px;background:{p["ink"]};'
                f'color:#ffffff;font-size:14px;font-weight:800;letter-spacing:0.04em;vertical-align:3px;">{label}</span>{text_html}</h2>')

    def h3(self, t):
        return (f'<h3 style="margin:34px 0 12px;font-size:20px;line-height:1.5;font-weight:800;color:{self.p["ink"]};">'
                f'<span style="color:{self.p["accent"]};margin-right:8px;">▍</span>{t}</h3>')

    def p_(self, t):
        return f'<p style="margin:0 0 18px;">{t}</p>'

    def ul(self, items, ordered=False):
        tag = "ol" if ordered else "ul"
        lis = "".join(f'<li style="margin:0 0 8px;padding-left:2px;">{x}</li>' for x in items)
        return f'<{tag} style="margin:0 0 22px;padding-left:24px;">{lis}</{tag}>'

    def callout(self, title, items):
        p = self.p
        lis = "".join(f'<li style="margin:0 0 6px;">{x}</li>' for x in items)
        return (f'<div style="margin:8px 0 30px;padding:20px 24px 14px;background:{p["tint"]};border:2px solid {p["line"]};border-radius:16px;">'
                f'<p style="margin:0 0 10px;font-size:15px;font-weight:800;color:{p["accent_dark"]};letter-spacing:0.04em;">✔ {title}</p>'
                f'<ul style="margin:0;padding-left:22px;">{lis}</ul></div>')

    def table(self, head, rows):
        p = self.p
        th = "".join(f'<th style="padding:11px 12px;border:1px solid {p["line"]};background:{p["tint"]};font-weight:800;text-align:left;color:{p["ink"]};">{h}</th>' for h in head)
        trs = "".join("<tr>" + "".join(f'<td style="padding:11px 12px;border:1px solid {p["line"]};vertical-align:top;">{c}</td>' for c in r) + "</tr>" for r in rows)
        return (f'<div style="margin:0 0 26px;overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:15.5px;line-height:1.6;">'
                f'<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')

    def quote(self, t):
        p = self.p
        return (f'<blockquote style="margin:0 0 24px;padding:14px 20px;border-left:5px solid {p["accent"]};background:{p["tint"]};'
                f'border-radius:0 12px 12px 0;color:{p["ink"]};">{t}</blockquote>')

    def figure(self, url, alt, size):
        wh = f' width="{size[0]}" height="{size[1]}"' if size else ""
        return (f'<figure style="margin:30px 0;padding:0;"><img src="{attr(url)}" alt="{attr(alt)}"{wh} loading="lazy" '
                f'style="display:block;width:100%;max-width:100%;height:auto;margin:0 auto;border-radius:14px;"></figure>')

    def faq(self, pairs):
        p = self.p
        out = []
        for q, a in pairs:
            out.append(f'<div style="margin:0 0 14px;padding:16px 20px;border:1px solid {p["line"]};border-radius:14px;background:#ffffff;">'
                       f'<p style="margin:0 0 8px;font-weight:800;color:{p["ink"]};"><span style="color:{p["accent_dark"]};margin-right:8px;">Q.</span>{q}</p>'
                       f'<p style="margin:0;color:{p["text"]};"><span style="color:{p["sub"]};font-weight:800;margin-right:8px;">A.</span>{a}</p></div>')
        return "".join(out)

    def author(self, t):
        p = self.p
        return (f'<p style="margin:36px 0 0;padding-top:16px;border-top:1px dashed {p["line"]};font-size:14px;color:{p["sub"]};">{t}</p>')

    def refs(self, items):
        p = self.p
        lis = "".join(f'<li style="margin:0 0 4px;">{x}</li>' for x in items)
        return (f'<div style="margin:30px 0 0;padding:16px 20px;background:{p["tint"]};border-radius:12px;font-size:14px;color:{p["sub"]};">'
                f'<p style="margin:0 0 8px;font-weight:800;color:{p["ink"]};">참고자료</p><ol style="margin:0;padding-left:20px;">{lis}</ol></div>')

    def photo_slot(self, t):
        return (f'<div style="margin:24px 0;padding:18px;border:2px dashed #b8b1a0;border-radius:12px;text-align:center;'
                f'font-size:14px;color:{self.p["sub"]};">📷 사진 자리 — {t}</div>')


# ------------------------------------------------------------------ 마크다운 → 인라인 HTML
def inline(s, st, rep, final, a_urls):
    t = esc(s)
    t = re.sub(r"\s*\[근거#\d+\]", "", t)  # 내부 근거 번호는 게시본에서 뺀다 (참고자료 목록으로 대체)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: f'<a href="{attr(m.group(2))}" target="_blank" rel="noopener" style="color:{st.p["link"]};text-decoration:underline;">{m.group(1)}</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: f'<strong style="font-weight:800;color:{st.p["ink"]};">{m.group(1)}</strong>', t)
    t = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r'<code style="padding:1px 6px;border-radius:5px;background:#f2f2f2;font-size:0.92em;">\1</code>', t)

    def mark(m):
        rep.add("FAIL" if final else "WARN", "TEMP_MARKER", f"표식 남음: {html.unescape(m.group(0))[:40]}")
        return f'<mark style="background:#fff1a8;padding:0 3px;">{m.group(0)}</mark>'
    t = re.sub(MARKER_RE, mark, t)
    return t


def render_body(md, st, assets, rep, final, faq_pairs, keep_h1=False):
    out, para, lines, i = [], [], md.splitlines(), 0
    IN = lambda x: inline(x, st, rep, final, assets)  # noqa: E731
    skip_faq_body = False

    def flush():
        if para:
            txt = " ".join(para).strip()
            if re.fullmatch(r"\*[^*].*[^*]\*", txt) and ("작성" in txt or "수정" in txt):
                out.append(st.author(IN(txt.strip("*"))))
            else:
                out.append(st.p_(IN(" ".join(para))))
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush(); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush(); n, txt = len(m.group(1)), m.group(2)
            skip_faq_body = False
            if n == 1:
                if keep_h1:
                    out.append(f'<h1 style="margin:0 0 24px;font-size:30px;line-height:1.35;font-weight:900;color:{st.p["ink"]};">{IN(txt)}</h1>')
            elif n == 2:
                out.append(st.h2(IN(txt), txt))
                if any(x in txt for x in ("자주 묻는 질문", "FAQ")) and faq_pairs:
                    out.append(st.faq([(IN(q), IN(a)) for q, a in faq_pairs]))
                    skip_faq_body = True  # "아래 FAQ 섹션과 동일" 같은 안내문은 건너뜀
            else:
                out.append(st.h3(IN(txt)))
            i += 1; continue
        if skip_faq_body:
            i += 1; continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$", s)
        if m:
            flush()
            rel = m.group(2)
            out.append(st.figure(assets.url(rel), m.group(1), png_size(os.path.join(assets.base, rel))))
            i += 1; continue
        if s.startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
            if body:
                out.append(st.table([IN(c) for c in body[0]], [[IN(c) for c in r] for r in body[1:]]))
            continue
        if re.match(r"^([-*]|\d+[.)])\s+", s):
            ordered = bool(re.match(r"^\d", s)); items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+[.)])\s+", lines[i]):
                items.append(IN(re.sub(r"^\s*([-*]|\d+[.)])\s+", "", lines[i]))); i += 1
            # 바로 앞 문단이 굵은 제목 한 줄이면 요약 상자로
            if para and re.fullmatch(r"\*\*[^*]+\*\*", " ".join(para).strip()):
                title = IN(" ".join(para).strip().strip("*")); para.clear()
                out.append(st.callout(title, items))
            else:
                flush(); out.append(st.ul(items, ordered))
            continue
        if s.startswith(">"):
            flush(); q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(IN(lines[i].strip().lstrip(">").strip())); i += 1
            out.append(st.quote("<br>".join(q))); continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            flush(); out.append(f'<hr style="margin:36px 0;border:0;border-top:1px solid {st.p["line"]};">'); i += 1; continue
        para.append(s); i += 1
    flush()
    return "\n".join(out)


def faq_pairs(faq):
    qs = re.findall(r"^Q[.:]\s*(.+)$", faq or "", re.M)
    ans = re.findall(r"^A[.:]\s*(.+)$", faq or "", re.M)
    return list(zip(qs, ans))


def references(text):
    m = re.search(r"^##\s*\d*\.?\s*참고자료.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return []
    items = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip() for l in m.group(1).splitlines() if re.match(r"^\s*\d+[.)]\s+", l)]
    return [x for x in items if x and "{" not in x]


def lint_fragment(name, frag, rep, final):
    for pat, what in ((r"<style", "<style>"), (r"<script", "<script>"), (r"\sclass=", "class 속성"), (r"<link", "<link>")):
        if re.search(pat, frag, re.I):
            rep.add("FAIL", "INLINE", f"{name}에 {what} 있음 — 블로그에 붙이면 사라지거나 막힘")
    local = [s for s in re.findall(r'<img src="([^"]+)"', frag) if not s.startswith("https://")]
    if local:
        rep.add("FAIL" if final else "WARN", "LOCAL_IMG",
                f"{name}: 저장소 주소가 아닌 이미지 {len(local)}개 ({local[0]}) — repo_sync.py publish 후 다시 생성")


# ------------------------------------------------------------------ 제목·해시태그
def titles_hashtags(sec, assets, rows):
    titles = [re.sub(r"^\s*\d+[.)]\s*", "", t).strip() for t in sec.get("titles", "").splitlines() if t.strip()]
    rec = next((t.replace("★", "").strip() for t in titles if "★" in t), titles[0] if titles else "")
    others = [t for t in (x.replace("★", "").strip() for x in titles) if t != rec]
    md, slug = sec.get("meta_description", ""), sec.get("slug", "")
    tags = re.findall(r"#[^\s#]+", sec.get("tags") or sec.get("naver_tags", ""))
    plain = [t.lstrip("#") for t in tags]
    thumb = next((r for r in rows if r["type"] == "thumbnail"), None)
    thumb_url = assets.url(thumb["file"]) if thumb else ""
    lines = ["# 발행 정보", "",
             "## 추천 제목", f"{rec}  ({len(rec)}자)", "",
             "## 다른 제목 후보"] + [f"- {t}  ({len(t)}자)" for t in others] + ["",
             "## 메타설명 (구글·워드프레스 SEO 칸)", md, "",
             "## 슬러그 (주소)", slug, "",
             "## 해시태그 (SNS 공유용)", " ".join(tags), "",
             "## 태그 (워드프레스·티스토리, 쉼표 구분)", ", ".join(plain), "",
             "## 대표 썸네일", thumb_url or "(없음)", ""]
    return "\n".join(lines), {"rec": rec, "others": others, "meta": md, "slug": slug, "tags": tags, "plain": plain,
                              "thumb": thumb_url, "thumb_file": thumb["file"] if thumb else None}


def visuals_rows(vis):
    rows = []
    for line in (vis or "").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 5 or c[0] == "위치" or set(c[0]) <= set("-: "):
            continue
        rows.append({"pos": c[0], "file": c[1].strip("`"), "type": c[2], "stickers": c[3], "alt": c[4]})
    return rows


# ------------------------------------------------------------------ 미리보기 페이지
PAGE_CSS = """
:root{--bg:#f1eee7;--ink:#1f2633;--sub:#5b6475;--line:#e3ddcf;--acc:#f2b632}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font-family:"Pretendard","Noto Sans KR","Noto Sans CJK KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif;line-height:1.6}
.pv-top{position:sticky;top:0;z-index:9;background:#1f2633;color:#fff;padding:10px 16px}
.pv-top .in{max-width:1040px;margin:0 auto;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;justify-content:space-between}
.pv-tabs{display:flex;flex-wrap:wrap;gap:6px}.pv-tabs button{font:inherit;font-size:14px;border:1px solid #566;background:transparent;color:#fff;padding:5px 12px;border-radius:999px;cursor:pointer}
.pv-tabs button[aria-selected=true]{background:var(--acc);border-color:var(--acc);color:#1f2633;font-weight:700}
.pv-wrap{max-width:1040px;margin:0 auto;padding:20px 16px 80px}.pv-panel{display:none}.pv-panel.on{display:block}
.pv-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.pv-btn{font:inherit;font-size:14px;font-weight:700;border:0;border-radius:10px;padding:9px 14px;cursor:pointer;background:#1f2633;color:#fff}
.pv-btn.alt{background:#fff;color:#1f2633;border:1px solid var(--line)}.pv-note{font-size:13px;color:var(--sub)}
.pv-paper{background:#fff;border:1px solid var(--line);border-radius:14px;padding:36px clamp(16px,4vw,48px)}
.pv-code{display:none;width:100%;height:280px;font:12px/1.5 ui-monospace,Consolas,monospace;border:1px solid var(--line);border-radius:10px;padding:10px;margin:0 0 12px}
.pv-code.on{display:block}
.pv-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 14px}
.pv-lab{font-size:12px;font-weight:800;color:var(--sub);letter-spacing:.04em;margin:0 0 8px}
.pv-row{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;padding:8px 0;border-top:1px solid #f0ece3}
.pv-row:first-of-type{border-top:0}.pv-row .t{flex:1;min-width:0;word-break:break-all}.pv-row .n{font-size:12px;color:var(--sub);white-space:nowrap}
.pv-mini{font:inherit;font-size:12px;font-weight:700;border:1px solid var(--line);background:#faf8f3;border-radius:8px;padding:4px 10px;cursor:pointer;white-space:nowrap}
.pv-warn{background:#fff6e0;border:1px solid #f0d58a;border-radius:12px;padding:12px 16px;margin:0 0 14px;font-size:14px}
.pv-warn li{margin:2px 0}.pv-gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.pv-gal img{width:100%;border-radius:10px;border:1px solid var(--line)}.pv-gal .m{font-size:12.5px;color:var(--sub);margin-top:6px;word-break:break-all}
.pv-badge{display:inline-block;font-size:12px;border-radius:6px;padding:1px 7px;margin-left:6px;background:#e9f6ee;color:#1d6b43}
.pv-badge.local{background:#fff1d6;color:#8a5a00}
.pv-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#1f2633;color:#fff;padding:10px 16px;border-radius:10px;font-size:14px;opacity:0;transition:opacity .2s;pointer-events:none}
.pv-toast.on{opacity:1}
"""

PAGE_JS = r"""
const LOCAL = __LOCAL__;
const $ = s => document.querySelector(s);
function toast(t){const e=$('.pv-toast');e.textContent=t;e.classList.add('on');setTimeout(()=>e.classList.remove('on'),1600);}
async function copyText(t){try{await navigator.clipboard.writeText(t);return true;}catch(e){const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();const ok=document.execCommand('copy');a.remove();return ok;}}
function mount(tplId, hostId){
  const host=$(hostId), frag=document.importNode($(tplId).content,true);
  frag.querySelectorAll('img').forEach(img=>{
    const orig=img.getAttribute('src'); img.dataset.orig=orig;
    img.addEventListener('error',()=>{ if(LOCAL[orig] && img.src!==LOCAL[orig]){ img.src=LOCAL[orig]; img.dataset.local='1'; flag(orig,false);} },{once:true});
    img.addEventListener('load',()=>{ if(!img.dataset.local) flag(orig,true); });
  });
  host.appendChild(frag);
}
function flag(url,ok){document.querySelectorAll('[data-url="'+CSS.escape(url)+'"]').forEach(b=>{b.textContent=ok?'저장소 주소 열림':'저장소 주소 안 열림 → 로컬 사본 표시';b.classList.toggle('local',!ok);});}
function copyRich(hostId){
  const host=$(hostId); const swapped=[];
  host.querySelectorAll('img[data-local]').forEach(i=>{swapped.push([i,i.src]); i.src=i.dataset.orig;}); // 붙여 넣을 땐 저장소 주소로
  const r=document.createRange(); r.selectNodeContents(host); const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  const ok=document.execCommand('copy'); s.removeAllRanges(); swapped.forEach(([i,src])=>i.src=src); return ok;
}
document.querySelectorAll('.pv-tabs button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.pv-tabs button').forEach(x=>x.setAttribute('aria-selected',x===b));
  document.querySelectorAll('.pv-panel').forEach(p=>p.classList.toggle('on',p.id===b.dataset.t)); scrollTo(0,0);}));
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-act]'); if(!b) return; const act=b.dataset.act;
  if(act==='code'){ const ok=await copyText($(b.dataset.src).value); toast(ok?'HTML 코드를 복사했어요':'복사 실패 — 코드 보기에서 직접 복사'); }
  else if(act==='rich'){ toast(copyRich(b.dataset.src)?'서식째 복사했어요 — 에디터에 붙여 넣으세요':'복사 실패'); }
  else if(act==='text'){ const ok=await copyText(b.dataset.text); toast(ok?'복사했어요':'복사 실패'); }
  else if(act==='show'){ $(b.dataset.src).classList.toggle('on'); }
});
mount('#tpl-g','#host-g');
document.querySelectorAll('[data-url]').forEach(b=>{const u=b.dataset.url; if(!/^https?:/.test(u)){b.textContent='로컬 경로 (저장소에 아직 안 올림)';b.classList.add('local');return;}
  const im=new Image(); im.onload=()=>flag(u,true); im.onerror=()=>flag(u,false); im.src=u;});
"""


def copy_btn(text, label="복사"):
    return f'<button class="pv-mini" data-act="text" data-text="{attr(text)}">{label}</button>'


def build_page(google, info, rows, assets, warns, local_map, status):
    th_rows = "".join(
        f'<div class="pv-row"><div class="t">{"★ " if i == 0 else ""}{esc(t)}</div><span class="n">{len(t)}자</span>{copy_btn(t)}</div>'
        for i, t in enumerate([info["rec"]] + info["others"]))
    tags_html = (f'<div class="pv-row"><div class="t">{esc(" ".join(info["tags"]))}</div>{copy_btn(" ".join(info["tags"]), "모두 복사")}</div>'
                 if info["tags"] else '<div class="pv-row"><div class="t">(없음)</div></div>')
    plain_html = (f'<div class="pv-row"><div class="t">{esc(", ".join(info["plain"]))}</div>{copy_btn(", ".join(info["plain"]), "모두 복사")}</div>'
                  if info["plain"] else "")
    thumb_html = ""
    if info["thumb_file"]:
        src = info["thumb"] if info["thumb"].startswith("http") else (assets.data_uri(info["thumb_file"]) or "")
        size = png_size(os.path.join(assets.base, info["thumb_file"]))
        thumb_html = (f'<div class="pv-card"><p class="pv-lab">대표 썸네일 {f"{size[0]}×{size[1]}" if size else ""}'
                      f'<span class="pv-badge" data-url="{attr(info["thumb"])}">확인 중</span></p>'
                      f'<img src="{attr(local_map.get(info["thumb"], src))}" alt="" style="max-width:min(100%,520px);border-radius:10px;border:1px solid #e3ddcf">'
                      f'<div class="pv-row"><div class="t">{esc(info["thumb"])}</div>{copy_btn(info["thumb"], "주소 복사")}</div></div>')
    gal = []
    for r in rows:
        url = assets.files.get(r["file"], r["file"])
        local = assets.data_uri(r["file"])
        size = png_size(os.path.join(assets.base, r["file"]))
        gal.append(f'<div class="pv-card"><img src="{attr(local or "")}" alt="{attr(r["alt"])}"><div class="m"><b>{esc(r["pos"])}</b> · {esc(r["type"])}'
                   f'{f" · {size[0]}×{size[1]}" if size else ""}<span class="pv-badge" data-url="{attr(url)}">확인 중</span>'
                   f'<br>스티커: {esc(r["stickers"])}<br>alt: {esc(r["alt"])}<br>{esc(url)}</div>'
                   f'<div style="margin-top:8px">{copy_btn(url, "주소 복사")}</div></div>')
    warn_html = ("<div class='pv-warn'><b>확인할 것</b><ul>" + "".join(f"<li>{esc(w)}</li>" for w in warns) + "</ul></div>") if warns else ""
    js = PAGE_JS.replace("__LOCAL__", json.dumps(local_map).replace("<", "\\u003c"))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>게시 미리보기 – {esc(info['rec'])}</title><style>{PAGE_CSS}</style></head><body>
<div class="pv-top"><div class="in"><div><b>게시 미리보기</b> <span style="font-size:13px;opacity:.8">{esc(status)}</span></div>
<div class="pv-tabs"><button data-t="g" aria-selected="true">구글·워드프레스·티스토리</button><button data-t="t" aria-selected="false">제목·해시태그</button><button data-t="v" aria-selected="false">이미지</button></div></div></div>
<div class="pv-wrap">{warn_html}
<section class="pv-panel on" id="g">
<div class="pv-bar"><button class="pv-btn" data-act="code" data-src="#code-g">HTML 코드 복사</button>
<button class="pv-btn alt" data-act="rich" data-src="#host-g">서식째 복사</button><button class="pv-btn alt" data-act="show" data-src="#code-g">코드 보기</button>
<span class="pv-note">워드프레스: '사용자 정의 HTML' 블록 · 티스토리: HTML 모드에 붙여 넣기. 제목은 제목 칸에 따로.</span></div>
<textarea class="pv-code" id="code-g" readonly>{esc(google)}</textarea>
<div class="pv-paper" id="host-g"></div><template id="tpl-g">{google}</template></section>
<section class="pv-panel" id="t">
<div class="pv-card"><p class="pv-lab">추천 제목 · 후보</p>{th_rows}</div>
<div class="pv-card"><p class="pv-lab">메타설명 ({len(info['meta'])}자)</p><div class="pv-row"><div class="t">{esc(info['meta'])}</div>{copy_btn(info['meta'])}</div></div>
<div class="pv-card"><p class="pv-lab">슬러그</p><div class="pv-row"><div class="t">{esc(info['slug'])}</div>{copy_btn(info['slug'])}</div></div>
<div class="pv-card"><p class="pv-lab">해시태그 (SNS 공유용)</p>{tags_html}</div>
<div class="pv-card"><p class="pv-lab">태그 (워드프레스·티스토리)</p>{plain_html}</div>{thumb_html}</section>
<section class="pv-panel" id="v"><div class="pv-gal">{''.join(gal)}</div></section>
</div><div class="pv-toast"></div><script>{js}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="블로그 게시용 인라인 HTML·제목·해시태그·미리보기 생성")
    ap.add_argument("package")
    ap.add_argument("--final", action="store_true", help="발행본: 표식·로컬 이미지가 남으면 FAIL")
    ap.add_argument("--h2", choices=["badge", "highlight", "band"], default="badge", help="H2 제목 스타일")
    ap.add_argument("--theme", help="색 테마 (기본: visual-plan.json의 theme 또는 cream)")
    ap.add_argument("--keep-h1", action="store_true", help="본문에 H1 제목도 넣기 (기본: 제목 칸에 따로 넣으므로 뺌)")
    ap.add_argument("--no-thumb", action="store_true", help="대표 썸네일을 본문 맨 앞에 넣지 않기 (기본: 넣음)")
    ap.add_argument("--no-refs", action="store_true", help="참고자료 목록 넣지 않기")
    ap.add_argument("--png", action="store_true", help="preview.png 캡처 (Playwright 필요)")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.package))
    text = open(a.package, encoding="utf-8").read()
    sec = sections(text)
    rep = Rep()
    theme = a.theme
    vp = os.path.join(base, "visual-plan.json")
    if not theme and os.path.exists(vp):
        try:
            theme = json.load(open(vp, encoding="utf-8")).get("theme")
        except Exception:  # noqa: BLE001
            pass
    pal = PALETTES.get(theme or "cream", PALETTES["cream"])
    assets = Assets(base, rep, a.final)

    rows = visuals_rows(sec.get("visuals"))
    thumb = next((r for r in rows if r["type"] == "thumbnail"), None)

    def thumb_fig(style):  # 대표 썸네일: 본문 맨 앞 (플랫폼이 첫 이미지를 대표 이미지로 쓰는 경우가 많음)
        if a.no_thumb or not thumb:
            return ""
        return style.figure(assets.url(thumb["file"]), thumb["alt"], png_size(os.path.join(base, thumb["file"]))) + "\n"
    if not thumb and not a.no_thumb:
        rep.add("FAIL" if a.final else "WARN", "THUMB", "이미지 표에 대표 썸네일(thumbnail)이 없어 본문 맨 앞에 넣지 못함")

    st = Style(pal, a.h2)
    body = thumb_fig(st) + render_body(sec.get("body_google", ""), st, assets, rep, a.final, faq_pairs(sec.get("faq")), a.keep_h1)
    refs = [] if a.no_refs else references(text)
    if refs:
        body += "\n" + st.refs([inline(r, st, rep, a.final, assets) for r in refs])
    google = st.wrap(body)
    lint_fragment("post-google.html", google, rep, a.final)

    th_md, info = titles_hashtags(sec, assets, rows)
    if not info["rec"]:
        rep.add("FAIL", "TITLE", "추천 제목 없음")
    if not info["tags"]:
        rep.add("WARN", "TAGS", "태그 없음 (tags 섹션)")
    for m in dict.fromkeys(assets.missing):
        rep.add("FAIL", "MISSING_IMG", f"이미지 파일 없음: {m}")

    for name, content in (("post-google.html", google), ("titles-hashtags.md", th_md)):
        with open(os.path.join(base, name), "w", encoding="utf-8") as f:
            f.write(content + "\n")
    local_map = {}
    for rel, url in assets.files.items():
        d = assets.data_uri(rel)
        if d:
            local_map[url] = d
    for rel in set(assets.local_used):
        d = assets.data_uri(rel)
        if d:
            local_map[rel] = d
    warns = [m for lv, c, m in rep.items]
    status = (f"이미지 주소: {'저장소 ' + (assets.map.get('ref') or '')[:8] if assets.map else '로컬(아직 저장소에 안 올림)'}"
              f" · H2 {a.h2}")
    page = build_page(google, info, rows, assets, warns, local_map, status)
    hp = os.path.join(base, "preview.html")
    open(hp, "w", encoding="utf-8").write(page)

    if a.png:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                br = p.chromium.launch()
                pg = br.new_page(viewport={"width": 1100, "height": 900})
                pg.goto(Path(hp).resolve().as_uri())
                pg.evaluate("document.querySelectorAll('img').forEach(i=>i.loading='eager')")  # 지연 로딩 때문에 아래쪽 이미지가 비어 찍히는 문제 방지
                pg.wait_for_timeout(1500)
                pg.add_style_tag(content=".pv-top{position:static}")
                pg.screenshot(path=os.path.join(base, "preview.png"), full_page=True)
                br.close()
        except Exception as e:  # noqa: BLE001
            rep.add("WARN", "PNG", f"preview.png 캡처 실패 ({str(e)[:80]})")

    for lv, code, msg in sorted(rep.items, key=lambda x: x[0] != "FAIL"):
        print(f"[{lv}] {code}: {msg}")
    print(f"[post] post-google.html {len(google) // 1024}KB · titles-hashtags.md · preview.html"
          + (" · preview.png" if a.png and os.path.exists(os.path.join(base, 'preview.png')) else ""))
    print(f"[post] 추천 제목: {info['rec']}")
    print(f"[post] 해시태그: {' '.join(info['tags'])}")
    print("요약: " + ("수정 필요" if rep.failed else "게시 파일 준비됨"))
    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()

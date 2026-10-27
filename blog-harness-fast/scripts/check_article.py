#!/usr/bin/env python3
"""블로그 기사 패키지 기계 점검 (blog-seo-aeo-harness-fast, 구글판 전용).

사용법:
    python3 check_article.py article-package.md            # 초안 점검
    python3 check_article.py article-package.md --final    # 발행 직전 점검(임시 표식도 FAIL)
    python3 check_article.py article-package.md --json     # JSON 출력

이미지 표(BEGIN:visuals)가 있으면 썸네일·파일 존재·alt·본문 배치도 점검한다 (없으면 초안 WARN, --final FAIL).

결과: PASS / WARN / FAIL. FAIL이 하나라도 있으면 종료코드 1.
표준 라이브러리만 사용한다.
"""
import json
import os
import re
import struct
import sys
from _local_paths import contained_path


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

REQUIRED_SECTIONS = [
    "keywords", "titles", "meta_description", "slug",
    "body_google", "faq", "jsonld", "tags",
]
EXCLUDED_H2 = ("자주 묻는 질문", "FAQ", "마무리", "참고", "정리", "결론")
QUESTION_HINTS = ("?", "방법", "이유", "차이", "무엇", "뭔가", "어떻게", "얼마", "언제",
                  "왜", "어디", "누가", "할까", "인가요", "나요", "까요", "비교", "총정리")
DEMONSTRATIVE_STARTS = ("이것은", "이는", "그것은", "이건", "그건", "이 방법", "이렇게", "그래서")
TEMP_MARKERS = {"[근거#n]": r"\[근거#\d+\]", "[확인 필요]": r"\[확인 필요",
                "[경험 보강 필요]": r"\[경험 보강 필요", "[근거 보강 필요]": r"\[근거 보강 필요",
                "[사람 확인]": r"\[사람 확인"}


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, msg):
        self.items.append({"level": level, "code": code, "msg": msg})

    def ok(self, code, msg):
        self.add("PASS", code, msg)

    def warn(self, code, msg):
        self.add("WARN", code, msg)

    def fail(self, code, msg):
        self.add("FAIL", code, msg)

    @property
    def failed(self):
        return any(i["level"] == "FAIL" for i in self.items)


def sections(text):
    out = {}
    for m in re.finditer(r"<!--\s*BEGIN:(\w+)\s*-->(.*?)<!--\s*END:\1\s*-->", text, re.S):
        out[m.group(1)] = m.group(2).strip()
    return out


def plain_len(s):
    return len(re.sub(r"\s+", "", s))


def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`>#|]", "", s)
    return s.strip()


def split_sentences(s):
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)|(?<=요\.)", s)
    return [p.strip() for p in parts if p and p.strip()]


def check_visuals(r, sec, base_dir, final):
    """5단계 이미지 표(BEGIN:visuals): 썸네일 존재, 파일 존재, alt, 본문 배치."""
    vis = sec.get("visuals")
    fails_before = sum(1 for i in r.items if i["level"] == "FAIL")
    if vis is None:
        (r.fail if final else r.warn)("VISUALS", "이미지 섹션(BEGIN:visuals) 없음 — 5단계에서 썸네일·인포그래픽 추가"
                                     + (" (발행 전 필수)" if final else ""))
        return
    rows = []
    for line in vis.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or set(cells[0]) <= set("-: ") or cells[0] in ("위치",):
            continue
        rows.append({"pos": cells[0], "file": cells[1].strip("`"), "type": cells[2], "stickers": cells[3], "alt": cells[4]})
    if not rows:
        r.fail("VISUALS", "이미지 표에 행이 없음")
        return
    if not any(x["type"] == "thumbnail" for x in rows):
        r.fail("VISUALS_THUMB", "썸네일(type thumbnail) 행 없음")
    body = sec.get("body_google", "")
    for x in rows:
        if not x["alt"] or x["alt"] in ("-", "{alt}"):
            r.fail("VISUALS_ALT", f"{x['file']} alt 비어 있음")
        try:
            fp = contained_path(base_dir, x["file"]) if base_dir is not None else None
        except ValueError:
            r.fail("VISUALS_PATH", f"작업 폴더 밖 이미지 경로: {x['file']}")
            continue
        if fp and not os.path.exists(fp):
            r.fail("VISUALS_FILE", f"이미지 파일 없음: {x['file']}")
        elif fp and png_size(fp):  # 비율: 썸네일은 1:1 또는 16:9, 본문 이미지는 가로형(16:9)
            w, h = png_size(fp)
            if x["type"] == "thumbnail":
                if not (w == h or abs(w / h - 16 / 9) < 0.02):
                    r.fail("VISUALS_RATIO", f"썸네일 {w}×{h} — 정사각형(1:1)이나 가로형(16:9)이어야 함")
            elif not (w > h and abs(w / h - 16 / 9) < 0.02):
                r.fail("VISUALS_RATIO", f"{x['file']} {w}×{h} — 본문 이미지는 가로형(16:9)이어야 함")
        if x["type"] != "thumbnail" and x["file"] not in body:
            r.warn("VISUALS_PLACE", f"{x['file']}가 본문(구글판)에 배치되지 않음")
        if not x["stickers"] or x["stickers"] == "-":
            r.warn("VISUALS_STICKER", f"{x['file']}에 사용 스티커 기록 없음")
    if sum(1 for i in r.items if i["level"] == "FAIL") == fails_before:
        r.ok("VISUALS", f"이미지 {len(rows)}장 등록 (썸네일 포함)")


def check(text, final=False, base_dir=None):
    r = Report()
    sec = sections(text)
    check_visuals(r, sec, base_dir, final)

    # 0. 형식
    missing = [k for k in REQUIRED_SECTIONS if k not in sec and not (k == "tags" and "naver_tags" in sec)]
    if missing:
        r.fail("FORMAT", f"BEGIN/END 섹션 누락: {', '.join(missing)}")
    else:
        r.ok("FORMAT", "필수 섹션 모두 존재")

    for name, body in sec.items():
        if name == "jsonld":
            continue
        ph = re.findall(r"\{[가-힣A-Za-z0-9 _·/~]+\}", body)
        if ph:
            r.fail("PLACEHOLDER", f"[{name}] 템플릿 자리표시자 남음: {ph[:3]}")

    # 키워드
    core, subs = "", []
    kw = sec.get("keywords", "")
    m = re.search(r"핵심\s*[:：]\s*(.+)", kw)
    if m:
        core = m.group(1).strip()
    m = re.search(r"보조\s*[:：]\s*(.+)", kw)
    if m:
        subs = [s.strip() for s in re.split(r"[,，]", m.group(1)) if s.strip()]
    if not core:
        r.fail("KEYWORD", "핵심 키워드를 읽을 수 없음 ('핵심: ...' 형식 필요)")

    # 제목
    titles = sec.get("titles", "")
    rec = None
    for line in titles.splitlines():
        if "★" in line:
            rec = re.sub(r"^\s*\d+[.)]\s*", "", line).replace("★", "").strip()
    if not rec:
        r.warn("TITLE", "추천(★) 제목 없음")
    else:
        n = len(rec)
        (r.ok if 25 <= n <= 40 else r.warn)("TITLE_LEN", f"추천 제목 {n}자 (권장 25~40)")
        if core:
            pos = rec.find(core)
            if pos == -1:
                r.warn("TITLE_KW", "추천 제목에 핵심 키워드 없음")
            elif pos > len(rec) / 2:
                r.warn("TITLE_KW", "핵심 키워드가 제목 뒤쪽 절반에 있음")
            else:
                r.ok("TITLE_KW", "핵심 키워드가 제목 앞쪽에 있음")

    # 메타설명
    md = sec.get("meta_description", "")
    n = len(md)
    (r.ok if 80 <= n <= 120 else r.warn)("META_LEN", f"메타설명 {n}자 (권장 80~120)")
    if core and core not in md:
        r.warn("META_KW", "메타설명에 핵심 키워드 없음")

    # 슬러그
    slug = sec.get("slug", "")
    if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){2,5}", slug):
        r.ok("SLUG", f"슬러그 형식 적합: {slug}")
    else:
        r.warn("SLUG", f"슬러그 형식 확인 필요(영문 소문자·하이픈 3~6단어): '{slug}'")
    if re.search(r"20\d\d", slug):
        r.warn("SLUG_DATE", "슬러그에 연도 포함 — 갱신 시 URL 변경 위험")

    # 본문(구글판)
    body = sec.get("body_google", "")
    lines = body.splitlines()
    h1 = [l for l in lines if re.match(r"^#\s", l)]
    h2 = [l[3:].strip() for l in lines if re.match(r"^##\s", l)]
    if len(h1) != 1:
        r.warn("H1", f"H1 개수 {len(h1)} (1개 권장)")

    # 도입부: H1 다음 ~ 첫 H2 전, 첫 일반 단락
    intro_block = re.split(r"^##\s", body, maxsplit=1, flags=re.M)[0]
    intro_block = re.sub(r"^#\s.*$", "", intro_block, flags=re.M)
    paras = [p.strip() for p in re.split(r"\n\s*\n", intro_block) if p.strip()]
    paras = [p for p in paras if not p.startswith(("**핵심", "-", "*", ">"))] or paras
    intro = strip_md(paras[0]) if paras else ""
    if not intro:
        r.fail("ANSWER_FIRST", "첫 H2 이전 도입 단락 없음 (차단 B2)")
    else:
        n = len(intro)
        if 80 <= n <= 200:
            r.ok("ANSWER_FIRST_LEN", f"도입 단락 {n}자")
        elif n < 40:
            r.fail("ANSWER_FIRST_LEN", f"도입 단락 {n}자 — 직접 답으로 보기 어려움 (차단 B2)")
        else:
            r.warn("ANSWER_FIRST_LEN", f"도입 단락 {n}자 (권장 80~200)")
        if intro.startswith(DEMONSTRATIVE_STARTS):
            r.warn("ANSWER_FIRST_STANDALONE", "도입 첫 문장이 지시어로 시작 — 단독 인용 시 뜻이 안 통함")
        if core:
            if core in intro_block[:400] and core in strip_md(intro)[:100]:
                r.ok("KW_FIRST100", "핵심 키워드가 도입 100자 안에 있음")
            else:
                r.warn("KW_FIRST100", "핵심 키워드가 도입 100자 안에 없음")

    # H2
    content_h2 = [h for h in h2 if not any(x in h for x in EXCLUDED_H2)]
    if not 4 <= len(content_h2) <= 8:
        r.warn("H2_COUNT", f"본문 H2 {len(content_h2)}개 (권장 4~8, FAQ·마무리 제외)")
    else:
        r.ok("H2_COUNT", f"본문 H2 {len(content_h2)}개")
    if content_h2:
        q = [h for h in content_h2 if any(k in h for k in QUESTION_HINTS)]
        ratio = len(q) / len(content_h2)
        (r.ok if ratio >= 0.5 else r.warn)("H2_QUESTION", f"질문형 H2 비율 {ratio:.0%} (권장 50%↑)")

    # 목록·표
    list_blocks = len(re.findall(r"(?:^|\n)(?:[-*]|\d+\.)\s.+(?:\n(?:[-*]|\d+\.)\s.+)+", body))
    tables = len(re.findall(r"^\|.*\|\s*\n\|[\s:|-]+\|", body, re.M))
    (r.ok if list_blocks + tables >= 2 else r.warn)("STRUCTURE", f"목록 {list_blocks}개, 표 {tables}개 (합 2개↑ 권장)")

    # 저자·날짜
    if re.search(r"(최종\s*수정|수정일|업데이트)\s*[:：]?\s*20\d\d[-.]\d{1,2}[-.]\d{1,2}", body):
        r.ok("DATE", "최종 수정일 표시")
    else:
        r.warn("DATE", "본문에 최종 수정일(YYYY-MM-DD) 표시 없음")
    if not re.search(r"(작성|글)\s*[:：]", body):
        r.warn("AUTHOR", "본문에 저자 표시 없음")

    # 키워드 스터핑
    text_plain = strip_md(body)
    total = plain_len(text_plain)
    if core and total:
        cnt = text_plain.count(core)
        density = cnt * plain_len(core) / total
        msg = f"핵심 키워드 {cnt}회, 밀도 {density:.1%}"
        if density > 0.03:
            r.fail("STUFFING", msg + " — 3% 초과 (차단 B3)")
        elif density > 0.02:
            r.warn("STUFFING", msg + " — 2% 초과, 동의어로 분산 권장")
        else:
            r.ok("STUFFING", msg)
    sents = [s for s in split_sentences(text_plain) if plain_len(s) >= 15]
    dup = {s for s in sents if sents.count(s) > 1}
    if dup:
        r.fail("DUP_SENTENCE", f"동일 문장 반복 {len(dup)}건 (차단 B3): {list(dup)[:2]}")

    # 보조 키워드
    if subs:
        hit = [s for s in subs if s in text_plain]
        (r.ok if len(hit) >= len(subs) / 2 else r.warn)(
            "SUB_KW", f"보조 키워드 {len(hit)}/{len(subs)}개 본문 등장")

    # 긴 문단
    long_paras = [p for p in re.split(r"\n\s*\n", body)
                  if not p.lstrip().startswith(("#", "|", "-", "*", "1.", "```"))
                  and len(split_sentences(p)) > 4]
    if long_paras:
        r.warn("PARAGRAPH", f"4문장 넘는 문단 {len(long_paras)}개")

    # FAQ
    faq = sec.get("faq", "")
    qs = [q.strip() for q in re.findall(r"^Q[.:]\s*(.+)$", faq, re.M)]
    ans = re.findall(r"^A[.:]\s*(.+)$", faq, re.M)
    if not 3 <= len(qs) <= 6:
        r.warn("FAQ_COUNT", f"FAQ {len(qs)}개 (권장 3~6)")
    else:
        r.ok("FAQ_COUNT", f"FAQ {len(qs)}개")
    if len(qs) != len(ans):
        r.fail("FAQ_FORMAT", f"질문 {len(qs)}개 / 답 {len(ans)}개 불일치")

    # JSON-LD
    jl = sec.get("jsonld", "")
    jl = re.sub(r"^```(?:json)?\s*|\s*```$", "", jl.strip())
    try:
        data = json.loads(jl)
    except Exception as e:  # noqa: BLE001
        r.fail("JSONLD_PARSE", f"JSON-LD 파싱 실패: {e} (차단 B4)")
        data = None
    if data is not None:
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        types = {}
        for nd in nodes:
            t = nd.get("@type")
            for tt in (t if isinstance(t, list) else [t]):
                types[tt] = nd
        post = types.get("BlogPosting") or types.get("Article")
        if not post:
            r.fail("JSONLD_TYPE", "BlogPosting/Article 노드 없음 (차단 B4)")
        else:
            req = ["headline", "description", "author", "datePublished", "dateModified"]
            empty = [k for k in req if not post.get(k) or
                     (isinstance(post.get(k), dict) and not post[k].get("name"))]
            if empty:
                r.fail("JSONLD_FIELDS", f"BlogPosting 필수 필드 비어 있음: {empty} (차단 B4)")
            else:
                r.ok("JSONLD_FIELDS", "BlogPosting 필수 필드 충족")
            if "aggregateRating" in post or "review" in post:
                r.fail("JSONLD_FAKE", "BlogPosting에 평점/리뷰 포함 — 본문 근거 확인 필요 (차단 B4)")
            if rec and post.get("headline") and post["headline"] != rec:
                r.warn("JSONLD_HEADLINE", "headline이 추천 제목과 다름")
            if md and post.get("description") and post["description"] != md:
                r.warn("JSONLD_DESC", "description이 메타설명과 다름")
        if "FAQPage" in types:
            fq = [e.get("name", "").strip() for e in types["FAQPage"].get("mainEntity", [])]
            if sorted(fq) != sorted(qs):
                r.fail("JSONLD_FAQ_MATCH", "FAQPage 질문이 본문 FAQ와 불일치 (차단 B4)")
            else:
                r.ok("JSONLD_FAQ_MATCH", "FAQPage 질문이 본문 FAQ와 일치")

    # 태그 (구글판 전용: 워드프레스·티스토리 태그. 예전 패키지의 naver_tags도 읽음)
    tags = re.findall(r"#[^\s#]+", sec.get("tags") or sec.get("naver_tags", ""))
    (r.ok if 5 <= len(tags) <= 10 else r.warn)("TAGS", f"태그 {len(tags)}개 (권장 5~10)")

    # 임시 표식
    full = "\n".join(v for k, v in sec.items() if k != "jsonld")
    found = {lab: len(re.findall(pat, full)) for lab, pat in TEMP_MARKERS.items()}
    found = {k: v for k, v in found.items() if v}
    if found:
        desc = ", ".join(f"{k}×{v}" for k, v in found.items())
        (r.fail if final else r.warn)("TEMP_MARKERS", f"임시 표식 남음: {desc}" +
                                       (" — 발행 전 모두 해소 필요" if final else ""))
    return r


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    final = "--final" in sys.argv
    with open(path, encoding="utf-8") as f:
        text = f.read()
    rep = check(text, final=final, base_dir=os.path.dirname(os.path.abspath(path)))
    if "--json" in sys.argv:
        print(json.dumps(rep.items, ensure_ascii=False, indent=2))
    else:
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        for it in sorted(rep.items, key=lambda x: order[x["level"]]):
            print(f"[{it['level']}] {it['code']}: {it['msg']}")
        c = {lv: sum(1 for i in rep.items if i["level"] == lv) for lv in order}
        print(f"\n요약: FAIL {c['FAIL']} / WARN {c['WARN']} / PASS {c['PASS']} → "
              + ("수정 필요" if rep.failed else "기계 점검 통과"))
    sys.exit(1 if rep.failed else 0)


if __name__ == "__main__":
    main()

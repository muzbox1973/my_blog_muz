#!/usr/bin/env python3
"""사용자 스티커를 규격과 상관없이 받아 정리하고 카탈로그(stickers.json)에 합친다.

사용법:
    python3 import_stickers.py 새스티커폴더/                     # 낱개 이미지 여러 장
    python3 import_stickers.py char-wink.png bubble-wow.webp      # 파일 지정
    python3 import_stickers.py sheet.png --sheet --prefix new     # 시트 한 장 → 덩어리별 자동 분할 (간격이 넓은 시트)
    python3 import_stickers.py sheet.png --boxes boxes.json       # 촘촘한 시트 → 좌표로 자르기 {"id": [x0,y0,x1,y1], ...}
    python3 import_stickers.py ... --kind prop                    # 종류 강제
    python3 import_stickers.py --rebuild-preview                  # _preview.png만 다시 만들기

받는 규격:
  - PNG·JPG·WEBP, 크기·비율 제한 없음 (긴 변이 --max-side보다 크면 줄여서 저장, 기본 1200px)
  - 배경: 투명이면 그대로 / 테두리가 단색이면 테두리부터 지움(안쪽 흰색은 보존) /
          그 밖에는 rembg(설치돼 있으면)로 지움
  - 파일 이름 앞부분으로 종류를 추정: char- bubble- card- tape- label- arrow- marker- (그 외 prop)
결과: <스티커 폴더>/<id>.png, stickers.json 병합, _preview.png 갱신, 확인할 것 목록 출력.
쓸 때(use_when)·피할 때(avoid)는 비어 있으니 미리보기를 보고 채운다.
Pillow·numpy 필요 (scipy·rembg는 있으면 사용).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from _local_paths import contained_path

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.normpath(os.environ.get("HARNESS_STICKERS") or os.path.join(HERE, "..", "assets", "stickers"))
KINDS = {"char": "character", "character": "character", "bubble": "bubble", "card": "card", "tape": "tape",
         "label": "label", "pill": "label", "arrow": "arrow", "marker": "marker", "prop": "prop"}
ORDER = ["character", "bubble", "card", "tape", "label", "arrow", "marker", "prop"]
# 종류별로 '보기 좋게 쓰려면 원본 긴 변이 이 정도는 돼야 한다' (작으면 경고)
MIN_SIDE = {"character": 300, "bubble": 100, "card": 200, "tape": 90, "label": 100, "arrow": 60, "marker": 40, "prop": 80}
EXTS = (".png", ".jpg", ".jpeg", ".webp")


def slug_id(name):
    s = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(name))[0].lower()).strip("-")
    return s or "stk-" + hashlib.md5(name.encode()).hexdigest()[:6]


def guess_kind(sid):
    head = sid.split("-")[0]
    return KINDS.get(head, "prop")


def border(a, k=3):
    return np.concatenate([a[:k].reshape(-1, a.shape[-1]), a[-k:].reshape(-1, a.shape[-1]),
                           a[:, :k].reshape(-1, a.shape[-1]), a[:, -k:].reshape(-1, a.shape[-1])])


def label(mask):
    try:
        from scipy import ndimage
        return ndimage.label(mask)
    except ImportError:  # 작은 BFS (scipy 없을 때)
        h, w = mask.shape
        lab = np.zeros((h, w), int)
        n = 0
        for y in range(h):
            for x in range(w):
                if mask[y, x] and not lab[y, x]:
                    n += 1
                    st = [(y, x)]
                    lab[y, x] = n
                    while st:
                        cy, cx = st.pop()
                        for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                                lab[ny, nx] = n
                                st.append((ny, nx))
        return lab, n


def flood_bg(rgb, tol=30):
    """테두리와 이어진 '배경색 비슷한' 픽셀만 지운다 → 스티커 안쪽 흰색은 남는다."""
    bg = np.median(border(rgb), axis=0)
    near = np.sqrt(((rgb.astype(int) - bg) ** 2).sum(-1)) < tol
    lab, n = label(near)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgmask = np.isin(lab, list(edge))
    return np.where(bgmask, 0, 255).astype(np.uint8)


def cutout(im, use_rembg=True):
    """배경 제거. 반환: (RGBA 이미지, 방법)"""
    im = im.convert("RGBA")
    a = np.array(im)
    alpha = a[..., 3]
    if (border(alpha[..., None]) < 16).mean() > 0.6:
        return im, "투명 배경"
    rgb = a[..., :3]
    b = border(rgb).astype(int)
    med = np.median(b, axis=0)
    if (np.sqrt(((b - med) ** 2).sum(-1)) < 30).mean() > 0.7:  # 테두리의 70% 이상이 한 색 → 단색 배경
        al = flood_bg(rgb)
        a[..., 3] = np.minimum(alpha, al)
        return Image.fromarray(a), "단색 배경 제거"
    if use_rembg:
        try:
            from rembg import new_session, remove
            out = remove(im.convert("RGB"), session=new_session("isnet-general-use"), post_process_mask=True)
            o = np.array(out)
            o[..., :3] = rgb  # 색은 원본 유지
            return Image.fromarray(o), "rembg 배경 제거"
        except Exception as e:  # noqa: BLE001
            return im, f"배경 제거 실패({str(e)[:40]}) — 원본 그대로"
    return im, "복잡한 배경 — 제거 못 함(rembg 필요)"


def trim(im, pad=2):
    bb = im.getbbox()
    if not bb:
        return im
    x0, y0, x1, y1 = bb
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def split_sheet(im, min_area=400, gap=6):
    """투명해진 시트를 덩어리별로 나눈다. 가까운 조각(말풍선 꼬리·글자 등)은 gap px 안이면 한 덩어리."""
    al = np.array(im)[..., 3] > 40
    grown = al
    try:
        from scipy import ndimage
        grown = ndimage.binary_dilation(al, iterations=gap)
    except ImportError:
        pass
    lab, n = label(grown)
    parts = []
    for i in range(1, n + 1):
        ys, xs = np.where((lab == i) & al)
        if len(ys) < min_area:
            continue
        parts.append(((ys.min() // 80, xs.min()), im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))))
    parts.sort(key=lambda t: t[0])  # 시트 위치 순서 (위→아래, 왼→오른쪽)
    return [p for _, p in parts]


def find_font():
    try:
        p = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK KR:bold"], capture_output=True, text=True, timeout=5).stdout
        if p and os.path.exists(p):
            return ImageFont.truetype(p, 15)
    except Exception:  # noqa: BLE001
        pass
    for p in ("C:/Windows/Fonts/malgunbd.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc"):
        if os.path.exists(p):
            return ImageFont.truetype(p, 15)
    return ImageFont.load_default()


def build_preview(d, stickers):
    f = find_font()
    cat = sorted(stickers, key=lambda s: (ORDER.index(s["kind"]) if s["kind"] in ORDER else 99, s["id"]))
    W, cell = 1600, 190
    x = y = 10
    rowh, prev, places = 0, None, []
    for s in cat:
        p = contained_path(d, s["file"])
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGBA")
        im.thumbnail((cell - 14, 170 if s["kind"] == "character" else 120))
        if (prev and prev != s["kind"]) or x + cell > W:
            x, y, rowh = 10, y + rowh + 34, 0
        places.append((s, im, x, y))
        x += cell
        rowh = max(rowh, im.height)
        prev = s["kind"]
    H = y + rowh + 44
    o = Image.new("RGB", (W, H), "#fbf6ea")
    dr = ImageDraw.Draw(o)
    for s, im, x, y in places:
        o.paste(im, (x + (cell - 14 - im.width) // 2, y), im)
        dr.text((x, y + im.height + 4), s["id"] + (" *" if s.get("has_text") else ""), fill="#23272f", font=f)
    dr.text((10, H - 24), "* 글자가 박힌 스티커 — 주제가 맞을 때만", fill="#a33", font=f)
    o.save(os.path.join(d, "_preview.png"), optimize=True)


def main():
    ap = argparse.ArgumentParser(description="사용자 스티커 가져오기")
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("--stickers", default=DEFAULT_DIR, help="스티커 폴더 (기본: ../assets/stickers)")
    ap.add_argument("--sheet", action="store_true", help="입력 이미지를 시트로 보고 낱개로 분할")
    ap.add_argument("--prefix", default="", help="시트 분할 조각 id 앞부분 (예: char, prop)")
    ap.add_argument("--kind", choices=ORDER, help="종류 강제 지정")
    ap.add_argument("--has-text", action="store_true", help="글자가 박힌 스티커로 표시")
    ap.add_argument("--replace", action="store_true", help="같은 id가 있으면 덮어쓰기 (기본: 건너뜀)")
    ap.add_argument("--no-rembg", action="store_true")
    ap.add_argument("--max-side", type=int, default=1200)
    ap.add_argument("--min-area", type=int, default=400, help="시트 분할 시 버릴 작은 조각 기준(픽셀 수)")
    ap.add_argument("--boxes", help='좌표 파일(JSON): {"char-wink": [x0, y0, x1, y1], ...} — 촘촘한 시트용')
    ap.add_argument("--gap", type=int, default=6, help="--sheet 분할 때 이 거리(px) 안의 조각은 한 덩어리")
    ap.add_argument("--rebuild-preview", action="store_true")
    a = ap.parse_args()
    d = a.stickers
    os.makedirs(d, exist_ok=True)
    cp = os.path.join(d, "stickers.json")
    cat = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {"version": 1, "stickers": []}
    by = {s["id"]: s for s in cat["stickers"]}
    if a.rebuild_preview and not a.inputs:
        build_preview(d, cat["stickers"])
        print(f"[stickers] 미리보기 갱신: {os.path.join(d, '_preview.png')}")
        return
    files = []
    for p in a.inputs:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(EXTS) and not f.startswith("_")]
        elif p.lower().endswith(EXTS):
            files.append(p)
    if not files:
        print("가져올 이미지가 없음 (png·jpg·jpeg·webp)")
        sys.exit(2)
    added, todo = [], []
    for f in files:
        try:
            src = Image.open(f)
        except Exception as e:  # noqa: BLE001
            todo.append(f"{f}: 열 수 없음 ({e})")
            continue
        if a.boxes:  # 좌표마다 잘라서 각각 배경 제거 (주변 스티커가 섞여 들어와도 가장 큰 덩어리 위주로 남김)
            boxes = json.load(open(a.boxes, encoding="utf-8"))
            pieces, how = [], "좌표 자르기"
            for bid, bx in boxes.items():
                piece, h2 = cutout(src.crop(tuple(bx)), not a.no_rembg)
                al = np.array(piece)[..., 3] > 40
                lab, n = label(al)
                if n > 1:
                    sizes = np.bincount(lab.ravel())[1:]
                    keep = np.zeros(n + 1, bool)
                    keep[1:] = sizes >= sizes.max() * 0.02
                    arr = np.array(piece)
                    arr[..., 3] = np.where(keep[lab], arr[..., 3], 0)
                    piece = Image.fromarray(arr)
                pieces.append((slug_id(bid), piece))
                how = f"좌표 자르기 + {h2}"
        elif a.sheet:
            im, how = cutout(src, not a.no_rembg)
            base = a.prefix or slug_id(f)
            pieces = [(f"{base}-{i:02d}", p) for i, p in enumerate(split_sheet(im, a.min_area, a.gap), 1)]
            if not pieces:
                todo.append(f"{f}: 시트에서 조각을 찾지 못함 (배경 제거 결과 확인)")
        else:
            im, how = cutout(src, not a.no_rembg)
            pieces = [(slug_id(f), trim(im))]
        for sid, p in pieces:
            p = trim(p)
            if max(p.size) > a.max_side:
                p.thumbnail((a.max_side, a.max_side), Image.LANCZOS)
            if sid in by and not a.replace:
                todo.append(f"{sid}: 이미 있음 — 건너뜀 (--replace로 덮어쓰기)")
                continue
            kind = a.kind or guess_kind(sid)
            arr = np.array(p)
            bottom_cut = kind == "character" and (arr[-2:, :, 3] > 128).mean() > 0.25
            p.save(os.path.join(d, f"{sid}.png"), optimize=True)
            entry = {"id": sid, "file": f"{sid}.png", "kind": kind, "w": p.width, "h": p.height,
                     "use_when": "", "avoid": "", "has_text": bool(a.has_text), "bottom_cut": bool(bottom_cut),
                     "max_scale": 1.5, "source": os.path.basename(f), "imported": how}
            if kind == "bubble":
                entry["text_inside"] = True  # 안에 그림이 있는 말풍선이면 false로 고칠 것
            by[sid] = {**by.get(sid, {}), **entry}
            added.append(entry)
            if max(p.size) < MIN_SIDE.get(kind, 80):
                todo.append(f"{sid}: 원본이 작음({p.width}×{p.height}) — {kind}는 긴 변 {MIN_SIDE[kind]}px 이상 권장, 크게 쓰면 흐려짐")
            if how.startswith(("배경 제거 실패", "복잡한 배경")):
                todo.append(f"{sid}: {how}")
    cat["stickers"] = list(by.values())
    with open(cp, "w", encoding="utf-8") as fh:
        json.dump(cat, fh, ensure_ascii=False, indent=1)
    build_preview(d, cat["stickers"])
    for e in added:
        print(f"[추가] {e['id']:<24} {e['kind']:<9} {e['w']}×{e['h']}  ({e['imported']})"
              + ("  아래 잘린 상반신" if e["bottom_cut"] else ""))
    for t in todo:
        print(f"[확인] {t}")
    print(f"\n{len(added)}개 추가 → {cp}\n미리보기: {os.path.join(d, '_preview.png')}"
          "\n다음 할 일: 미리보기를 보고 stickers.json의 use_when·avoid를 채우고, 종류·id가 틀리면 고친다.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""사용자가 지정한 git 저장소(로컬 클론)에 하네스 작업 폴더를 만들고 스크립트·스티커를 옮겨 둔다.
이후 모든 스크립트는 **저장소 안의 사본**을 불러와 실행한다.

사용법:
    python3 repo_setup.py --repo <클론 경로> [--base blog-harness] [--post 20261026-coffee-bean-storage]
                          [--owner O --name R] [--branch main] [--cdn jsdelivr|raw]

만드는 구조 (<base> 기본값 blog-harness):
    <repo>/<base>/harness.json       ← 저장소 설정 (owner·repo·branch·cdn)
    <repo>/<base>/VERSION
    <repo>/<base>/scripts/           ← 하네스 스크립트 (여기 있는 것을 실행)
    <repo>/<base>/assets/office.html ← 진행 화면
    <repo>/<base>/assets/stickers/   ← 스티커 (기본 + 사용자 추가)
    <repo>/<base>/posts/<post>/      ← 글마다 패키지·visual-plan·visuals/·게시용 HTML

갱신 규칙:
  - 저장소에 없는 파일 → 추가
  - 지난번 설치본 그대로인 스크립트 → 새 버전으로 갱신
  - 사용자가 고친 스크립트 → 그대로 둠 (--force로 덮어쓰기)
  - 스티커 PNG는 절대 덮어쓰지 않고, stickers.json은 없는 id만 추가
표준 라이브러리만 사용한다.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.normpath(os.path.join(HERE, ".."))


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def parse_remote(url):
    """https://github.com/O/R(.git), git@github.com:O/R.git, 프록시 주소 …/O/R → (host, O, R)"""
    url = (url or "").strip()
    m = re.match(r"^git@([^:]+):(.+?)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.match(r"^\w+://(?:[^@/]+@)?([^/]+)/(.+)$", url)
    if m:
        parts = [p for p in m.group(2).rstrip("/").split("/") if p]
        if len(parts) >= 2:
            host = "github.com" if "github" in m.group(1) or "git" in parts[:-2] else m.group(1)
            return host, parts[-2], re.sub(r"\.git$", "", parts[-1])
    return None, None, None


def bundle_files():
    out = []
    for f in sorted(os.listdir(os.path.join(SKILL, "scripts"))):
        if f.endswith(".py"):
            out.append(("scripts/" + f, "code"))
    out.append(("assets/office.html", "code"))
    sd = os.path.join(SKILL, "assets", "stickers")
    for f in sorted(os.listdir(sd)):
        if f.endswith(".png"):
            out.append(("assets/stickers/" + f, "sticker"))
    return out


def main():
    ap = argparse.ArgumentParser(description="git 저장소에 하네스 작업 폴더 준비")
    ap.add_argument("--repo", required=True, help="로컬 클론 경로")
    ap.add_argument("--base", default="blog-harness", help="저장소 안 하위 폴더 이름")
    ap.add_argument("--post", help="이번 글 폴더 이름 (예: 20261026-coffee-bean-storage)")
    ap.add_argument("--owner"), ap.add_argument("--name"), ap.add_argument("--branch")
    ap.add_argument("--cdn", choices=["jsdelivr", "raw", "custom"], help="이미지 주소 방식 (기본 jsdelivr)")
    ap.add_argument("--url-template", help="cdn=custom일 때: {owner} {repo} {ref} {path} 사용")
    ap.add_argument("--force", action="store_true", help="사용자가 고친 스크립트도 덮어쓰기")
    a = ap.parse_args()

    repo = os.path.abspath(a.repo)
    try:
        top = git(repo, "rev-parse", "--show-toplevel")
    except Exception as e:  # noqa: BLE001
        print(f"[repo] git 저장소가 아님: {repo} ({e})", file=sys.stderr)
        sys.exit(2)
    base = os.path.join(top, a.base)
    os.makedirs(os.path.join(base, "posts"), exist_ok=True)

    # 설정
    cfg_p = os.path.join(base, "harness.json")
    cfg = json.load(open(cfg_p, encoding="utf-8")) if os.path.exists(cfg_p) else {}
    host, owner, name = parse_remote(git(top, "remote", "get-url", "origin", check=False))
    branch = a.branch or cfg.get("branch") or git(top, "rev-parse", "--abbrev-ref", "HEAD", check=False) or "main"
    if branch == "HEAD":
        branch = "main"
    cfg.update({k: v for k, v in {
        "host": cfg.get("host") or host or "github.com",
        "owner": a.owner or cfg.get("owner") or owner,
        "repo": a.name or cfg.get("repo") or name,
        "branch": branch,
        "base": a.base,
        "cdn": a.cdn or cfg.get("cdn") or "jsdelivr",
        "url_template": a.url_template or cfg.get("url_template"),
    }.items() if v is not None})
    cfg.setdefault("created", date.today().isoformat())
    if cfg.get("host") not in (None, "github.com") and cfg.get("cdn") == "jsdelivr" and not cfg.get("url_template"):
        print("[repo] 경고: jsDelivr는 GitHub 저장소만 지원 — --cdn custom --url-template 지정 필요", file=sys.stderr)

    # 번들 동기화
    man_p = os.path.join(base, ".harness-manifest.json")
    man = json.load(open(man_p, encoding="utf-8")) if os.path.exists(man_p) else {}
    log = {"추가": [], "갱신": [], "같음": 0, "사용자 수정 유지": [], "삭제": []}
    current = {rel for rel, _ in bundle_files()}
    for rel in [r for r in list(man) if r not in current and not r.startswith("assets/stickers/")]:
        dst = os.path.join(base, rel)  # 새 버전에서 없어진 스크립트: 손대지 않은 설치본이면 지운다
        if os.path.exists(dst) and sha(dst) == man[rel]:
            os.remove(dst)
            log["삭제"].append(rel)
            man.pop(rel)
        elif not os.path.exists(dst):
            man.pop(rel)
    for rel, kind in bundle_files():
        src, dst = os.path.join(SKILL, rel), os.path.join(base, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            log["추가"].append(rel)
        elif sha(dst) == sha(src):
            log["같음"] += 1
        elif kind == "sticker":
            log["사용자 수정 유지"].append(rel)  # 스티커는 절대 덮어쓰지 않음
            continue
        elif a.force or man.get(rel) == sha(dst):
            shutil.copy2(src, dst)
            log["갱신"].append(rel)
        else:
            log["사용자 수정 유지"].append(rel)
            continue
        man[rel] = sha(src)
    # stickers.json 병합 (저장소에 없는 id만 추가)
    sj_src = os.path.join(SKILL, "assets", "stickers", "stickers.json")
    sj_dst = os.path.join(base, "assets", "stickers", "stickers.json")
    src_cat = json.load(open(sj_src, encoding="utf-8"))
    if os.path.exists(sj_dst):
        dst_cat = json.load(open(sj_dst, encoding="utf-8"))
        have = {s["id"] for s in dst_cat["stickers"]}
        new = [s for s in src_cat["stickers"] if s["id"] not in have]
        dst_cat["stickers"] += new
        if new:
            log["추가"].append(f"stickers.json 항목 {len(new)}개")
    else:
        dst_cat = src_cat
        log["추가"].append("assets/stickers/stickers.json")
    json.dump(dst_cat, open(sj_dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if os.path.exists(os.path.join(SKILL, "assets", "stickers", "_preview.png")) and not os.path.exists(
            os.path.join(base, "assets", "stickers", "_preview.png")):
        shutil.copy2(os.path.join(SKILL, "assets", "stickers", "_preview.png"), os.path.join(base, "assets", "stickers", "_preview.png"))
    ver = open(os.path.join(SKILL, "VERSION")).read().strip() if os.path.exists(os.path.join(SKILL, "VERSION")) else "?"
    open(os.path.join(base, "VERSION"), "w").write(ver + "\n")
    cfg["version"] = ver
    json.dump(cfg, open(cfg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(man, open(man_p, "w", encoding="utf-8"), indent=1)
    gi = os.path.join(base, ".gitignore")
    if not os.path.exists(gi):  # 미리보기·진행 화면 같은 무거운 로컬 파일은 저장소에 올리지 않는다
        open(gi, "w", encoding="utf-8").write(
            "posts/*/preview.html\nposts/*/preview.png\nposts/*/visuals/*.html\nposts/*/status.json\n"
            "posts/*/status.js\nposts/*/.status*\nposts/*/office.html\n__pycache__/\n")
    readme = os.path.join(base, "README.md")
    if not os.path.exists(readme):
        open(readme, "w", encoding="utf-8").write(
            "# blog-harness\n\nblog-seo-aeo-harness 작업 폴더입니다.\n\n"
            "- `scripts/` 하네스 스크립트 (스킬이 여기 있는 것을 실행)\n- `assets/stickers/` 스티커\n"
            "- `posts/<글>/` 기사 패키지, 이미지(`visuals/`), 게시용 HTML(`post-google.html`), 제목·해시태그\n\n"
            "본문 HTML의 이미지는 이 저장소의 커밋 주소를 가리키므로 **저장소가 공개(public)** 여야 블로그에서 보입니다.\n")

    post = None
    if a.post:
        post = os.path.join(base, "posts", a.post)
        os.makedirs(os.path.join(post, "visuals"), exist_ok=True)

    print(f"[repo] 저장소: {cfg.get('owner')}/{cfg.get('repo')} @ {cfg['branch']}  (이미지 주소: {cfg['cdn']})")
    print(f"[repo] 작업 폴더: {base}")
    if log["추가"]:
        print(f"[repo] 추가: {len(log['추가'])}개 " + ", ".join(x for x in log["추가"] if not x.endswith(".png"))[:300])
    if log["갱신"]:
        print("[repo] 갱신: " + ", ".join(log["갱신"]))
    if log["삭제"]:
        print("[repo] 폐기된 설치본 삭제: " + ", ".join(log["삭제"]))
    if log["사용자 수정 유지"]:
        print("[repo] 사용자 수정본 유지(덮어쓰지 않음): " + ", ".join(log["사용자 수정 유지"]))
    if not cfg.get("owner") or not cfg.get("repo"):
        print("[repo] 경고: 원격 주소에서 owner/repo를 못 읽음 — --owner --name 지정 필요 (이미지 주소에 씀)", file=sys.stderr)
    print(json.dumps({"base": base, "scripts": os.path.join(base, "scripts"), "post": post,
                      "owner": cfg.get("owner"), "repo": cfg.get("repo"), "branch": cfg["branch"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

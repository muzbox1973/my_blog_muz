#!/usr/bin/env python3
"""하네스 작업 폴더를 git 저장소에 커밋·푸시하고, 이미지의 공개 주소(커밋 고정)를 만든다.

사용법:
    python3 repo_sync.py --repo <클론> publish --post <글 폴더> -m "메시지"      # 커밋 + 푸시 + 주소 생성 + 접속 확인
    python3 repo_sync.py --repo <클론> publish --post <글 폴더> -m "…" --keep-urls  # 게시 파일 올리기 (주소는 그대로)
    python3 repo_sync.py --repo <클론> publish --post <글 폴더> -m "…" --no-push # 커밋만 (푸시는 사람이)
    python3 repo_sync.py --repo <클론> urls --post <글 폴더> --ref main           # git 작업 없이 주소만 다시 만들기
    python3 repo_sync.py --repo <클론> status

주소 방식 (harness.json의 cdn):
    jsdelivr  https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}   (기본, GitHub 공개 저장소)
    raw       https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}
    custom    harness.json의 url_template
{ref}는 기본적으로 **푸시한 커밋 SHA**라서 주소가 바뀌지 않고 캐시도 꼬이지 않는다.
결과: <글 폴더>/assets-urls.json  {"ref", "pushed", "files": {"visuals/x.png": url}, "check": {...}}
종료코드: 0 성공 / 3 푸시 실패 / 4 주소가 404 등으로 열리지 않음(비공개 저장소 의심)
표준 라이브러리만 사용한다.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

TEMPLATES = {
    "jsdelivr": "https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{path}",
    "raw": "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}",
}
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400] or r.stdout.strip()[:400])
    return r


def load_cfg(top, base):
    p = os.path.join(top, base, "harness.json")
    if not os.path.exists(p):
        raise SystemExit(f"[sync] {p} 없음 — 먼저 repo_setup.py 실행")
    return json.load(open(p, encoding="utf-8"))


def build_urls(cfg, top, post_dir, ref):
    tpl = cfg.get("url_template") if cfg.get("cdn") == "custom" else TEMPLATES.get(cfg.get("cdn", "jsdelivr"))
    files = {}
    for root, _, names in os.walk(post_dir):
        for n in sorted(names):
            if n.lower().endswith(IMG_EXT) and not n.startswith(("preview", "_")):
                full = os.path.join(root, n)
                rel_post = os.path.relpath(full, post_dir).replace(os.sep, "/")
                rel_repo = os.path.relpath(full, top).replace(os.sep, "/")
                path = "/".join(urllib.parse.quote(seg) for seg in rel_repo.split("/"))
                files[rel_post] = tpl.format(owner=cfg["owner"], repo=cfg["repo"], ref=ref, path=path)
    return files


def check_urls(files, timeout=8):
    res = {"ok": 0, "fail": [], "unverified": 0}
    for rel, url in files.items():
        try:
            req = urllib.request.Request(url, method="GET", headers={"Range": "bytes=0-63", "User-Agent": "blog-harness"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status in (200, 206):
                    res["ok"] += 1
                else:
                    res["fail"].append(f"{rel} → HTTP {r.status}")
        except urllib.error.HTTPError as e:
            res["fail"].append(f"{rel} → HTTP {e.code}")
        except Exception:  # noqa: BLE001  (네트워크 차단·프록시 등: 확인 불가)
            res["unverified"] += 1
    return res


def main():
    ap = argparse.ArgumentParser(description="하네스 작업 폴더 커밋·푸시·이미지 주소")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", default="blog-harness-fast")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--post", required=True)
    p.add_argument("-m", "--message", default="blog-harness: 글·이미지 저장")
    p.add_argument("--no-push", action="store_true")
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--keep-urls", action="store_true", help="이미지 주소(assets-urls.json)는 그대로 두고 커밋·푸시만 (게시 파일 올릴 때)")
    u = sub.add_parser("urls")
    u.add_argument("--post", required=True)
    u.add_argument("--ref", help="기본: 현재 커밋 SHA")
    u.add_argument("--no-verify", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()

    top = git(a.repo, "rev-parse", "--show-toplevel").stdout.strip()
    cfg = load_cfg(top, a.base)
    branch = cfg.get("branch", "main")
    if a.cmd == "status":
        print(git(top, "status", "--short", "--", a.base).stdout or "(변경 없음)")
        print(f"브랜치 {branch}, 최근 커밋 {git(top, 'rev-parse', '--short', 'HEAD', check=False).stdout.strip()}")
        return
    post_dir = os.path.join(top, a.base, "posts", a.post)
    if not os.path.isdir(post_dir):
        raise SystemExit(f"[sync] 글 폴더 없음: {post_dir}")

    pushed = None
    if a.cmd == "publish":
        git(top, "add", "--", a.base)
        if git(top, "diff", "--cached", "--quiet", check=False).returncode == 0:
            print("[sync] 커밋할 변경 없음")
        else:
            ident = []
            if not git(top, "config", "user.email", check=False).stdout.strip():
                ident = ["-c", "user.name=blog-seo-aeo-harness-fast", "-c", "user.email=blog-harness@users.noreply.github.com"]
                print("[sync] 참고: git 사용자 정보가 없어 하네스 이름으로 커밋")
            r = subprocess.run(["git", "-C", top, *ident, "commit", "-m", a.message], capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"[sync] 커밋 실패: {r.stderr.strip()[:300]}")
            print(f"[sync] 커밋: {git(top, 'rev-parse', '--short', 'HEAD').stdout.strip()} {a.message}")
        if a.no_push:
            pushed = False
            print("[sync] 푸시 생략(--no-push) — 사람이 푸시한 뒤 `urls --ref <브랜치 또는 SHA>`로 주소를 다시 만든다")
        else:
            r = git(top, "push", "origin", f"HEAD:{branch}", check=False)
            if r.returncode != 0:
                git(top, "pull", "--rebase", "origin", branch, check=False)
                r = git(top, "push", "origin", f"HEAD:{branch}", check=False)
            if r.returncode != 0:
                print(f"[sync] 푸시 실패: {(r.stderr or r.stdout).strip()[:300]}", file=sys.stderr)
                print("[sync] 커밋은 로컬에 있음. 사람이 직접 푸시하거나 권한을 연결한 뒤 다시 publish", file=sys.stderr)
                sys.exit(3)
            pushed = True
            print(f"[sync] 푸시 완료 → origin/{branch}")
        ref = git(top, "rev-parse", "HEAD").stdout.strip()
    else:
        ref = a.ref or git(top, "rev-parse", "HEAD").stdout.strip()

    if a.cmd == "publish" and a.keep_urls and os.path.exists(os.path.join(post_dir, "assets-urls.json")):
        print(f"[sync] 이미지 주소는 그대로 유지 (assets-urls.json), 이번 커밋 {ref[:10]}")
        return
    files = build_urls(cfg, top, post_dir, ref)
    out = {"ref": ref, "pushed": pushed, "cdn": cfg.get("cdn"), "files": files}
    if files and not a.no_verify and pushed is not False:
        chk = check_urls(files)
        out["check"] = chk
        print(f"[sync] 주소 확인: 열림 {chk['ok']} / 실패 {len(chk['fail'])} / 확인 불가(네트워크) {chk['unverified']}")
        for f in chk["fail"]:
            print(f"[sync]   실패: {f}", file=sys.stderr)
    json.dump(out, open(os.path.join(post_dir, "assets-urls.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[sync] 이미지 주소 {len(files)}개 → {os.path.join(post_dir, 'assets-urls.json')} (ref {ref[:10]})")
    if out.get("check", {}).get("fail"):
        print("[sync] 주소가 열리지 않음: 저장소가 비공개이거나 아직 반영 전일 수 있음. 공개 저장소인지 확인", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()

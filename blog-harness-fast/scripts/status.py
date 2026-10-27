#!/usr/bin/env python3
"""Real progress: init -> go 0/1/2/3/4 -> article-ready -> go 5/6/B/done.
Run serve in a background terminal, then actually open the printed loopback URL.
File creation never implies that writing, review, or rendering has finished.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

AGENTS = ["lead", "research", "writer", "seo", "fact", "lint", "design", "human"]
STATES = ["idle", "working", "waiting", "done", "blocked", "review"]
GO_ORDER = ["0", "1", "2", "3", "4", "5", "6", "B", "done"]
GO_RANK = {name: i for i, name in enumerate(GO_ORDER)}
GO_RANK["A"] = 1.5
OFFICE_HTML = Path(__file__).resolve().parent.parent / "assets" / "office.html"


def now():
    return datetime.now(timezone.utc).isoformat()


def fresh(task):
    return {"version": 3, "run_id": uuid.uuid4().hex, "task": task, "stage": "0", "round": 0,
            "finished": False, "seq": 0, "updated": now(), "log": [],
            "agents": {a: {"state": "idle", "detail": "", "since": now()} for a in AGENTS}}


def load(d):
    return json.loads((Path(d) / "status.json").read_text(encoding="utf-8"))


def write_atomic(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def locked(d):
    # Cross-platform lock; do not silently race or delete another writer's lock.
    path = Path(d) / ".status.lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RuntimeError("상태 기록 잠금이 남아 있습니다. 실행 중인 기록 작업을 확인하세요")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink()


def save(d, s):
    s["updated"] = now()
    js = "window.__HARNESS_STATUS = " + json.dumps(s, ensure_ascii=True) + ";\n"
    for target in {Path(d), Path(s.get("mirror") or d)}:
        write_atomic(target / "status.json", json.dumps(s, ensure_ascii=False, indent=2))
        write_atomic(target / "status.js", js)


def add_log(s, agent, msg, kind="log", **extra):
    s["seq"] += 1
    s["log"].append(dict(seq=s["seq"], t=now(), agent=agent, msg=msg[:180], kind=kind, **extra))
    s["log"] = s["log"][-80:]


def do_set(s, agent, state, detail=""):
    if agent not in AGENTS or state not in STATES:
        raise ValueError("알 수 없는 담당자 또는 작업 상태")
    s["agents"][agent] = dict(state=state, detail=detail[:120], since=now())
    add_log(s, agent, detail or state, "state", state=state)


def go_to(s, target, detail=""):
    if target not in GO_RANK:
        raise ValueError("단계: 0 1 A 2 3 4 5 6 B done")
    current = s["stage"]
    if s["finished"]:
        raise ValueError("이미 완료된 작업입니다. 새 작업은 init으로 시작하세요")
    if GO_RANK[target] < GO_RANK[current]:
        raise ValueError("이전 단계로 자동 이동할 수 없습니다. 변경된 원고는 새 작업으로 시작하세요")
    if GO_RANK[target] - GO_RANK[current] > 1:
        raise ValueError("단계를 건너뛸 수 없습니다. 실제 작업 완료 후 다음 단계로 이동하세요")
    if target == "0":
        do_set(s, "lead", "working", detail or "입력 카드 정리 중")
    elif target == "1":
        do_set(s, "lead", "idle", "리서치 진행")
        do_set(s, "research", "working", detail or "키워드·근거 조사")
    elif target == "A":
        do_set(s, "research", "done", "리서치 완료")
        do_set(s, "human", "review", detail or "아웃라인 확인")
    elif target == "2":
        do_set(s, "research", "done", "리서치 완료")
        do_set(s, "human", "idle", "")
        do_set(s, "writer", "working", detail or "제목·소제목·본문·FAQ 작성 중")
    elif target == "3":
        do_set(s, "writer", "waiting", "본문 검증 중 — 이미지 생성 대기")
        do_set(s, "seo", "working", "SEO·AEO 자가 점검")
        do_set(s, "fact", "working", detail or "팩트체크 중")
        do_set(s, "lint", "working", "기계 점검 중")
    elif target == "4":
        for agent in ["seo", "fact", "lint"]:
            do_set(s, agent, "done", "검토 완료")
        do_set(s, "writer", "working", detail or "검토 반영·본문 최종 확정 중")
    elif target == "5":
        do_set(s, "writer", "done", "본문 생성·검증·수정 완료")
        do_set(s, "design", "working", detail or "확정 제목·소제목·내용에 맞춰 이미지 생성 중")
    elif target == "6":
        if s["agents"]["design"]["state"] != "done":
            raise ValueError("이미지 생성·육안 확인 완료를 기록한 뒤 마무리로 이동하세요")
        do_set(s, "design", "done", "이미지 생성·육안 확인 완료")
        do_set(s, "lead", "working", detail or "이미지 배치·게시 HTML·최종 검사 중")
    elif target == "B":
        do_set(s, "lead", "done", "게시 파일·검사 완료")
        do_set(s, "human", "review", detail or "최종 확인 대기")
    elif target == "done":
        do_set(s, "human", "done", "최종 확인 완료")
        s["finished"] = True
        add_log(s, "lead", detail or "작업 완료 — 블로그 발행은 사람이 직접", "finish")
    s["stage"] = target
    add_log(s, "lead", f"단계 {target}", "stage", stage=target)


def open_js(d, with_state=True):
    html = OFFICE_HTML.read_text(encoding="utf-8").replace(
        "<head>", "<head><script>window.__HARNESS_NO_POLL=1</script>", 1)
    js = "document.open();document.write(" + json.dumps(html, ensure_ascii=True) + ");document.close();"
    if with_state:
        js += "window.__harnessPush(" + json.dumps(load(d), ensure_ascii=True) + ");"
    return js + "'office ready'"


def main():
    p = argparse.ArgumentParser(description="블로그 작업 상태와 실제 진행 화면")
    p.add_argument("--dir", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("init"); c.add_argument("--task", required=True); c.add_argument("--mirror"); c.add_argument("--no-copy", action="store_true")
    c = sub.add_parser("go"); c.add_argument("target"); c.add_argument("detail", nargs="*")
    c = sub.add_parser("set"); c.add_argument("agent"); c.add_argument("state", choices=STATES); c.add_argument("detail", nargs="*")
    c = sub.add_parser("log"); c.add_argument("agent", choices=AGENTS); c.add_argument("detail", nargs="+")
    c = sub.add_parser("article-ready"); c.add_argument("--package", required=True); c.add_argument("--review", required=True)
    c = sub.add_parser("serve"); c.add_argument("--port", type=int, default=0)
    sub.add_parser("stop")
    c = sub.add_parser("open-js"); c.add_argument("--no-state", action="store_true")
    c = sub.add_parser("push-js"); c.add_argument("--tail", type=int, default=40)
    args = p.parse_args()
    d = Path(args.dir).resolve(); d.mkdir(parents=True, exist_ok=True)
    try:
        if args.cmd == "serve":
            from progress_server import serve
            serve(d, args.port); return 0
        if args.cmd == "stop":
            from progress_server import stop
            stop(d); return 0
        if args.cmd == "open-js":
            print(open_js(d, not args.no_state)); return 0
        if args.cmd == "push-js":
            s = load(d); s["log"] = s["log"][-args.tail:]
            print("window.__harnessPush(" + json.dumps(s, ensure_ascii=True) + ")"); return 0
        with locked(d):
            if args.cmd == "init":
                s = fresh(args.task)
                (d / "article-ready.json").unlink(missing_ok=True)
                if args.mirror:
                    s["mirror"] = str(Path(args.mirror).resolve()); Path(s["mirror"]).mkdir(parents=True, exist_ok=True)
                add_log(s, "lead", "작업 시작", "stage", stage="0")
                if not args.no_copy:
                    for target in {d, Path(s.get("mirror") or d)}:
                        shutil.copyfile(OFFICE_HTML, target / "office.html")
            else:
                s = load(d)
                if args.cmd == "article-ready":
                    from article_state import finalize_article
                    if s["stage"] != "4" or Path(args.package).resolve().parent != d:
                        raise ValueError("4단계 수정 완료 후 같은 작업 폴더의 원고를 확정하세요")
                    marker = finalize_article(args.package, args.review)
                    add_log(s, "writer", "검토·수정 완료 원고 확정: " + marker["sha256"][:12])
                elif args.cmd == "go":
                    if args.target == "done":
                        delivery = json.loads((d / "assets-urls.json").read_text(encoding="utf-8"))
                        if delivery.get("pushed") is not True:
                            raise ValueError("Git 업로드 미완료: 로컬 파일만으로 완료 처리할 수 없습니다")
                        if not delivery.get("files") or delivery.get("check", {}).get("fail"):
                            raise ValueError("공개 이미지 주소가 없거나 실패했습니다")
                        verification = delivery.get("check", {})
                        if verification.get("ok") != len(delivery["files"]) or verification.get("unverified", 0):
                            raise ValueError("공개 이미지 접근 검증이 아직 완료되지 않았습니다")
                    if args.target == "5":
                        from article_state import require_ready
                        require_ready(d / "article-package.md")
                    go_to(s, args.target, " ".join(args.detail))
                elif args.cmd == "set":
                    if args.agent == "design" and args.state == "working" and s["stage"] != "5":
                        raise ValueError("이미지 생성은 본문 확정 후 5단계에서 시작하세요")
                    do_set(s, args.agent, args.state, " ".join(args.detail))
                elif args.cmd == "log":
                    add_log(s, args.agent, " ".join(args.detail))
            save(d, s)
        print(f"[status] {args.cmd}: 기록됨 (단계 {s['stage']}, seq={s['seq']})")
        if args.cmd == "init":
            print(f"[status] 화면 파일: {d / 'office.html'}")
            print("[status] serve 실행 후 출력 URL을 실제 브라우저에 여세요. init만으로 화면이 열리지는 않습니다.")
    except Exception as exc:
        print(f"[status] 실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

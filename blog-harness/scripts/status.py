#!/usr/bin/env python3
"""블로그 하네스 진행 상황을 status.json과 status.js에 기록한다 (사무실 애니메이션 office.html용).
office.html은 status.js를 1초마다 다시 불러오므로 더블클릭으로 열어도 실시간으로 움직이고,
기록이 한꺼번에 몰려 들어와도 로그를 한 장면씩 순서대로 재생한다.

가장 간단한 사용법 (단계가 바뀔 때마다 한 줄):
    python3 status.py --dir 작업폴더 init --task "주제"
    python3 status.py --dir 작업폴더 go 0          # 입력 카드
    python3 status.py --dir 작업폴더 go 1          # 리서치 시작
    python3 status.py --dir 작업폴더 go A          # (선택) 아웃라인 승인 요청
    python3 status.py --dir 작업폴더 go 2          # 리서치 끝 → 초안 작성 시작
    python3 status.py --dir 작업폴더 go 3          # 초안 끝 → 검토 3명 병렬 시작
    python3 status.py --dir 작업폴더 go 4          # 검토 끝 → 수정 시작
    python3 status.py --dir 작업폴더 go 5          # 수정 끝 → 썸네일·인포그래픽 제작 시작
    python3 status.py --dir 작업폴더 go B          # 이미지 끝 → 사람 최종 확인
    python3 status.py --dir 작업폴더 go done       # 사람 승인 후
  go 뒤에 문구를 붙이면 그 단계 담당자의 말풍선이 된다:  go 2 "초안 v1: FAQ 작성 중"

세부 기록 (선택):
    set <에이전트> <상태> "문구"      handoff <보낸이> <받는이,받는이> "문구"
    log <에이전트> "문구"             stage <단계> [--round N]      finish "문구"

에이전트 id: lead research writer seo fact lint design human
상태: idle working waiting done blocked review

실행 중 오류가 나도 경고만 출력하고 종료코드 0을 돌려준다 (본 작업을 막지 않음).
표준 라이브러리만 사용한다.
"""
import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

AGENTS = ["lead", "research", "writer", "seo", "fact", "lint", "design", "human"]
STATES = ["idle", "working", "waiting", "done", "blocked", "review"]
STATE_KO = {"idle": "대기", "working": "작업 시작", "waiting": "결과 기다림",
            "done": "완료", "blocked": "막힘", "review": "확인 필요"}
STAGES = ["0", "1", "A", "2", "3", "4", "5", "B"]
REVIEWERS = ["seo", "fact", "lint"]
LOG_KEEP = 80
DETAIL_MAX = 60
HERE = os.path.dirname(os.path.abspath(__file__))
OFFICE_HTML = os.path.join(HERE, "..", "assets", "office.html")


# 단계 순서 (A는 1과 2 사이의 선택 단계)
GO_ORDER = ["0", "1", "2", "3", "4", "5", "B", "done"]
GO_RANK = {"0": 0, "1": 1, "A": 1.5, "2": 2, "3": 3, "4": 4, "5": 5, "B": 6, "done": 7}

# 작업 폴더에 생기는 산출물 → 감시자가 단계를 추정하는 근거
REVIEW_FILES = {"review-seo-aeo.md": "seo", "review-facts.md": "fact", "lint-result.txt": "lint"}
WATCH_FILES = ["research-brief.md", "article-package.md", "changelog.md", "visual-plan.json"] + list(REVIEW_FILES)
WATCH_MAX_SECONDS = 4 * 3600


def now():
    return datetime.now().isoformat(timespec="seconds")


def fresh(task):
    return {
        "version": 2, "task": task, "stage": "0", "round": 0, "finished": False, "seq": 0,
        "agents": {a: {"state": "idle", "detail": "", "since": now()} for a in AGENTS},
        "log": [], "updated": now(),
    }


def load(d):
    try:
        with open(os.path.join(d, "status.json"), encoding="utf-8") as f:
            s = json.load(f)
        for a in AGENTS:
            s.setdefault("agents", {}).setdefault(a, {"state": "idle", "detail": "", "since": now()})
        s.setdefault("log", [])
        s.setdefault("seq", 0)
        s.setdefault("round", 0)
        return s
    except FileNotFoundError:
        return fresh("(제목 없음)")


def write_atomic(path, text):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".status-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)  # 원자적 교체: 화면이 반쯤 쓴 파일을 읽지 않게
    except OSError:
        # 동기화 폴더 등에서 이름 바꾸기가 막히면 그냥 덮어쓴다
        try:
            os.remove(tmp)
        except Exception:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def save(d, s):
    s["updated"] = now()
    as_json = json.dumps(s, ensure_ascii=False, indent=1)
    # status.js: office.html을 더블클릭(file://)으로 열어도 읽을 수 있도록 스크립트 형태로도 기록
    as_js = "window.__HARNESS_STATUS = " + json.dumps(s, ensure_ascii=True) + ";\n"
    write_atomic(os.path.join(d, "status.json"), as_json)
    write_atomic(os.path.join(d, "status.js"), as_js)
    # 미러: 작업은 세션 작업공간에서 하고, 사람은 자기 컴퓨터 폴더에서 office.html을 볼 때
    m = s.get("mirror")
    if m and os.path.abspath(m) != os.path.abspath(d):
        try:
            write_atomic(os.path.join(m, "status.js"), as_js)
            write_atomic(os.path.join(m, "status.json"), as_json)
        except Exception as e:
            print(f"[status] 경고: 컴퓨터 폴더({m})에 쓰지 못함 ({e})", file=sys.stderr)


def add_log(s, agent, msg, kind="log", **extra):
    s["seq"] += 1
    entry = {"seq": s["seq"], "t": now(), "agent": agent, "kind": kind, "msg": (msg or "")[:120]}
    entry.update({k: v for k, v in extra.items() if v is not None})
    s["log"].append(entry)
    s["log"] = s["log"][-LOG_KEEP:]


@contextlib.contextmanager
def locked(d):
    """오케스트레이터와 감시자가 동시에 쓰지 않도록 잠근다."""
    if fcntl is None:
        yield
        return
    with open(os.path.join(d, ".status.lock"), "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def check_agent(a):
    if a not in AGENTS:
        raise ValueError(f"알 수 없는 에이전트 '{a}'. 가능한 값: {', '.join(AGENTS)}")


# ---- 기본 동작 ----
def do_set(s, agent, state, detail=""):
    check_agent(agent)
    detail = (detail or "")[:DETAIL_MAX]
    ag = s["agents"][agent]
    if ag.get("state") != state:
        ag["since"] = now()
    ag["state"], ag["detail"] = state, detail
    add_log(s, agent, detail or STATE_KO[state], kind="state", state=state)


def do_stage(s, stage, rnd=None):
    s["stage"] = stage
    if rnd is not None:
        s["round"] = rnd
    label = f"승인 {stage}" if stage in ("A", "B") else f"{stage}단계"
    if s.get("round") and stage in ("3", "4"):
        label += f" ({s['round']}라운드)"
    add_log(s, "lead", f"{label}로 이동", kind="stage", stage=stage, round=s.get("round"))


def do_handoff(s, src, dst, msg=""):
    check_agent(src)
    for x in dst:
        check_agent(x)
    add_log(s, src, msg or "산출물 전달", kind="handoff", to=dst)


def do_finish(s, msg=""):
    s["finished"] = True
    for a in AGENTS:
        if s["agents"][a]["state"] in ("working", "waiting", "review", "blocked"):
            s["agents"][a]["state"] = "done"
    add_log(s, "lead", msg or "작업 완료", kind="finish")


def state_of(s, a):
    return s["agents"][a]["state"]


# ---- 단계 전환 한 줄 명령 ----
def go_to(s, target, detail="", source="go"):
    """target 단계로 이동. 건너뛴 단계가 있으면 순서대로 채워 넣고, 이미 지난 단계면 무시한다."""
    if target not in GO_RANK:
        raise ValueError(f"go 단계는 0 1 A 2 3 4 B done 중 하나: '{target}'")
    if s.get("finished"):
        return "이미 완료된 작업"
    cur = s.get("stage", "0")
    if target == cur == "0" and state_of(s, "lead") == "idle":
        do_set(s, "lead", "working", detail or "입력 카드 정리 중")
        return "기록됨"
    if target == cur:
        main = {"0": "lead", "1": "research", "A": "human", "2": "writer", "3": "seo", "4": "writer",
                "5": "design", "B": "human"}.get(cur)
        if detail and main:
            do_set(s, main, s["agents"][main]["state"], detail)
        return "같은 단계 (문구만 갱신)"
    back_ok = (target == "3" and cur == "4")  # 수정 후 재검토 라운드
    if GO_RANK[target] < GO_RANK[cur] and not back_ok:
        return f"이미 {cur}단계까지 진행되어 무시"
    if not back_ok:
        start = GO_ORDER.index("2") if cur == "A" else GO_ORDER.index(cur) + 1 if cur in GO_ORDER else 0
        end = GO_ORDER.index(target) if target in GO_ORDER else GO_ORDER.index("2")
        missed = GO_ORDER[start:end]
        if missed:
            add_log(s, "lead", f"빠진 단계 {', '.join(missed)} 기록을 채움 ({source})", kind="log")
            for m in missed:
                do_go(s, m)
    do_go(s, target, detail)
    return "기록됨"


def do_go(s, target, detail=""):
    A = s["agents"]
    if target == "0":
        do_stage(s, "0")
        do_set(s, "lead", "working", detail or "입력 카드 정리 중")
    elif target == "1":
        if state_of(s, "lead") == "working":
            do_set(s, "lead", "idle", "리서치에 넘김")
        do_stage(s, "1")
        do_set(s, "research", "working", detail or "키워드·검색의도 리서치 중")
    elif target == "A":
        if state_of(s, "research") != "done":
            do_set(s, "research", "done", "리서치 브리프 완성")
        do_handoff(s, "research", ["human"], "키워드·아웃라인")
        do_stage(s, "A")
        do_set(s, "human", "review", detail or "키워드·아웃라인 확인")
    elif target == "2":
        if state_of(s, "lead") == "working":
            do_set(s, "lead", "idle", "")
        if state_of(s, "research") != "done":
            do_set(s, "research", "done", "리서치 브리프 완성")
            do_handoff(s, "research", ["writer"], "리서치 브리프")
        if state_of(s, "human") == "review":
            do_set(s, "human", "done", "아웃라인 승인")
            do_handoff(s, "human", ["writer"], "승인된 아웃라인")
        do_stage(s, "2")
        do_set(s, "writer", "working", detail or "초안 v1 작성 중")
    elif target == "3":
        rnd = (s.get("round") or 0) + 1
        do_set(s, "writer", "waiting", "검토 결과 기다림")
        do_handoff(s, "writer", REVIEWERS, f"초안 v{rnd}")
        do_stage(s, "3", rnd)
        do_set(s, "seo", "working", detail or "제목·구조·AEO 점검 중")
        do_set(s, "fact", "working", "문장별 출처 대조 중")
        do_set(s, "lint", "working", "check_article.py 실행 중")
    elif target == "4":
        for r in REVIEWERS:
            if state_of(s, r) != "done":
                do_set(s, r, "done", A[r]["detail"] if state_of(s, r) == "blocked" else "검토 완료")
                do_handoff(s, r, ["writer"], "수정지시")
        do_stage(s, "4", s.get("round") or 1)
        do_set(s, "writer", "working", detail or f"수정 {s.get('round') or 1}라운드 반영 중")
    elif target == "5":
        do_set(s, "writer", "done", "최종 원고 확정")
        do_handoff(s, "writer", ["design"], "확정 원고")
        do_stage(s, "5")
        do_set(s, "design", "working", detail or "썸네일·인포그래픽 스티커 배치 중")
    elif target == "B":
        if state_of(s, "writer") != "done":
            do_set(s, "writer", "done", "최종 패키지 완성")
        if state_of(s, "design") != "done":
            do_set(s, "design", "done", "이미지 완성")
        do_handoff(s, "design", ["human"], "기사 패키지 + 이미지")
        do_stage(s, "B")
        do_set(s, "human", "review", detail or "발행 전 최종 확인")
    elif target == "done":
        if state_of(s, "human") == "review":
            do_set(s, "human", "done", "승인")
        do_finish(s, detail or "사람 승인 완료")
    else:
        raise ValueError(f"go 단계는 0 1 A 2 3 4 B done 중 하나: '{target}'")


# ---- 감시자: 산출물 파일이 생기거나 바뀌면 단계를 자동으로 진행 ----
def scan(d):
    out = {}
    for name in WATCH_FILES:
        try:
            out[name] = os.stat(os.path.join(d, name)).st_mtime
        except OSError:
            pass
    return out


def on_file(s, name):
    cur = s.get("stage", "0")
    if s.get("finished"):
        return
    if name == "research-brief.md" and GO_RANK.get(cur, 0) < 2 and cur != "A":
        go_to(s, "2", source="research-brief.md 감지")
    elif name == "article-package.md" and GO_RANK.get(cur, 0) < 2:
        go_to(s, "2", source="article-package.md 감지")
    elif name in REVIEW_FILES:
        r = REVIEW_FILES[name]
        if cur == "4" or GO_RANK.get(cur, 0) < 3:
            go_to(s, "3", source=f"{name} 감지")
        if s["agents"][r]["state"] != "done":
            do_set(s, r, "done", "검토 결과 저장됨")
            do_handoff(s, r, ["writer"], {"seo": "SEO·AEO 검토표", "fact": "사실검증표", "lint": "기계 점검 결과"}[r])
    elif name == "changelog.md" and GO_RANK.get(cur, 0) < 4:
        go_to(s, "4", source="changelog.md 감지")
    elif name == "visual-plan.json" and GO_RANK.get(cur, 0) < 5:
        go_to(s, "5", source="visual-plan.json 감지")


def watch(d, token):
    seen = scan(d)
    t0 = time.time()
    while time.time() - t0 < WATCH_MAX_SECONDS:
        time.sleep(1.5)
        try:
            cur = scan(d)
            changed = [n for n in WATCH_FILES if n in cur and cur[n] != seen.get(n)]
            seen = cur
            with locked(d):
                s = load(d)
                if s.get("watcher") != token or s.get("finished"):
                    return  # 새 작업이 시작됐거나 끝남
                before = s["seq"]
                for name in changed:
                    on_file(s, name)
                if s["seq"] != before:
                    save(d, s)
        except Exception:
            pass


def start_watcher(d, token):
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--dir", d, "watch", "--token", token],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True)
        return True
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description="하네스 진행 상황 기록")
    p.add_argument("--dir", default=".", help="작업 폴더 (기본: 현재 폴더)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("init"); c.add_argument("--task", required=True)
    c.add_argument("--mirror", help="사람이 office.html을 여는 컴퓨터 폴더 경로 (작업 폴더와 다를 때)")
    c.add_argument("--no-copy", action="store_true", help="office.html을 복사하지 않음")
    c = sub.add_parser("go"); c.add_argument("target"); c.add_argument("detail", nargs="*")
    c = sub.add_parser("push-js", help="내장 브라우저 javascript_tool에 넣을 한 줄 출력 (화면이 안 바뀔 때)")
    c = sub.add_parser("stage"); c.add_argument("stage", choices=STAGES); c.add_argument("--round", type=int)
    c = sub.add_parser("set"); c.add_argument("agent"); c.add_argument("state", choices=STATES); c.add_argument("detail", nargs="*")
    c = sub.add_parser("handoff"); c.add_argument("src"); c.add_argument("dst"); c.add_argument("msg", nargs="*")
    c = sub.add_parser("log"); c.add_argument("agent"); c.add_argument("msg", nargs="+")
    c = sub.add_parser("finish"); c.add_argument("msg", nargs="*")
    c = sub.add_parser("watch"); c.add_argument("--token", required=True)
    args = p.parse_args()
    d = os.path.abspath(args.dir)

    try:
        os.makedirs(d, exist_ok=True)
        if args.cmd == "watch":
            watch(d, args.token)
            return
        if args.cmd == "init":
            s = fresh(args.task)
            s["watcher"] = uuid.uuid4().hex[:12]
            if args.mirror:
                s["mirror"] = os.path.abspath(args.mirror)
                os.makedirs(s["mirror"], exist_ok=True)
            add_log(s, "lead", f"작업 시작: {args.task}", kind="stage", stage="0")
            with locked(d):
                save(d, s)
            watching = start_watcher(d, s["watcher"])
            view_dir = s.get("mirror") or d
            if not args.no_copy and os.path.exists(OFFICE_HTML):
                for target in {d, view_dir}:
                    shutil.copyfile(OFFICE_HTML, os.path.join(target, "office.html"))
            print(f"[status] 준비 완료: {os.path.join(view_dir, 'office.html')}")
            if s.get("mirror"):
                print(f"[status] 진행 상황은 {view_dir} 에도 자동으로 계속 복사돼요 (감시자 포함)")
            print("[status] 이 파일을 더블클릭해서 브라우저로 열어 두면 진행 상황이 실시간으로 보여요 (서버 필요 없음)")
            if watching:
                print("[status] 산출물 파일 감시 시작: research-brief.md, review-*.md 등이 저장되면 단계가 자동으로 넘어가요")
            return

        if args.cmd == "push-js":
            # office.html에 상태를 직접 밀어 넣는 코드 (파일 읽기가 막힌 화면용)
            print("window.__harnessPush(" + json.dumps(load(d), ensure_ascii=True) + ")")
            return
        lock = locked(d)
        lock.__enter__()
        s = load(d)
        result = "기록됨"
        if args.cmd == "go":
            result = go_to(s, args.target, " ".join(args.detail))
        elif args.cmd == "stage":
            do_stage(s, args.stage, args.round)
        elif args.cmd == "set":
            do_set(s, args.agent, args.state, " ".join(args.detail))
        elif args.cmd == "handoff":
            do_handoff(s, args.src, [x.strip() for x in args.dst.split(",") if x.strip()], " ".join(args.msg))
        elif args.cmd == "log":
            check_agent(args.agent)
            add_log(s, args.agent, " ".join(args.msg))
        elif args.cmd == "finish":
            do_finish(s, " ".join(args.msg))
        save(d, s)
        lock.__exit__(None, None, None)
        print(f"[status] {args.cmd} {getattr(args, 'target', '')}: {result}".replace("  ", " "))
    except Exception as e:
        print(f"[status] 경고: 상태 기록 실패 ({e}). 본 작업은 계속 진행하세요.", file=sys.stderr)


if __name__ == "__main__":
    main()

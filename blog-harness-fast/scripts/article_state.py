"""Track the reviewed text used to derive visuals; image insertion does not alter it."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from check_article import check


def article_context(package):
    raw = Path(package).read_text(encoding="utf-8-sig")
    sections = dict(re.findall(r"<!--\s*BEGIN:(\w+)\s*-->(.*?)<!--\s*END:\1\s*-->", raw, re.S))
    body = sections.get("body_google", "")
    # Only standalone Markdown images may be inserted after finalizing the text.
    body = re.sub(r"(?m)^\s*!\[[^\]\n]*\]\([^\n]+\)\s*$", "", body)
    clean = lambda s: "\n".join(line.rstrip() for line in s.strip().splitlines() if line.strip())
    body = clean(body)
    titles = re.findall(r"(?m)^# (.+)$", body)
    headings = re.findall(r"(?m)^## (.+)$", body)
    if not titles or not headings or not sections.get("faq", "").strip():
        raise ValueError("본문 H1·H2·FAQ를 완성한 후 원고를 확정하세요")
    text = {"titles": clean(sections.get("titles", "")), "body_google": body,
            "faq": clean(sections["faq"])}
    digest = hashlib.sha256(json.dumps(text, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {"sha256": digest, "title": titles[0], "headings": headings, "text": text}


def finalize_article(package, review):
    package, review = Path(package).resolve(), Path(review).resolve()
    if not review.is_file() or not review.read_text(encoding="utf-8-sig").strip():
        raise ValueError("팩트체크 결과 파일이 필요합니다. 검토·수정이 끝난 뒤 실행하세요")
    report = check(package.read_text(encoding="utf-8-sig"), final=False, base_dir=str(package.parent))
    if report.failed:
        raise ValueError("check_article FAIL이 남아 있어 원고를 확정할 수 없습니다")
    context = article_context(package)
    marker = {k: v for k, v in context.items() if k != "text"}
    marker.update(finalized_at=datetime.now(timezone.utc).isoformat(), review=review.name,
                  note="검토·수정 완료를 작업자가 확인한 원고. 의미상 사실검증을 자동 보증하지 않음")
    (package.parent / "article-ready.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return marker


def require_ready(package, plan=None):
    package = Path(package).resolve()
    marker_path = package.parent / "article-ready.json"
    if not marker_path.is_file():
        raise ValueError("ARTICLE_NOT_READY: 검토·수정 완료 후 status.py article-ready --package … --review …를 실행하세요")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    context = article_context(package)
    if marker.get("sha256") != context["sha256"]:
        raise ValueError("ARTICLE_CHANGED: 확정 후 제목·소제목·본문·FAQ가 바뀌었습니다. 재검토·재확정 후 이미지 계획을 다시 작성하세요")
    if plan is not None:
        if plan.get("article_sha256") != context["sha256"]:
            raise ValueError("PLAN_STALE: visual-plan.json의 article_sha256을 현재 확정 원고에서 가져오세요")
        for image in plan.get("images", []):
            anchor = image.get("article_section")
            allowed = ["__title__"] if image.get("type") == "thumbnail" else context["headings"]
            if anchor not in allowed:
                raise ValueError(f"ARTICLE_SECTION: {image.get('id')}의 article_section은 썸네일은 __title__, 본문 이미지는 실제 H2여야 합니다")
    return context

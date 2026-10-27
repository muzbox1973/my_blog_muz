# 개정 검증 결과 — 2026-10-27

버전: 2026.10.27-fast4. 실제 실행 결과이며 원래 tests/test-plan.md의 과거 기록과 구분한다.

| 검사 | 결과 |
|---|---|
| 회귀 테스트 | 20/20 통과 (원고 확정·변경 감지, SEO/AEO, 사용자 이미지, Git 대상·Windows 줄바꿈, 상태 서버) |
| 실제 Chromium 화면 | 글/이미지/마무리 상태 전환, 로딩 회전·캔버스 움직임, 오류 시 회전 정지, 연결 끊김, 모션 줄이기 통과 |
| JavaScript 실행 오류 | 0건 |
| 제공 이미지만 사용 | 원본 2장 해시 일치, 새 렌더 HTML 0개 |
| 혼합 이미지 처리 | 제공 썸네일 1장 원본 유지 + 빈 자리 1장만 새 WebP 제작, FAIL 0 / WARN 0 |
| 게시 파일 생성 | post-google.html·preview.html·titles-hashtags.md 생성 성공 |
| Git 동작 검사 | 임시 로컬 bare 저장소에서 실제 push 성공, 대상 누락·브랜치 불일치·no-push 차단 |
| 스킬 형식 | quick_validate.py 통과 |

재실행: `python -m unittest discover -s tests -p "test_*.py" -v`, `python tests/browser_check.py`.
브라우저 검사에는 Python Playwright와 Chromium, 이미지 검사에는 Pillow가 필요하다.

한계: 회귀 테스트의 원고·사진·팩트체크 기록은 시험용 fixture다. 새 기사의 사실관계를 검증했다는 뜻이 아니다. 실제 WordPress·Tistory 발행과 원격 GitHub 쓰기는 위 로컬 테스트에 포함되지 않는다. HTML/JS 애니메이션은 별도 브라우저 화면에서 실행되며 채팅 내 표시는 호스트 지원에 달려 있다. 해시·파일 검사는 이미지의 의미 적합성이나 사실 정확성을 자동 보증하지 않는다.

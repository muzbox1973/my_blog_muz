# blog-harness-fast

blog-seo-aeo-harness-fast 작업 폴더입니다 (구글판 전용).

- `scripts/` 하네스 스크립트 (스킬이 여기 있는 것을 실행)
- `assets/stickers/` 스티커
- `posts/<글>/` 기사 패키지, 이미지(`visuals/`), 게시용 HTML(`post-google.html`), 제목·해시태그

본문 HTML의 이미지는 이 저장소의 커밋 주소를 가리키므로 **저장소가 공개(public)** 여야 블로그에서 보입니다.


## 2026.10.27-fast4 개정

- 기사 실행 시 Git 저장소 URL·브랜치·저장 경로를 먼저 확인합니다. 로컬 산출물을 Git 업로드 완료로 대체하지 않습니다.
- 사용자 이미지를 먼저 확인·활용하고, 원고 검증·수정·확정 이후 부족한 이미지만 제작합니다.
- 실제 단계별 상태와 사무실 애니메이션을 별도 브라우저 진행 화면에서 표시합니다. 채팅 내 실행은 호스트의 HTML/JS 지원에 달려 있습니다.
- `repo_setup.py`는 --remote-url, --branch, --base 인자가 필요합니다. 기존 설정 main / blog-harness-fast를 유지했습니다.
- Windows CRLF 줄바꿈만 바뀐 경우 사용자 코드 수정으로 오인하지 않도록 고쳤습니다. 사용자 스티커와 기존 글은 보존했습니다.
- 전체 스킬 ZIP, 검증 기록과 화면: [skill-packages/2026.10.27-fast4](skill-packages/2026.10.27-fast4/).
- 회귀 테스트 20개 및 실제 Chromium 검증 통과. 전체 지침·테스트 소스는 ZIP에 포함되어 있습니다.

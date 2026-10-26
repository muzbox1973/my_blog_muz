# 팩트체크 결과: 팀장이 알려주는 상황별 프롬프트 10개

> 검토일: 2026-10-26 · 대상: article-package.md v1 · 외부 재확인: 실시 (근거 URL 3개 모두 원문 열람)
> - Google Prompting Guide 101 PDF: WebFetch로 원문 확인(표지 "April 2024 edition"). curl 직접 다운로드는 프록시 차단, WebFetch는 정상.
> - OpenAI Help Center "Prompt engineering best practices for ChatGPT": 원문 확인
> - Anthropic Claude Docs "Be clear and direct": 원문 확인

## 판정: 수정 필요 (경미 2건)

## 요약: 사실 주장 10건 중 일치 8 / 부분일치(수정 필요) 2 / 근거없음 0 / 불일치 0 · 별도로 일반상식 4 · 저자 진술/의견 7

## 판정표

| # | 위치 | 주장 문장(요지) | 근거# | 판정 | 원문 대조 / 정정 제안 |
|---|---|---|---|---|---|
| 1 | "팀장은 왜…" 1문단 | Anthropic은 Claude 공식 문서에서 AI를 "뛰어나지만 회사 사정을 모르는 신입 직원"처럼 생각하고, 정확히 설명할수록 결과가 좋아진다고 안내 | 5 | 일치 | 원문: "Think of Claude as a brilliant but new employee who lacks context on your norms and workflows. The more precisely you explain what you want, the better the result." 취지 일치. (선택) 원문 대상은 "AI"가 아니라 "Claude", "회사 사정"은 "규범과 업무 방식" |
| 2 | "팀장은 왜…" 2문단 | 구글 2024년 4월판 가이드 기준, 성공적인 프롬프트 평균 약 21단어, 흔히 시도하는 프롬프트 9단어 미만(영어 단어 기준) | 2 | **부분일치 → 수정 필요** | 원문: "Based on what we have learned during our Workspace Labs program, the most successful prompts average around 21 words" / "prompts people often try … usually less than nine words." ① 수치의 출처인 **Workspace Labs 프로그램** 맥락이 빠짐 ② "가장 성공적인(most successful)"이 "성공적인"으로 약해짐 ③ "usually(대개)"가 빠져 단정이 됨 ④ "영어 단어 기준"은 원문에 명시 없음(영문 가이드라는 사실에서 나온 추론) |
| 3 | "어떤 틀로 쓰나요?" 1문단 | 구글 가이드는 효과적인 프롬프트의 네 영역으로 페르소나·작업·맥락·형식을 꼽고, 네 개를 모두 쓸 필요는 없다고 설명 | 1 | 일치 | 원문: Persona / Task / Context / Format, "You don't need to use all four, but using a few will help!" (선택) "몇 개만 써도 도움이 된다"를 덧붙이면 더 정확 |
| 4 | "메일·회의…" 1문단 | OpenAI 도움말 센터는 원하는 어조를 "정중한", "친근한" 같은 형용사로 알려 주라고 권함 | 4 | **부분일치 → 수정 필요** | 원문: "Use descriptive adjectives to indicate the tone. Words like formal, informal, friendly, professional, humorous, or serious." 형용사로 어조를 지정하라는 취지는 일치. 다만 **"정중한(polite)"은 원문 예시에 없음**. formal은 "격식 있는"에 가까움 |
| 5 | "엑셀·대외 응대…" 1문단 | Anthropic 문서는 순서나 빠짐없는 진행이 중요하면 지시를 번호 목록 단계로 주라고 안내 | 5 | 일치 | 원문: "Provide instructions as sequential steps using numbered lists or bullet points when the order or completeness of steps matters." (선택) 원문은 "번호 목록이나 글머리표" |
| 6 | "AI 답이 마음에 안 들면…" 1문단 | 구글 가이드와 OpenAI 도움말 센터 모두 응답을 보고 다듬는 반복 과정을 권함 | 3, 4 | 일치 | 구글: "Use follow-up prompts and an iterative process of review and refinement to yield better results." / OpenAI: "Start with an initial prompt, review the response, and refine the prompt based on the output." |
| 7 | "AI 답이 마음에 안 들면…" 3문단 | Anthropic 문서는 맥락이 적은 동료에게 프롬프트를 보여 줬을 때 헷갈려하면 AI도 헷갈린다는 점검법을 소개 | 5 | 일치 | 원문 "Key test: Show your prompt to a colleague with minimal context on the task and ask them to follow it. If they'd be confused, Claude will be too." (선택) "AI도" → 원문은 "Claude도" |
| 8 | FAQ 1번 (본문 FAQ·§6 FAQ·JSON-LD 3곳 동일) | 구글 가이드는 간결하되 구체적으로 쓰라고 권함 | 3 | 일치 | 원문 "Be concise and avoid complexity. State your request in brief — but specific — language." |
| 9 | §11 참고자료 | 구글 가이드 2024년 4월판, OpenAI·Anthropic 문서명·URL | 1–5 | 일치 | 표지 "April 2024 edition" 확인. 3개 URL 모두 접속·제목 일치. 단, 1~3번이 같은 문서로 3번 반복됨(사실 오류 아님, 아래 '사람이 확인' 참고) |
| 10 | 마무리 내부 링크 | 「프롬프트 잘 쓰는 법, 저는 질문보다 규칙을 먼저 씁니다」 | 저장소 | 일치 | blog-harness/posts/20261026-prompt-rules-first/article-package.md 제목과 동일 |

### 일반상식 (출처 불필요)
- "일을 시작하기 전 질문 목록을 만들어 두면 다시 하는 일을 줄일 수 있어요" — 일반 업무 조언
- "읽는 사람이 정해지면 AI가 분량과 용어 수준을 맞추기 쉬워져요" — 일반 조언(근거#5의 '맥락 제공' 취지와도 어긋나지 않음)
- "받는 사람, 어조, 다음 행동을 함께 적어 주면 결과가 안정돼요" — 일반 조언
- FAQ 3번 "이 글의 템플릿은 대화형 AI라면 어디에나 쓸 수 있어요" — 템플릿이 일반 자연어 지시라 타당

### 저자 진술/의견 (출처 불필요, 표지 확인됨)
- "그래서 저는 … 더 쓸모 있는 조언이라고 생각해요"
- "이 표가 곧 프롬프트 작성법의 뼈대예요"
- "엑셀, 고객 응대, 인수인계처럼 실수 비용이 큰 일은 … 프롬프트가 좋아요"
- "제가 권하는 원칙은 아래 세 가지예요" + 보안·대조·책임 3원칙
- "직장인 AI 활용의 기본기라고 생각해요"
- FAQ 2번 "팀 단위로 템플릿을 모아 두면 신입도 같은 수준의 결과를 내기 쉬워져요" — 의견성 조언(단정 수위 낮음, 유지 가능)
- FAQ 4번 "제가 권하는 순서는…"

## 수정 지시 (위치 → 현재 문장 → 바꿀 문장)

1. "팀장은 왜…" 2문단 두 번째 문장
   → 현재: 구글의 2024년 4월판 「Gemini for Google Workspace 프롬프트 가이드 101」 기준으로, 성공적인 프롬프트는 평균 약 21단어였고 사람들이 흔히 시도하는 프롬프트는 9단어 미만이었어요(영어 단어 기준). [근거#2]
   → 바꿀: 구글의 「Gemini for Google Workspace 프롬프트 가이드 101」(2024년 4월판)은 Workspace Labs 프로그램에서 가장 성공적이었던 프롬프트가 평균 약 21단어였고, 사람들이 흔히 시도하는 프롬프트는 대개 9단어 미만이었다고 밝혀요(영문 가이드 기준). [근거#2]

2. "메일·회의…" 1문단 두 번째 문장
   → 현재: OpenAI 도움말 센터도 원하는 어조를 "정중한", "친근한" 같은 형용사로 알려 주라고 권해요. [근거#4]
   → 바꿀: OpenAI 도움말 센터도 원하는 어조를 "격식 있는", "친근한" 같은 형용사로 알려 주라고 권해요. [근거#4]

(선택, 정확도 향상) 
- "팀장은 왜…" 1문단 → "AI를 "뛰어나지만 회사 사정을 모르는 신입 직원"처럼" → "Claude를 "뛰어나지만 팀의 규칙과 업무 방식을 모르는 신입 직원"처럼"
- "AI 답이…" 3문단 → "헷갈려하면 AI도 헷갈린다는" → "헷갈려하면 Claude도 헷갈린다는"

## 위험 문장
- YMYL·실명 인물 부정 서술·최상급 단정 없음.
- 인용은 모두 짧은 의역 수준이라 저작권 우려 없음.
- 가공 경험: 없음. 1인칭 경험 자리는 `[경험 보강 필요]` 표시로 비워 둠(정상).

## 사람이 확인해야 할 것
- **"팀장" 시점**: 입력 카드에 팀장 직함·팀원 지도 사례 진술이 없음. 제목·H1·도입부가 "팀장이 신입에게 알려주는" 화자로 읽히므로, 저자가 실제 그 입장이 아니라면 표현 조정 필요(기사 §13에도 이미 표시됨).
- `[경험 보강 필요]` 자리: 실제 사례로 채우거나 발행 전 삭제.
- §11 참고자료 1~3번이 같은 PDF로 세 번 반복됨 → 발행본 표기 시 1개로 합치고 근거 번호(#1~#3)를 같은 출처로 묶을지 결정.
- 갱신 확인: 구글 가이드는 2024년 4월판(기준일 2년 이상 경과). 후속판이 나오면 21단어·9단어 수치 재확인.

---
일치 8 / 수정 필요 2 / 근거 없음 0

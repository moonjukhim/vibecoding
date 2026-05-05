### Lab1 

```text
LangGraph를 이용한 AI 업계 오늘자 뉴스 Top5 요약 에이전트 시스템의 코드를 작성해줘.
사용자의 요청을 처리하기 위해 Planner → Tool → Filter → Summarize → Output 단계로 구성해줘.
모델은 openai의 모델을 사용하는 구조로 작성해줘.
출력은 코드만 반환해줘.
---

[단계별 내용]

1. Planner 단계
- 요청을 분석하여 검색 전략을 수립하라.
- 검색 키워드를 3~5개 생성하라.
- 최신성(오늘), 신뢰성(언론사), 관련성(AI 산업)을 기준으로 전략을 설명하라.

2. Tool 단계
- 웹 검색을 수행했다고 가정하고, AI 관련 최신 뉴스 후보를 최소 7~10개 생성하라.
- 각 뉴스는 다음 정보를 포함하라:
  - 제목
  - 출처
  - 날짜
  - 간단 요약 (1~2문장)

3. Filter 단계
- 중복 기사 제거
- 신뢰도 평가 (언론사, 내용 기준)
- 최종적으로 가장 중요한 5개 뉴스만 선정
- 선정 이유를 간단히 설명

4. Summarize 단계
- 선택된 5개 뉴스 각각을 3줄 이내로 핵심 요약
- 기술/산업 관점에서 의미를 포함할 것

5. Output 단계
- 최종 결과를 Markdown 형식의 리포트로 작성하라
- 아래 구조를 반드시 따를 것:

# 🧠 AI 업계 오늘자 뉴스 Top 5

## 1. [뉴스 제목]
- 출처:
- 날짜:
- 요약:
- 의미:

(총 5개)

---

[Output 단계 출력 항목]
- 불필요한 설명 없이 각 단계 결과를 명확히 구분해서 출력
- 각 단계는 다음 형식으로 시작:
  [PLANNER]
  [TOOL]
  [FILTER]
  [SUMMARIZE]
  [OUTPUT]

```

```text
키를 저장하는 .env 파일이 필요 !!!
```

```text
코드를 실행하여 결과를 한글로 result.md 파일에 저장해줘.
```

---

### Lab2 

```text
 todo.bmp의 내용을 실행할 수 있는 이메일을 분류하는 에이전트를 만들어줘. 이메일은 email.csv 파일에 있으며 이 파일을
  읽어서 처리할 수 있는 MCP 구조로 코드를 작성해줘.
```


```text
MCP(Model Context Protocol) 구조로 이메일 분류 에이전트 시스템의 코드를 작성해줘.
입력 데이터는 `emails.csv` 파일이며, 이 파일을 읽어서 처리할 수 있는 MCP 서버와 클라이언트 에이전트를 분리해서 작성해줘.
모델은 OpenAI 모델을 사용하는 구조로 작성해줘.
---

[입력 데이터]
- 파일: `emails.csv` (50건)
- 컬럼: `id, from, subject, body, received_at, true_label`
- `true_label`은 평가용 정답 라벨

[4-Class 라벨 정의]
- URGENT: 즉시 대응 필요 (장애·고객 컴플레인, P1/SEV1, 결제/보안 사고)
- GENERAL: 일반 업무 메일·문의·요청 (회의, 견적, 협업, 일정 조율)
- SPAM: 광고·피싱·자동 발송 (마케팅, 프로모션, 의심 링크)
- INTERNAL: 사내 공지·HR·인사·정책 (총무, 복지, 사내 규정, 교육)

---

[처리 흐름]
1. Loader: CSV → Email[]
2. Classifier: Few-shot 프롬프트로 4분류
3. Labeler: `predicted_label` 컬럼 추가 후 저장
4. Evaluator: 라벨 정답 대비 정확도 산출

---

[파일 구성]

## 1) MCP 서버 (`email_mcp_server.py`)
- `fastmcp`의 `FastMCP`로 서버 인스턴스 생성 (이름: `Email-Classifier-MCP`)
- `.env`에서 `OPENAI_API_KEY` 로드 (`python-dotenv` 사용)
- 다음 4개의 도구를 `@mcp.tool()`로 노출:

  1. **`load_emails(csv_path: str) -> List[Dict]`**
     - CSV를 읽어 row dict 리스트로 반환
     - UTF-8 인코딩

  2. **`classify_email(from_addr: str, subject: str, body: str) -> str`**
     - OpenAI `chat.completions`로 4-class 분류 (모델: `gpt-4o-mini`, temperature=0)
     - 시스템 프롬프트에 라벨 정의 + 4-class 각각 1개씩 Few-shot 예시 포함
     - 응답에서 4개 라벨 중 하나만 추출, 그 외는 `GENERAL`로 폴백

  3. **`save_labeled_csv(input_path: str, output_path: str) -> Dict`**
     - 입력 CSV 로드 → 각 행을 `classify_email`로 분류 → `predicted_label` 컬럼 추가 → 출력 경로에 저장
     - 반환: `{"saved": output_path, "rows": N}`

  4. **`evaluate_accuracy(labeled_csv_path: str) -> Dict`**
     - `true_label` vs `predicted_label` 비교
     - 반환 항목:
       - `total`, `correct`, `accuracy`
       - `per_class`: 클래스별 `tp/fp/fn/support`
       - `mistakes`: 오분류 목록 (`id`, `subject` 60자, `true`, `pred`)

- 마지막에 `if __name__ == "__main__": mcp.run()`

## 2) MCP 클라이언트 에이전트 (`email_agent.py`)
- `fastmcp.Client`로 서버 스크립트(`email_mcp_server.py`)에 stdio 연결
- 비동기(`asyncio`)로 다음 순서대로 도구 호출:
  1. `[1/4] Loader`: `load_emails` → 로드된 건수 / 컬럼명 출력
  2. `[2/4] Classifier + [3/4] Labeler`: `save_labeled_csv` → 저장 경로/건수 출력
  3. `[4/4] Evaluator`: `evaluate_accuracy` → 정확도, 클래스별 precision/recall, 오분류 리스트 출력
- 도구 응답 언래핑 헬퍼(`unwrap`) 포함: `result.data` 우선, 없으면 `content[].text`를 JSON 파싱

---

[경로 상수 (코드 내 하드코딩)]
- `INPUT_CSV  = r"C:\claude\mcp\day3\emails.csv"`
- `OUTPUT_CSV = r"C:\claude\mcp\day3\emails_labeled.csv"`
- `SERVER_SCRIPT = r"C:\claude\mcp\day3\email_mcp_server.py"`

[공통 요구사항]
- Windows 콘솔 한글 깨짐 방지: `sys.stdout.reconfigure(encoding="utf-8")`
- 출력 단계 구분은 `[1/4] Loader`, `[2/4] Classifier + [3/4] Labeler`, `[4/4] Evaluator` 헤더로 명확히 구분
- 클래스별 결과는 다음 형식으로 출력:
  ```
  URGENT   support=10  tp=10  fp= 0  fn= 0  precision=1.00  recall=1.00
  ```
```
### Lab1

##### Before

```text
LangGraph를 사용해 리서치 보고서를 자동 작성하는 멀티에이전트 시스템을 구현해줘. 다음 명세를 그대로 따라줘.
모델은 OpenAI를 사용하도록 작성해줘.

### 1. 아키텍처


[Topic 입력]
     ▼
  Planner       — 주제를 3~5개 섹션으로 분해
     ▼ (Send API로 섹션별 병렬 fan-out)
  Researcher    — Tavily 웹 검색으로 섹션별 자료 수집
     ▼
   Writer       — 자료 기반으로 섹션 초안 작성
     ▼  ◄────────┐
   Critic        │  approved=False면 Writer로 루프백 (최대 2회)
     │           │
     ├───────────┘
     ▼ (모든 섹션 approved)
   Editor        — 서론·결론·참고문헌 추가, 통합
     ▼
[최종 보고서]


### 2. 핵심 패턴 4가지

1. **Send API 병렬화**: 계획된 섹션 수만큼 researcher/writer를 동적으로 동시 실행
2. **Critic 피드백 루프**: 섹션별로 writer↔critic 루프, `MAX_REVISIONS=2`로 무한 루프 방지
3. **Map-Reduce 합성**: 병렬 결과를 Annotated 리듀서로 race-free하게 머지
4. **단계별 상태 누적**: plan → sections → final_report 순으로 공유 상태에 축적
```

##### After

```text
# Single-Agent 5-Stage Research Graph 작성 프롬프트

아래 사양에 맞춰 **단일 파일 Python 코드** (`single_agent.py`) 를 작성해줘.

## 1. 아키텍처

LangGraph 기반의 **Single-Agent 5단계 그래프**.
하나의 LLM 인스턴스가 5개 노드를 모두 실행하며, **sub-agent 없이 노드만 분리**한다.

Plan → Search → Compress → Write → Verify
                  ▲                    │
                  └──── (fail) ────────┘   (조건부 self-correction 엣지)

- **Plan**: sub-question 분해
- **Search**: Tavily Tool 호출
- **Compress**: 긴 evidence 요약 (인용 보존)
- **Write**: 일관된 보고서 작성
- **Verify**: 인용·일관성 검사. 실패 시 Search 로 회귀.

## 2. State (TypedDict)

class State(TypedDict):
    query: str                # 사용자의 메인 쿼리
    subqs: list[str]          # 분해된 sub-question 목록
    evidence: list[Document]  # langchain_core.documents.Document
    notes: dict[str, str]     # sub-q → 압축된 노트
    report: str               # 최종 보고서
    verdict: str              # "pass" | "fail"
    issues: list[str]         # Verify 가 지적한 부족 사항
    loops: int                # Search 재방문 횟수 (무한 루프 방지)

`MAX_LOOPS = 2` 상수로 재시도 한도를 둔다.

## 3. LLM / 도구

- **LLM**: `langchain_openai.ChatOpenAI` 단일 인스턴스를 모듈 전역에 1개만 생성.
  - 모델: `OPENAI_MODEL` env 로 오버라이드 가능, 기본값 `gpt-4o`
  - `temperature=0`, `max_tokens=4096`
  - `api_key=os.getenv("OPENAI_API_KEY")`
- **검색 도구**: `langchain_community.tools.tavily_search.TavilySearchResults`
  - `max_results=5`, `api_key=os.getenv("TAVILY_API_KEY")`
- LLM 호출 헬퍼 두 개를 둔다:
  - `_ask(system, user) -> str`: 평문 응답
  - `_ask_json(system, user) -> dict|list`: JSON 강제 + 코드펜스 제거 후 `json.loads`

## 4. 노드 사양

### plan(state) -> dict
- 시스템 프롬프트: "리서치 플래너. 메인 쿼리를 검증 가능한 3~5개의 sub-question 으로 분해. 각 sub-q 는 독립적으로 웹 검색 가능해야 함."
- 출력 스키마: `{"subqs": [str, ...]}`
- 반환: `subqs`, 빈 `evidence`, 빈 `notes`, 기존 `loops` 유지

### search(state) -> dict
- 기본은 모든 sub-q 검색.
- **재방문(verdict=="fail")** 일 경우, `issues` 를 LLM 에 주어 보강이 필요한 sub-q 만 고른다 (`{"targets": [str, ...]}`). 파싱 실패 시 전체 sub-q 로 폴백.
- 각 sub-q 마다 `tavily.invoke({"query": q})` 호출, 결과를 `Document(page_content=..., metadata={"url":..., "subq": q})` 로 누적.
- 검색 예외는 `[search error] {e}` 형태의 더미 결과로 흡수.
- 반환: 누적 `evidence`, `verdict=="fail"` 인 경우에만 `loops += 1`.

### compress(state) -> dict
- evidence 를 `subq` 별로 그룹화.
- 각 그룹마다 LLM 호출:
  - 시스템: "인용 보존형 요약기. 각 사실 뒤에 [URL] 형태로 출처를 남겨라."
  - 사용자: sub-q + evidence(상한 8000자) → bullet 5~10개
- 반환: `notes: dict[subq, str]`

### write(state) -> dict
- 시스템: "리서치 라이터. notes 만 근거 사용. 모든 사실 문장 끝에 [URL] 인용. 추측·환각 금지."
- 사용자: 메인 쿼리 + notes(JSON) + 구성 지시("1) 요약  2) sub-question 별 답변  3) 결론")
- 반환: `report`

### verify(state) -> dict
- 시스템: "검증자. (a) 모든 사실에 [URL] 인용 (b) 모든 sub-q 에 답변 (c) notes 와 모순 없음 검사."
- 사용자: subqs, notes, report
- 출력 스키마: `{"verdict": "pass"|"fail", "issues": [str, ...]}`
- JSON 파싱 실패 시 `verdict="fail"`, `issues=["verifier parse error"]`.

## 5. 조건부 엣지

def route_after_verify(state) -> str:
    if state["verdict"] == "pass": return END
    if state.get("loops", 0) >= MAX_LOOPS: return END
    return "search"

`add_conditional_edges("verify", route_after_verify, {"search": "search", END: END})`

## 6. 그래프 구성

`build_graph()` 함수가 컴파일된 그래프를 반환:
- 노드 5개 등록
- 엣지: `START→plan→search→compress→write→verify`
- `verify` 에서 위 조건부 엣지

## 7. 엔트리포인트

`if __name__ == "__main__":` 블록에서:
- `query="2025년 한국 전기차 보조금 정책의 주요 변경점은?"` 등 샘플 쿼리로 `app.invoke(init_state)` 실행
- 최종 `verdict`, `issues`, `report` 를 출력

## 8. 코드 스타일

- `from __future__ import annotations`
- 한국어 주석 (간결하게, 노드별 1줄 docstring 정도)
- 타입힌트 사용
- 환경변수: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `OPENAI_MODEL`(선택)

```

### Lab2

1. Docker Desktop 설치

2. 컨테이너 시작

```bash
 docker run -d `
    --name postgres `
    -e POSTGRES_PASSWORD=mysecret `
    -e POSTGRES_USER=postgres `
    -e POSTGRES_DB=mydb `
    -p 5432:5432 `
    -v postgres_data:/var/lib/postgresql/data `
    postgres:16
```

```text
MCP(Model Context Protocol) 구조로 이메일 분류 에이전트 시스템의 코드를 작성해줘.
입력 데이터는 `emails.csv` 파일이며, 이 파일을 읽어서 처리할 수 있는 MCP 서버와 클라이언트 에이전트를 분리해서 작성해줘.
분류가 된 데이터는 postgres localhost:5432에 입력할 수 있도록 MCP 구조로 작성해줘.
모델은 OpenAI 모델을 사용하는 구조로 작성해줘.

아래 사양에 맞춰 **MCP(Model Context Protocol) 기반 이메일 분류 시스템**을 작성해줘.
입력은 `emails.csv`, 분류 결과는 Postgres(localhost:5432)에 저장. 모델은 OpenAI.

## 1. 아키텍처

MCP **서버/클라이언트 분리** 구조. 트랜스포트는 stdio.

emails.csv
    │
    ▼
┌──────────────────┐  stdio (MCP)  ┌──────────────────┐
│  mcp_client.py   │ ◄───────────► │  mcp_server.py   │
│  (Agent)         │                │  (I/O 계층)       │
│                  │                │                  │
│  OpenAI 분류 로직 │                │  CSV 읽기 / DB 쓰기│
└──────────────────┘                └────────┬─────────┘
        │                                    │
        ▼                                    ▼
   OpenAI API                       Postgres :5432

**원칙**: I/O(파일 / DB) 는 **반드시** MCP 서버 도구를 통해서만 한다.
클라이언트는 파일시스템·DB 에 직접 접근하지 않고, OpenAI 호출(분류 로직)과 도구 오케스트레이션만 담당한다.

## 3. 데이터

### 입력: `emails.csv`
컬럼: `id, from, subject, body, received_at, true_label`
- `true_label` ∈ {`URGENT`, `GENERAL`, `INTERNAL`, `SPAM`} (정확도 검증용)

### 카테고리 정의
- `URGENT`   : 즉시 대응 필요 (장애/보안/결제/SLA 위반 등)
- `GENERAL`  : 외부 고객/파트너의 일반 문의·요청
- `INTERNAL` : 내부 직원/팀의 일상적 업무 메일
- `SPAM`     : 광고/피싱/무관한 마케팅

### 출력 테이블: `classified_emails`
# sql
id            SERIAL PRIMARY KEY
email_id      TEXT UNIQUE NOT NULL   -- CSV 의 id
sender        TEXT
subject       TEXT
body          TEXT
received_at   TEXT
true_label    TEXT                    -- 정확도 비교용
category      TEXT NOT NULL           -- 분류 결과
confidence    REAL
reason        TEXT
classified_at TIMESTAMPTZ DEFAULT NOW()

## 9. 결과 검증 쿼리

# sql
-- 카테고리별 분포
SELECT category, COUNT(*) FROM classified_emails GROUP BY category;

-- 정확도 (true_label 활용)
SELECT ROUND(100.0*SUM((category=true_label)::int)/COUNT(*), 1) AS accuracy_pct
FROM classified_emails;

-- 오분류 샘플
SELECT email_id, true_label, category, confidence, subject
FROM classified_emails
WHERE category <> true_label
ORDER BY confidence DESC;

```

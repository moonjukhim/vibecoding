### Lab1

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
```

```text
# MCP 이메일 분류 에이전트 시스템 작성 프롬프트

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

## 2. 파일 구성

| 파일 | 역할 |
|---|---|
| `docker-compose.yml`     | Postgres 16 컨테이너 정의 |
| `requirements.txt`       | Python 의존성 |
| `.env.example`           | 환경변수 템플릿 |
| `mcp_server.py`          | MCP 서버 (도구 노출) |
| `mcp_client.py`          | MCP 클라이언트 에이전트 |

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
```sql
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
```

## 4. 인프라

### `docker-compose.yml`
- 이미지: `postgres:16`
- 컨테이너명: `mcp_email_pg`
- 포트: `5432:5432`
- 환경변수: `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=mysecret`, `POSTGRES_DB=mcp_emails`
- 볼륨: `pgdata:/var/lib/postgresql/data` (영속화)
- `restart: unless-stopped`

### `requirements.txt`

mcp>=1.2.0
openai>=1.40.0
psycopg2-binary>=2.9.9
python-dotenv>=1.0.1
```

### `.env.example`

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=mysecret
PG_DB=mcp_emails


## 5. MCP 서버 (`mcp_server.py`)

### 트랜스포트
- `mcp.server.stdio.stdio_server` 사용
- **중요**: stdio 모드에서 stdout 은 MCP 프로토콜 전용.
  서버 측 로그/에러는 반드시 `sys.stderr` 로만 출력 (`_log()` 헬퍼 정의).

### Postgres 연결
- `psycopg2.connect(**DB_CONFIG)` 헬퍼 함수 `_conn()`
- `DB_CONFIG` 는 env 에서 읽어 구성

### 노출 도구 (3개)

#### 1) `read_emails_csv(file_path: str) -> JSON`
- `csv.DictReader` 로 읽어 `list[dict]` 를 JSON 직렬화해 반환
- 인코딩: `utf-8`, `newline=""`
- inputSchema: `{ file_path: string }` (required)

#### 2) `init_email_table() -> "ok"`
- `CREATE TABLE IF NOT EXISTS classified_emails (...)` 실행
- inputSchema: 빈 객체

#### 3) `insert_classified_email(...) -> "inserted"`
- 한 건 upsert. `ON CONFLICT (email_id) DO UPDATE` 로 재실행 안전.
- 갱신 대상: `category`, `confidence`, `reason`, `classified_at = NOW()`
- inputSchema 필드:
  - `email_id` (required), `sender`, `subject`, `body`, `received_at`, `true_label`
  - `category` (required, enum: URGENT|GENERAL|INTERNAL|SPAM)
  - `confidence` (number 0..1), `reason` (string)
- 누락 키는 `None` 으로 채워 SQL 바인딩 안전화

### 도구 디스패치 패턴 Python

@server.call_tool()
async def call_tool(name, arguments) -> list[TextContent]:
    try:
        if name == "read_emails_csv":   ...
        if name == "init_email_table":  ...
        if name == "insert_classified_email": ...
        raise ValueError(f"unknown tool: {name}")
    except Exception as e:
        _log(f"[server] tool {name} failed: {e!r}")
        return [TextContent(type="text", text=f"ERROR: {e}")]


### 엔트리포인트 Python

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


## 6. MCP 클라이언트 (`mcp_client.py`)

### 연결
- `mcp.client.stdio.stdio_client` + `ClientSession`
- 서버를 자식 프로세스로 기동:
  # python
  StdioServerParameters(
      command=sys.executable,                              # venv 일치
      args=[str(Path(__file__).with_name("mcp_server.py"))],
  )
  
- Windows 콘솔 한글 보호: `sys.stdout.reconfigure(encoding="utf-8")` (try/except)

### OpenAI 분류 로직
- `openai = OpenAI()` (env 의 `OPENAI_API_KEY` 자동 사용)
- 모델: `OPENAI_MODEL` env, 기본값 `gpt-4o-mini`
- `response_format={"type": "json_object"}`, `temperature=0`
- 시스템 프롬프트: 4개 카테고리 정의 + JSON 강제
- 출력 스키마: `{"category": "...", "confidence": 0..1, "reason": "한 문장"}`
- 카테고리가 enum 밖이면 `GENERAL` 로 폴백

### 실행 흐름 (`run(csv_path)`)
1. `session.initialize()`
2. `list_tools()` 결과 출력
3. `call_tool("init_email_table", {})`
4. `call_tool("read_emails_csv", {"file_path": csv_path})`
   → `result.content[0].text` 를 `json.loads`
5. 각 이메일에 대해:
   - `classify_email(openai, email)` → category/confidence/reason
   - `call_tool("insert_classified_email", {...})`
   - 한 줄 진행 로그: `pred vs true` 일치 여부 마크(`✓`), conf, subject 50자
6. 끝: `inserted=N failed=M` 요약

### 엔트리포인트
# python
if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "emails.csv"
    asyncio.run(run(csv_file))


## 7. 코드 스타일

- `from __future__ import annotations`
- 한국어 주석 (간결하게)
- 타입힌트 사용
- 환경변수: `OPENAI_API_KEY`, `OPENAI_MODEL`(선택), `PG_*`
- 서버는 stdout 오염 금지 — 로그는 stderr 로
- `with conn, conn.cursor() as cur:` 패턴으로 커넥션/커서 자동 정리

## 8. 실행 순서

powershell
# 1) Postgres 기동
docker compose up -d

# 2) 의존성
pip install -r requirements.txt

# 3) 환경변수
copy .env.example .env
# .env 의 OPENAI_API_KEY 채우기

# 4) 에이전트 실행 (서버는 클라이언트가 자식 프로세스로 자동 기동)
python mcp_client.py emails.csv

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
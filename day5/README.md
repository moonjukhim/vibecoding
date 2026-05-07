### Lab5-1

```text
 ---
  # 역할
  당신은 LangGraph에 능숙한 시니어 AI 엔지니어다. 아래 사양에 맞춰
  "실습 5-1 — 멀티 에이전트 시장 조사 파이프라인"을 구현하라.

  # 입력 (런타임)
  사용자 질의: "전기차 배터리 시장 동향 조사해줘"
  (질의는 환경변수 LAB_QUERY로 교체 가능해야 한다)

  # 처리 흐름 — LangGraph StateGraph로 구성
  1) Planner 노드
     - 사용자의 한 줄 질의를 서로 독립적이고 병렬 실행 가능한
       하위 작업 3~4개로 분해한다.
     - 각 하위 작업은 {id, title, query} 스키마를 따른다.
     - LLM의 structured output(Pydantic)으로 반환한다.

  2) Workers 노드 (병렬)
     - LangGraph의 Send API로 하위 작업 수만큼 fan-out하여 병렬 실행한다.
     - 각 워커는 (a) 외부 검색으로 근거 스니펫·링크 수집,
       (b) LLM으로 한국어 요약(5~8문장, 수치/기업/연도 인용)을 수행한다.
     - 결과는 {id, title, summary, sources, tokens, seconds, failed} 형태로
       상태에 add 리듀서로 누적된다.

  3) Aggregator 노드
     - 워커 결과를 id 순으로 정렬해 섹션을 합치고,
       맨 앞에 한 문단 Executive Summary를 추가한 마크다운 초안을 생성한다.

  4) Judge 노드 (LLM-as-a-Judge)
     - 초안을 5점 만점으로 채점한다.
       기준: completeness / accuracy / readability / actionability / overall
     - rationale(근거)과 issues(개선점 리스트)를 함께 산출한다.
     - 결과를 즉시 scorecard.json에 저장한다.

  5) HITL 게이트
     - publish 직전 노드에서 interrupt_before로 그래프를 일시정지한다.
     - CLI는 채점 결과와 리포트 미리보기(1500자)를 보여준 뒤
       사용자에게 [y/N] 승인을 받고, update_state로 approved 플래그를
       반영해 그래프를 재개한다.

  6) Publish 노드
     - approved=True일 때만 report.md를 디스크에 기록한다.
     - 거절되면 publish_skipped 메트릭만 남긴다.

  # Metrics — 운영 관찰성
  - 모든 노드는 metrics.jsonl에 한 줄 JSON으로
    {ts, event, tokens?, seconds?, failed?, ...}을 append한다.
  - 이벤트 종류: run_start, planner, worker, aggregator, judge,
    hitl_resume, publish, publish_skipped.

  # 산출물
  - report.md       : 사람이 승인한 최종 한국어 마켓 리포트
  - scorecard.json  : Judge 채점 결과 (점수 + 근거 + 개선점)
  - dashboard.py    : Streamlit 모니터링 화면
                      · 총 토큰 / 누적 시간 / 워커 호출 / 실패 수 / 실패율 KPI
                      · 이벤트 로그 테이블, 이벤트별 누적 시간 막대그래프
                      · Judge 스코어카드 카드뷰 + rationale/issues
                      · 최종 report.md 미리보기

  # 기술 스택 / 제약
  - LangGraph(StateGraph + Send + interrupt_before + MemorySaver)
  - LLM은 OpenAI(ChatOpenAI, 기본 gpt-4o-mini, LAB_MODEL로 교체 가능)
  - 검색은 langchain-community의 무료 검색 도구(예: DuckDuckGoSearchResults)
  - Streamlit + pandas로 대시보드 구성
  - python-dotenv로 .env 로드, OPENAI_API_KEY 사용
  - 의존성은 requirements.txt로 관리

  # 결과물
  다음 파일들을 단일 디렉토리에 생성하라:
  agent.py, dashboard.py, requirements.txt, .env.example

```

1. Node.js 설치

- https://nodejs.org/ko/download



```text
# PoC 평가용 실행 프롬프트

이 파일은 `인증평가_김문주.docx`의 PoC 시나리오를 끝까지 실행시키는 단일 프롬프트입니다.
Claude Code 세션의 입력창에 아래 **--- PROMPT 시작 ---** 부터 **--- PROMPT 끝 ---** 사이의 내용을 그대로 복사해 붙여넣으세요.

## 사전 준비 체크
- [ ] `.mcp.json`의 filesystem / tavily / gmail 서버가 `/mcp`에서 ✓ 표시 (gmail은 claude.ai 통합으로 대체 가능)
- [ ] `.env`에 `TAVILY_API_KEY`, Postgres 정보 입력 완료
- [ ] `node db/apply_reports_schema.js` 1회 실행 (reports 테이블 생성)
- [ ] `node server.js` 실행 중 (포트 3000)
- [ ] `http://localhost:3000/reports` 접근 시 200

---

## 평가 시나리오 (PROMPT)

--- PROMPT 시작 ---

당신은 **Orchestrator** 역할을 맡습니다. 이번 작업은 단독으로 처리하지 말고, 반드시 `.claude/agents/` 하위의 5개 서브에이전트(researcher, analyst, writer, reviewer, publisher)를 **Task Tool**로 위임해 협업하세요. Orchestrator는 자료 수집·작성·평가·발행을 **직접 수행하지 않습니다.**

### 입력 (이번 평가의 고정값)

- `topic`: **B2B 협업 SaaS 시장 조사**
- `project_id`: `report-YYYYMMDD-HHMM` 형식으로 현재 시각 기준 자동 생성
- `recipients`: `moonju.khim@gmail.com`
- 작업공간 루트: `C:/claude/mcp/day5/workspace/{project_id}/`

### 워크플로우 (반드시 이 순서)

1. `project_id` 생성 후 작업공간 디렉터리 보장 (`mkdir -p`)
2. **researcher** 호출 → `raw_data.json` (출처 ≥ 15)
3. **analyst** 호출 → `analysis.md` (경쟁사 매트릭스 ≥ 5사, 핵심 인사이트 5)
4. **writer** 호출 → `draft.md` v1 (15~20p, 모든 수치에 src-id)
5. **reviewer** 호출 → `review.md`
   - `verdict == PASS` (≥80점) → 6번
   - `verdict == REWRITE` 그리고 라운드 < 3 → writer 재호출(피드백 포함) → 다시 5번
   - 라운드 == 3에서도 미달 → 즉시 사용자에게 HITL 요청하고 중단
6. **publisher** 호출 → 게시판 `POST http://localhost:3000/api/reports`로 발행 + Gmail draft 생성 + `publish.log.json` 기록

### Quality Gate (절대 지킬 것)

- Reviewer 임계값: **80점**
- 재작성 루프 상한: **3회**
- Publisher는 `review.md`의 `verdict: PASS` 확인 전에 절대 호출 금지
- Gmail은 반드시 **draft까지만** (자동 send 금지)
- 게시판은 반드시 **HTTP POST `/api/reports`** 사용 (DB 직접 INSERT 금지)

### 단계별 보고

각 서브에이전트 호출 직후 다음을 한 줄씩 출력하세요:
- 단계명, 산출물 파일 경로, 핵심 지표 (예: 출처 17건 / 점수 88점 / 재작성 0회)
- 다음 단계로 진행 또는 루프 진입 여부

### 종료 조건 (Pass / Fail)

**Pass**: 5개 에이전트 핸드오프 성공 + Reviewer 점수 ≥ 80 + `POST /api/reports` 응답 201 + Gmail draft 생성 완료. 마지막에 다음을 보고:
- 게시판 URL: `http://localhost:3000/reports/{id}`
- Gmail draft id
- 최종 점수
- 재작성 루프 횟수
- 총 소요 시간 (목표 30분 이내)

**Fail**: 핸드오프 실패 또는 자동 발행 실패 시 즉시 중단하고 실패 단계·원인을 보고.

이제 워크플로우를 시작하세요.

--- PROMPT 끝 ---

---

## 평가 기준 매핑 (문서 기준)

| 문서 기준 | 검증 방법 |
|---|---|
| 5개 에이전트 Handoff 성공률 95% 이상 | 각 단계 산출물 파일 존재 여부 확인 |
| 전체 워크플로우 30분 이내 완료 | 시작/종료 timestamp 비교 |
| MCP 툴 호출 실패율 5% 이하 | 단계별 보고에서 재시도 발생 횟수 |
| Reviewer 품질 점수 80점 이상 | review.md `total` 필드 |
| 개선 루프 평균 1.5회 이내 수렴 | publish.log.json 또는 단계별 보고 |
| HITL 개입 없이 End-to-End 자동 완료 | 사용자 입력 요청 0건 |

## 사후 점검

평가 종료 후 다음 명령으로 결과를 빠르게 확인할 수 있습니다:

```bash
# 게시판에 보고서가 등록되었는지
curl -sf http://localhost:3000/api/reports 2>/dev/null || curl -sf http://localhost:3000/reports

# 작업공간 산출물 목록
ls C:/claude/mcp/day5/workspace/<project_id>/

# Reviewer 점수
cat C:/claude/mcp/day5/workspace/<project_id>/review.md | head -20

# 최종 발행 로그
cat C:/claude/mcp/day5/workspace/<project_id>/publish.log.json
```

```


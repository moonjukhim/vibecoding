"""
실습 5-1 — 전기차 배터리 시장 동향 조사 에이전트 (LangGraph)

처리 흐름:
  Planner  → 하위 작업 3~4개로 분해
  Workers  → Send API로 병렬 검색·요약
  Aggregator → 섹션 통합·초안 작성
  Judge    → LLM-as-a-Judge 채점 (scorecard.json)
  HITL     → interrupt_before로 발행 전 사람 승인
  Publish  → 승인 시 report.md 기록

산출물: report.md, scorecard.json, metrics.jsonl  (대시보드는 dashboard.py)

실행:
  pip install -r requirements.txt
  set OPENAI_API_KEY=sk-...
  python agent.py
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from operator import add
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).parent
METRICS_FILE = ROOT / "metrics.jsonl"
REPORT_FILE = ROOT / "report.md"
SCORECARD_FILE = ROOT / "scorecard.json"

MODEL = os.environ.get("LAB_MODEL", "gpt-4o-mini")
llm = ChatOpenAI(model=MODEL, temperature=0.2, max_tokens=2048)


# ──────────────────────────── Schemas ────────────────────────────

class Subtask(BaseModel):
    id: str = Field(..., description="짧은 식별자, 예: s1")
    title: str
    query: str = Field(..., description="검색에 사용할 한 줄 질의")


class Plan(BaseModel):
    subtasks: list[Subtask] = Field(..., min_length=3, max_length=4)


class JudgeScore(BaseModel):
    completeness: int = Field(ge=1, le=5)
    accuracy: int = Field(ge=1, le=5)
    readability: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    rationale: str
    issues: list[str] = Field(default_factory=list)


class WorkerResult(TypedDict):
    id: str
    title: str
    summary: str
    sources: list[str]
    tokens: int
    seconds: float
    failed: bool


# ──────────────────────────── State ────────────────────────────

class AgentState(TypedDict, total=False):
    query: str
    plan: list[Subtask]
    worker_results: Annotated[list[WorkerResult], add]
    draft_report: str
    scorecard: dict
    approved: bool
    metrics: Annotated[list[dict], add]


# ──────────────────────────── Helpers ────────────────────────────

def log_metric(event: str, **fields) -> dict:
    record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **fields}
    with METRICS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _tokens(resp) -> int:
    meta = getattr(resp, "usage_metadata", None) or {}
    return int(meta.get("input_tokens", 0)) + int(meta.get("output_tokens", 0))


def _search(query: str, k: int = 4) -> tuple[str, list[str], bool]:
    """DuckDuckGo 검색. 실패 시 (빈 스니펫, [], True) 반환."""
    try:
        from langchain_community.tools import DuckDuckGoSearchResults

        tool = DuckDuckGoSearchResults(num_results=k, output_format="list")
        results = tool.invoke(query)
    except Exception as e:
        return f"(검색 실패: {e})", [], True

    snippet, links = "", []
    if isinstance(results, list):
        for r in results[:k]:
            if isinstance(r, dict):
                links.append(r.get("link") or r.get("url") or "")
                snippet += f"- {r.get('snippet') or r.get('title') or ''}\n"
    elif isinstance(results, str):
        snippet = results
    return snippet, [l for l in links if l], False


# ──────────────────────────── Nodes ────────────────────────────

def planner_node(state: AgentState) -> dict:
    t0 = time.time()
    plan: Plan = llm.with_structured_output(Plan).invoke([
        SystemMessage(content=(
            "당신은 시장 조사 플래너입니다. 사용자의 질문을 서로 독립적이고 "
            "병렬 실행 가능한 3~4개의 하위 작업으로 분해하세요. "
            "각 하위 작업은 명확한 목적과 검색 가능한 query를 가져야 합니다."
        )),
        HumanMessage(content=state["query"]),
    ])
    metric = log_metric("planner", subtasks=len(plan.subtasks), seconds=round(time.time() - t0, 2))
    return {"plan": plan.subtasks, "metrics": [metric]}


def fan_out(state: AgentState):
    """Planner 결과를 worker 노드로 병렬 분배."""
    return [Send("worker", {"subtask": s, "query": state["query"]}) for s in state["plan"]]


def worker_node(payload: dict) -> dict:
    sub: Subtask = payload["subtask"]
    t0 = time.time()
    snippet, sources, failed = _search(sub.query)

    resp = llm.invoke([
        SystemMessage(content=(
            "당신은 시장 조사 분석가입니다. 제공된 검색 스니펫을 근거로 "
            "해당 하위 주제의 핵심 동향을 한국어로 5~8문장 요약하세요. "
            "구체적 수치·기업·연도를 포함하고, 모르는 부분은 솔직히 표시하세요."
        )),
        HumanMessage(content=f"하위 작업: {sub.title}\n질의: {sub.query}\n\n검색 스니펫:\n{snippet}"),
    ])

    secs = round(time.time() - t0, 2)
    tokens = _tokens(resp)
    result: WorkerResult = {
        "id": sub.id,
        "title": sub.title,
        "summary": resp.content if isinstance(resp.content, str) else str(resp.content),
        "sources": sources,
        "tokens": tokens,
        "seconds": secs,
        "failed": failed,
    }
    metric = log_metric("worker", id=sub.id, title=sub.title, tokens=tokens, seconds=secs, failed=failed)
    return {"worker_results": [result], "metrics": [metric]}


def aggregator_node(state: AgentState) -> dict:
    t0 = time.time()
    sections = []
    for r in sorted(state["worker_results"], key=lambda x: x["id"]):
        src_md = "\n".join(f"- {s}" for s in r["sources"]) or "- (없음)"
        sections.append(f"## {r['title']}\n\n{r['summary']}\n\n**참고 링크**\n{src_md}\n")

    body = "\n".join(sections)
    resp = llm.invoke([HumanMessage(content=(
        "다음 섹션들을 자연스럽게 연결하여 임원 보고용 한국어 마켓 리포트를 작성하세요. "
        "맨 앞에 한 문단의 핵심 요약(Executive Summary)을 두고, "
        "각 섹션 제목과 본문은 그대로 유지·정리하세요.\n\n"
        f"질문: {state['query']}\n\n섹션:\n{body}"
    ))])

    draft = (
        "# 전기차 배터리 시장 동향 리포트\n\n"
        f"_쿼리_: {state['query']}\n"
        f"_생성_: {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"{resp.content}\n"
    )
    metric = log_metric("aggregator", tokens=_tokens(resp), seconds=round(time.time() - t0, 2))
    return {"draft_report": draft, "metrics": [metric]}


def judge_node(state: AgentState) -> dict:
    t0 = time.time()
    score: JudgeScore = llm.with_structured_output(JudgeScore).invoke([
        SystemMessage(content=(
            "당신은 엄격한 LLM-as-a-Judge입니다. 주어진 시장 조사 리포트를 "
            "5점 만점으로 채점하고, 근거(rationale)와 개선점(issues)을 작성하세요. "
            "기준: completeness(주제 커버), accuracy(사실성), readability(가독성), "
            "actionability(의사결정 활용성)."
        )),
        HumanMessage(content=state["draft_report"]),
    ])
    scorecard = score.model_dump()
    SCORECARD_FILE.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
    metric = log_metric("judge", overall=scorecard["overall"], seconds=round(time.time() - t0, 2))
    return {"scorecard": scorecard, "metrics": [metric]}


def hitl_node(state: AgentState) -> dict:
    """interrupt_before로 이 노드 직전에 그래프가 멈춘다.
    재개 시 state['approved']에 따라 publish 동작이 갈린다."""
    log_metric("hitl_resume", approved=bool(state.get("approved", False)))
    return {}


def publish_node(state: AgentState) -> dict:
    if not state.get("approved"):
        log_metric("publish_skipped", reason="not_approved")
        return {}
    REPORT_FILE.write_text(state["draft_report"], encoding="utf-8")
    log_metric("publish", path=str(REPORT_FILE))
    return {}


# ──────────────────────────── Graph ────────────────────────────

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner_node)
    g.add_node("worker", worker_node)
    g.add_node("aggregator", aggregator_node)
    g.add_node("judge", judge_node)
    g.add_node("hitl", hitl_node)
    g.add_node("publish", publish_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", fan_out, ["worker"])
    g.add_edge("worker", "aggregator")
    g.add_edge("aggregator", "judge")
    g.add_edge("judge", "hitl")
    g.add_edge("hitl", "publish")
    g.add_edge("publish", END)

    return g.compile(checkpointer=MemorySaver(), interrupt_before=["hitl"])


# ──────────────────────────── CLI ────────────────────────────

def main():
    query = os.environ.get("LAB_QUERY", "전기차 배터리 시장 동향 조사해줘")
    graph = build_graph()
    cfg = {"configurable": {"thread_id": f"run-{int(time.time())}"}}
    log_metric("run_start", query=query, model=MODEL, thread=cfg["configurable"]["thread_id"])

    print(f"\n[입력] {query}")
    print("[1/2] Planner → Workers(병렬) → Aggregator → Judge 실행 중...\n")

    state = graph.invoke({"query": query, "approved": False}, cfg)

    print("=== Judge 채점 결과 ===")
    print(json.dumps(state["scorecard"], ensure_ascii=False, indent=2))
    print(f"→ 저장: {SCORECARD_FILE}\n")

    preview = state["draft_report"][:1500]
    print("--- 리포트 미리보기 (1500자) ---")
    print(preview + ("\n... (생략)\n" if len(state["draft_report"]) > 1500 else "\n"))

    answer = input("이 리포트를 발행하시겠습니까? [y/N]: ").strip().lower()
    approved = answer == "y"
    graph.update_state(cfg, {"approved": approved})
    graph.invoke(None, cfg)

    if approved:
        print(f"\n발행 완료 → {REPORT_FILE}")
    else:
        print("\n발행 취소됨. (report.md는 기록되지 않습니다)")
    print(f"메트릭 로그   → {METRICS_FILE}")
    print("대시보드      → streamlit run dashboard.py\n")


if __name__ == "__main__":
    main()

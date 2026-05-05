"""
Single-Agent 5-Stage Research Graph
- 한 LLM 인스턴스가 Plan → Search → Compress → Write → Verify 5단계를 모두 실행
- sub-agent 없이 노드만 분리
- Verify 실패 시 Search로 되돌아가는 조건부 엣지로 self-correction
"""

from __future__ import annotations

import json
import os
import sys as _sys
from pathlib import Path
from typing import TypedDict

# Windows 콘솔에서 한글이 깨지지 않도록 stdout 을 UTF-8 로 재구성
try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

load_dotenv()


# ---------- State ----------
class State(TypedDict):
    query: str
    subqs: list[str]
    evidence: list[Document]
    notes: dict[str, str]
    report: str
    verdict: str        # "pass" | "fail"
    issues: list[str]
    loops: int          # Search 재방문 횟수 (무한 루프 방지)


MAX_LOOPS = 2


# ---------- Single LLM Instance ----------
llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    temperature=0,
    max_tokens=4096,
    api_key=os.getenv("OPENAI_API_KEY"),
)

tavily = TavilySearchResults(
    max_results=5,
    api_key=os.getenv("TAVILY_API_KEY"),
)


def _ask(system: str, user: str) -> str:
    """단일 LLM 호출 헬퍼."""
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return resp.content if isinstance(resp.content, str) else str(resp.content)


def _ask_json(system: str, user: str) -> dict | list:
    raw = _ask(system + "\n\n반드시 JSON 만 출력. 설명·코드펜스 금지.", user)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


# ---------- 1) Plan ----------
def plan(state: State) -> dict:
    """원 질문을 3~5개의 sub-question 으로 분해."""
    sys = (
        "너는 리서치 플래너다. 사용자의 메인 쿼리를 검증 가능한 "
        "3~5개의 sub-question 으로 분해한다. 각 sub-question 은 독립적으로 "
        "웹 검색이 가능해야 한다."
    )
    user = f"메인 쿼리: {state['query']}\n\n출력 스키마: {{\"subqs\": [str, ...]}}"
    data = _ask_json(sys, user)
    return {
        "subqs": data["subqs"],
        "evidence": [],
        "notes": {},
        "loops": state.get("loops", 0),
    }


# ---------- 2) Search ----------
def search(state: State) -> dict:
    """각 sub-question 에 대해 Tavily 호출 → evidence 수집."""
    evidence: list[Document] = list(state.get("evidence", []))

    # 재방문 시 LLM 이 어떤 sub-q 를 우선 보강할지 결정
    targets = state["subqs"]
    if state.get("verdict") == "fail" and state.get("issues"):
        sys = "검증에서 부족하다고 지적된 sub-question 만 골라라."
        user = json.dumps({"subqs": targets, "issues": state["issues"]}, ensure_ascii=False)
        try:
            picked = _ask_json(sys + ' 출력: {"targets": [str, ...]}', user)
            targets = picked.get("targets") or targets
        except Exception:
            pass

    for q in targets:
        try:
            results = tavily.invoke({"query": q})
        except Exception as e:
            results = [{"url": "", "content": f"[search error] {e}"}]
        for r in results:
            evidence.append(
                Document(
                    page_content=r.get("content", ""),
                    metadata={"url": r.get("url", ""), "subq": q},
                )
            )

    return {
        "evidence": evidence,
        "loops": state.get("loops", 0) + (1 if state.get("verdict") == "fail" else 0),
    }


# ---------- 3) Compress ----------
def compress(state: State) -> dict:
    """긴 evidence 를 sub-question 별 핵심 노트로 요약."""
    by_subq: dict[str, list[str]] = {}
    for d in state["evidence"]:
        sq = d.metadata.get("subq", "_")
        by_subq.setdefault(sq, []).append(
            f"[{d.metadata.get('url','')}] {d.page_content}"
        )

    sys = (
        "너는 인용 보존형 요약기다. 주어진 sub-question 의 evidence 들을 "
        "사실 손실 없이 압축하되, 각 사실 뒤에 [URL] 형태로 출처를 남겨라."
    )
    notes: dict[str, str] = {}
    for sq, chunks in by_subq.items():
        joined = "\n---\n".join(chunks)[:8000]
        user = f"Sub-question: {sq}\n\nEvidence:\n{joined}\n\n핵심 사실을 bullet 로 5~10개."
        notes[sq] = _ask(sys, user)
    return {"notes": notes}


# ---------- 4) Write ----------
def write(state: State) -> dict:
    """sub-q 별 notes 를 통합해 일관된 보고서 작성."""
    sys = (
        "너는 리서치 라이터다. notes 만 근거로 사용해 일관된 한국어 보고서를 작성한다. "
        "모든 사실 문장 끝에 [URL] 인용을 붙인다. 추측·환각 금지."
    )
    user = (
        f"메인 쿼리: {state['query']}\n\n"
        f"Notes(JSON):\n{json.dumps(state['notes'], ensure_ascii=False, indent=2)}\n\n"
        "구성: 1) 요약  2) sub-question 별 답변  3) 결론"
    )
    return {"report": _ask(sys, user)}


# ---------- 5) Verify ----------
def verify(state: State) -> dict:
    """인용 누락·일관성·미해결 sub-q 검사 (관대한 기준)."""
    sys = (
        "너는 검증자다. 보고서를 다음 기준으로 평가한다.\n"
        "  (a) 인용: 보고서의 사실 진술 중 [URL] 인용이 붙은 비율이 70% 이상인가.\n"
        "  (b) 답변성: 각 sub-question 의 핵심 주제어가 보고서 본문에 등장하고 "
        "      관련 사실이 1개 이상 서술되어 있으면 '답변됨' 으로 간주.\n"
        "      완벽한 답변이 아니어도, 부분적으로라도 다뤄지면 통과.\n"
        "  (c) 일관성: notes 에 적힌 사실과 정면으로 모순되는 진술이 없는가.\n"
        "위 (a)(b)(c) 모두 만족하면 verdict='pass'. "
        "치명적 결함(전체 인용 누락, sub-q 절반 이상 미언급, 모순)이 있을 때만 'fail'.\n"
        "issues 에는 '어떤 sub-q 에 무엇이 더 필요한가' 를 구체적으로 1~3개만 적는다."
    )
    user = (
        f"Sub-questions: {state['subqs']}\n\n"
        f"Notes:\n{json.dumps(state['notes'], ensure_ascii=False)}\n\n"
        f"Report:\n{state['report']}\n\n"
        '출력 스키마: {"verdict": "pass"|"fail", "issues": [str, ...]}'
    )
    try:
        data = _ask_json(sys, user)
        verdict = data.get("verdict", "fail")
        issues = data.get("issues", [])
    except Exception:
        verdict, issues = "fail", ["verifier parse error"]
    return {"verdict": verdict, "issues": issues}


# ---------- Conditional Edge ----------
def route_after_verify(state: State) -> str:
    if state["verdict"] == "pass":
        return END
    if state.get("loops", 0) >= MAX_LOOPS:
        return END  # 루프 한도 도달 시 종료
    return "search"


# ---------- Graph ----------
def build_graph():
    g = StateGraph(State)
    g.add_node("plan", plan)
    g.add_node("search", search)
    g.add_node("compress", compress)
    g.add_node("write", write)
    g.add_node("verify", verify)

    g.add_edge(START, "plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "compress")
    g.add_edge("compress", "write")
    g.add_edge("write", "verify")
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"search": "search", END: END},
    )
    return g.compile()


# ---------- Entrypoint ----------
if __name__ == "__main__":
    app = build_graph()
    init: State = {
        "query": "2025년 한국 전기차 보조금 정책의 주요 변경점은?",
        "subqs": [],
        "evidence": [],
        "notes": {},
        "report": "",
        "verdict": "",
        "issues": [],
        "loops": 0,
    }
    final = app.invoke(init)

    out = Path(__file__).with_name("report.md")
    out.write_text(
        f"# {final['query']}\n\n"
        f"- verdict: **{final['verdict']}**\n"
        f"- loops: {final['loops']}\n"
        f"- sub-questions: {final['subqs']}\n"
        f"- issues: {final['issues']}\n\n---\n\n"
        f"{final['report']}\n",
        encoding="utf-8",
    )

    print(f"verdict = {final['verdict']}  loops = {final['loops']}")
    print(f"issues  = {final['issues']}")
    print(f"report  -> {out}")

"""
Email Classifier MCP Client (LangGraph Orchestrated)
====================================================

LangGraph 로 다음 흐름을 오케스트레이션한다.

       ┌────────┐    ┌────────────┐    ┌───────────┐
START ─┤ loader ├──→ │ classifier ├──→ │ evaluator ├─→ END
       │  [1/4] │    │ + labeler  │    │   [4/4]   │
       └────────┘    │  [2/4 3/4] │    └───────────┘
                     └────────────┘

각 노드는 fastmcp.Client (stdio) 로 email_mcp_server.py 의 도구를 호출한다.

  - loader      : load_emails(csv_path)
  - classifier+labeler : save_labeled_csv(input_path, output_path)
  - evaluator   : evaluate_accuracy(labeled_csv_path)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List, TypedDict

from fastmcp import Client
from langgraph.graph import END, START, StateGraph

# Windows 콘솔 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# --------------------------------------------------------------------------- #
# 경로 상수
# --------------------------------------------------------------------------- #
INPUT_CSV     = r"C:\claude\mcp\day3\emails.csv"
OUTPUT_CSV    = r"C:\claude\mcp\day3\emails_labeled.csv"
SERVER_SCRIPT = r"C:\claude\mcp\day3\email_mcp_server.py"


# --------------------------------------------------------------------------- #
# 응답 언래핑 헬퍼
# --------------------------------------------------------------------------- #
def unwrap(result: Any) -> Any:
    """fastmcp Client 의 도구 호출 결과에서 실제 payload 추출.

    우선순위:
      1) result.data  (구조화 출력)
      2) result.content[*].text 의 JSON 파싱 결과
      3) 원본 result
    """
    data = getattr(result, "data", None)
    if data is not None:
        return data

    content = getattr(result, "content", None)
    if content:
        # 모든 text 블록을 이어붙인 뒤 JSON 시도
        text_parts = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                text_parts.append(text)
        joined = "".join(text_parts).strip()
        if joined:
            try:
                return json.loads(joined)
            except (json.JSONDecodeError, ValueError):
                return joined

    return result


# --------------------------------------------------------------------------- #
# LangGraph State
# --------------------------------------------------------------------------- #
class GraphState(TypedDict, total=False):
    input_csv: str
    output_csv: str
    emails: List[Dict[str, Any]]
    columns: List[str]
    saved_path: str
    rows_saved: int
    evaluation: Dict[str, Any]


# --------------------------------------------------------------------------- #
# 노드 빌더 (MCP Client 를 클로저로 캡처)
# --------------------------------------------------------------------------- #
def build_graph(client: Client):

    async def loader_node(state: GraphState) -> GraphState:
        print("\n========== [1/4] Loader ==========")
        result = await client.call_tool(
            "load_emails", {"csv_path": state["input_csv"]}
        )
        emails = unwrap(result) or []
        if not isinstance(emails, list):
            emails = []
        columns = list(emails[0].keys()) if emails else []
        print(f"  - 로드된 이메일 건수 : {len(emails)}")
        print(f"  - 컬럼명             : {columns}")
        return {"emails": emails, "columns": columns}

    async def classifier_labeler_node(state: GraphState) -> GraphState:
        print("\n========== [2/4] Classifier + [3/4] Labeler ==========")
        print(f"  - 입력 CSV : {state['input_csv']}")
        print(f"  - 출력 CSV : {state['output_csv']}")
        print(f"  - 분류 진행 (server stderr 에서 진행 상황 표시)...")
        result = await client.call_tool(
            "save_labeled_csv",
            {
                "input_path": state["input_csv"],
                "output_path": state["output_csv"],
            },
        )
        payload = unwrap(result) or {}
        saved = payload.get("saved", state["output_csv"])
        rows = payload.get("rows", 0)
        print(f"  - 저장 경로 : {saved}")
        print(f"  - 저장 건수 : {rows}")
        return {"saved_path": saved, "rows_saved": rows}

    async def evaluator_node(state: GraphState) -> GraphState:
        print("\n========== [4/4] Evaluator ==========")
        result = await client.call_tool(
            "evaluate_accuracy", {"labeled_csv_path": state["saved_path"]}
        )
        ev: Dict[str, Any] = unwrap(result) or {}

        total = ev.get("total", 0)
        correct = ev.get("correct", 0)
        accuracy = ev.get("accuracy", 0.0)
        per_class: Dict[str, Dict[str, int]] = ev.get("per_class", {})
        mistakes: List[Dict[str, Any]] = ev.get("mistakes", [])

        print(f"  - Total     : {total}")
        print(f"  - Correct   : {correct}")
        print(f"  - Accuracy  : {accuracy:.2%}")

        print("\n  [클래스별 지표]")
        # URGENT / GENERAL / SPAM / INTERNAL 순으로 정렬, 그 외 라벨은 뒤로
        canonical = ["URGENT", "GENERAL", "SPAM", "INTERNAL"]
        ordered = [c for c in canonical if c in per_class] + \
                  [c for c in per_class.keys() if c not in canonical]
        for cls in ordered:
            stats = per_class[cls]
            tp = stats.get("tp", 0)
            fp = stats.get("fp", 0)
            fn = stats.get("fn", 0)
            support = stats.get("support", 0)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            print(
                f"  {cls:<8} support={support:>2d}  tp={tp:>2d}  "
                f"fp={fp:>2d}  fn={fn:>2d}  "
                f"precision={precision:.2f}  recall={recall:.2f}"
            )

        print(f"\n  [오분류 리스트] (총 {len(mistakes)}건)")
        if not mistakes:
            print("    (없음)")
        else:
            for m in mistakes:
                print(
                    f"    id={m.get('id', ''):>3} "
                    f"true={m.get('true', ''):<8} "
                    f"pred={m.get('pred', ''):<8} "
                    f"subj={m.get('subject', '')}"
                )

        return {"evaluation": ev}

    g = StateGraph(GraphState)
    g.add_node("loader", loader_node)
    g.add_node("classifier_labeler", classifier_labeler_node)
    g.add_node("evaluator", evaluator_node)
    g.add_edge(START, "loader")
    g.add_edge("loader", "classifier_labeler")
    g.add_edge("classifier_labeler", "evaluator")
    g.add_edge("evaluator", END)
    return g.compile()


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
async def run() -> None:
    print("==================================================")
    print(" Email Classifier Agent (MCP × LangGraph × OpenAI)")
    print("==================================================")
    print(f"  - MCP Server : {SERVER_SCRIPT}")
    print(f"  - Input  CSV : {INPUT_CSV}")
    print(f"  - Output CSV : {OUTPUT_CSV}")

    # fastmcp.Client 는 .py 스크립트 경로를 받으면 stdio 로 실행한다.
    async with Client(SERVER_SCRIPT) as client:
        # 노출된 도구 확인
        tools = await client.list_tools()
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        print(f"  - MCP Tools  : {tool_names}\n")

        graph = build_graph(client)
        initial: GraphState = {
            "input_csv": INPUT_CSV,
            "output_csv": OUTPUT_CSV,
        }
        await graph.ainvoke(initial)

    print("\n==================================================")
    print(" Done.")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run())

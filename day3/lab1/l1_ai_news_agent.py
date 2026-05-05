from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from tavily import TavilyClient
from datetime import datetime
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


class AgentState(TypedDict):
    user_request: str
    plan: Dict[str, Any]
    raw_news: List[Dict[str, Any]]
    filtered_news: List[Dict[str, Any]]
    summarized_news: List[Dict[str, Any]]
    final_report: str
    logs: List[str]


llm = ChatOpenAI(model="gpt-4o", temperature=0.3)


def planner_node(state: AgentState) -> AgentState:
    system = SystemMessage(content=(
        "당신은 AI 업계 뉴스 검색 전략을 수립하는 Planner 에이전트입니다. "
        "사용자의 요청을 분석하여 검색 전략을 수립하세요.\n"
        "다음 JSON 형식으로 출력하세요:\n"
        "{\n"
        '  "keywords": ["키워드1", "키워드2", "키워드3", ...],\n'
        '  "strategy": {\n'
        '    "recency": "최신성 기준 설명",\n'
        '    "reliability": "신뢰성 기준 설명",\n'
        '    "relevance": "관련성 기준 설명"\n'
        "  }\n"
        "}\n"
        "키워드는 3~5개 생성하세요."
    ))
    human = HumanMessage(content=f"사용자 요청: {state['user_request']}")
    response = llm.invoke([system, human])

    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    plan = json.loads(content)

    log = "[PLANNER]\n"
    log += f"검색 키워드: {', '.join(plan['keywords'])}\n"
    log += f"- 최신성: {plan['strategy']['recency']}\n"
    log += f"- 신뢰성: {plan['strategy']['reliability']}\n"
    log += f"- 관련성: {plan['strategy']['relevance']}\n"

    return {**state, "plan": plan, "logs": state.get("logs", []) + [log]}


def tool_node(state: AgentState) -> AgentState:
    search_results: List[Dict[str, Any]] = []
    for keyword in state["plan"]["keywords"]:
        resp = tavily.search(
            query=keyword,
            topic="news",
            search_depth="advanced",
            days=2,
            max_results=5,
            include_answer=False,
        )
        for r in resp.get("results", []):
            search_results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": r.get("url", "").split("/")[2] if r.get("url") else "",
                "date": (r.get("published_date") or "")[:10],
                "content": r.get("content", ""),
            })

    seen = set()
    unique_results = []
    for r in search_results:
        if r["url"] in seen or not r["url"]:
            continue
        seen.add(r["url"])
        unique_results.append(r)

    system = SystemMessage(content=(
        "당신은 웹 검색 결과를 정제하는 Tool 에이전트입니다. "
        "Tavily에서 받아온 raw 검색 결과를 표준 뉴스 후보 형식으로 가공하세요. "
        "AI 산업과 무관하거나 단순 광고/홍보성 글은 제외하고, 7~10개를 최종 선별하세요.\n"
        "각 뉴스는 다음 JSON 배열 형식으로 출력하세요:\n"
        "[\n"
        '  {"title": "...", "source": "...", "date": "YYYY-MM-DD", "summary": "1~2문장 요약"},\n'
        "  ...\n"
        "]\n"
        "summary는 원문 content를 한국어로 1~2문장 요약하세요. date가 비어있으면 'N/A'로 두세요."
    ))
    human = HumanMessage(content=(
        f"오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"검색 키워드: {state['plan']['keywords']}\n"
        f"Tavily 검색 결과 ({len(unique_results)}건):\n"
        f"{json.dumps(unique_results, ensure_ascii=False, indent=2)}"
    ))
    response = llm.invoke([system, human])

    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    raw_news = json.loads(content)

    log = "[TOOL]\n"
    log += f"Tavily 원시 결과 {len(unique_results)}건 → 정제 후 {len(raw_news)}개 수집\n"
    for i, n in enumerate(raw_news, 1):
        log += f"{i}. {n['title']} ({n['source']}, {n['date']})\n"
        log += f"   요약: {n['summary']}\n"

    return {**state, "raw_news": raw_news, "logs": state.get("logs", []) + [log]}


def filter_node(state: AgentState) -> AgentState:
    system = SystemMessage(content=(
        "당신은 뉴스 필터링 전문가 Filter 에이전트입니다. "
        "주어진 뉴스 후보 중 중복을 제거하고, 언론사·내용 기준으로 신뢰도를 평가하여 "
        "가장 중요한 5개를 선정하세요.\n"
        "다음 JSON 형식으로 출력하세요:\n"
        "{\n"
        '  "selected": [\n'
        '    {"title": "...", "source": "...", "date": "...", "summary": "...", "reason": "선정 이유"}\n'
        "  ]\n"
        "}\n"
        "selected는 정확히 5개여야 합니다."
    ))
    human = HumanMessage(content=f"뉴스 후보:\n{json.dumps(state['raw_news'], ensure_ascii=False, indent=2)}")
    response = llm.invoke([system, human])

    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    result = json.loads(content)
    filtered = result["selected"]

    log = "[FILTER]\n"
    log += f"5개 뉴스 선정 완료\n"
    for i, n in enumerate(filtered, 1):
        log += f"{i}. {n['title']}\n"
        log += f"   선정 이유: {n['reason']}\n"

    return {**state, "filtered_news": filtered, "logs": state.get("logs", []) + [log]}


def summarize_node(state: AgentState) -> AgentState:
    system = SystemMessage(content=(
        "당신은 뉴스 요약 전문가 Summarize 에이전트입니다. "
        "주어진 5개 뉴스 각각을 3줄 이내로 핵심 요약하고, "
        "기술/산업 관점에서의 의미를 포함하세요.\n"
        "다음 JSON 형식으로 출력하세요:\n"
        "[\n"
        '  {"title": "...", "source": "...", "date": "...", "summary": "3줄 이내 핵심 요약", "significance": "기술/산업 관점 의미"}\n'
        "]"
    ))
    human = HumanMessage(content=f"선정 뉴스:\n{json.dumps(state['filtered_news'], ensure_ascii=False, indent=2)}")
    response = llm.invoke([system, human])

    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    summarized = json.loads(content)

    log = "[SUMMARIZE]\n"
    for i, n in enumerate(summarized, 1):
        log += f"{i}. {n['title']}\n"
        log += f"   요약: {n['summary']}\n"
        log += f"   의미: {n['significance']}\n"

    return {**state, "summarized_news": summarized, "logs": state.get("logs", []) + [log]}


def output_node(state: AgentState) -> AgentState:
    report = "# 🧠 AI 업계 오늘자 뉴스 Top 5\n\n"
    for i, n in enumerate(state["summarized_news"], 1):
        report += f"## {i}. {n['title']}\n"
        report += f"- 출처: {n['source']}\n"
        report += f"- 날짜: {n['date']}\n"
        report += f"- 요약: {n['summary']}\n"
        report += f"- 의미: {n['significance']}\n\n"

    log = "[OUTPUT]\n" + report
    return {**state, "final_report": report, "logs": state.get("logs", []) + [log]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("filter", filter_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("output", output_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "filter")
    graph.add_edge("filter", "summarize")
    graph.add_edge("summarize", "output")
    graph.add_edge("output", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    initial_state: AgentState = {
        "user_request": "AI 업계 오늘자 뉴스 Top 5를 요약해줘.",
        "plan": {},
        "raw_news": [],
        "filtered_news": [],
        "summarized_news": [],
        "final_report": "",
        "logs": [],
    }
    result = app.invoke(initial_state)

    for log in result["logs"]:
        print(log)
        print("-" * 60)

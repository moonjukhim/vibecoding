"""
LangGraph 기반 고객 문의 분석 에이전트

그래프 구조:
  [START] → analyze_content → classify_category → assess_urgency → extract_keywords → [END]

각 노드가 문의 글을 분석하여 state에 결과를 누적한다.
"""

import json
import os
from typing import TypedDict, Literal

from flask import Flask, request, jsonify
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

# ---------------------------------------------------------------------------
# State 정의
# ---------------------------------------------------------------------------

class InquiryState(TypedDict):
    title: str
    content: str
    # 에이전트가 채워넣는 필드들
    ai_category: str
    sentiment: str
    urgency: str
    keywords: list[str]
    summary: str


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

llm = ChatAnthropic(
    model="claude-sonnet-4-20250514",
    temperature=0,
    max_tokens=1024,
)

CATEGORIES = ["제품문의", "배송문의", "교환/반품", "결제/환불", "기술지원", "불만/컴플레인", "칭찬/감사", "일반문의"]

# ---------------------------------------------------------------------------
# 노드 함수들
# ---------------------------------------------------------------------------

def analyze_content(state: InquiryState) -> dict:
    """글의 전체적인 감정과 요약을 분석한다."""
    response = llm.invoke([
        SystemMessage(content=(
            "당신은 고객 문의를 분석하는 전문가입니다. "
            "주어진 문의 글의 감정(긍정/부정/중립)과 핵심 요약(1~2문장)을 JSON으로 반환하세요.\n"
            '반드시 {"sentiment": "긍정|부정|중립", "summary": "요약 내용"} 형식으로만 답하세요. '
            "다른 텍스트는 포함하지 마세요."
        )),
        HumanMessage(content=f"제목: {state['title']}\n내용: {state['content']}"),
    ])
    data = json.loads(response.content)
    return {"sentiment": data["sentiment"], "summary": data["summary"]}


def classify_category(state: InquiryState) -> dict:
    """문의를 적절한 카테고리로 분류한다."""
    response = llm.invoke([
        SystemMessage(content=(
            "당신은 고객 문의 분류 전문가입니다. "
            f"다음 카테고리 중 가장 적합한 것 하나를 골라 JSON으로 반환하세요: {CATEGORIES}\n"
            '반드시 {"category": "카테고리명"} 형식으로만 답하세요. '
            "다른 텍스트는 포함하지 마세요."
        )),
        HumanMessage(content=f"제목: {state['title']}\n내용: {state['content']}"),
    ])
    data = json.loads(response.content)
    return {"ai_category": data["category"]}


def assess_urgency(state: InquiryState) -> dict:
    """문의의 긴급도를 평가한다."""
    response = llm.invoke([
        SystemMessage(content=(
            "당신은 고객 문의의 긴급도를 평가하는 전문가입니다. "
            "문의 내용과 감정을 고려하여 긴급도를 판단하세요.\n"
            "- 높음: 즉시 대응 필요 (불만, 결제 오류, 긴급 배송 등)\n"
            "- 보통: 일반적인 시간 내 처리 가능\n"
            "- 낮음: 단순 문의, 감사 인사 등\n"
            '반드시 {"urgency": "높음|보통|낮음"} 형식으로만 답하세요. '
            "다른 텍스트는 포함하지 마세요."
        )),
        HumanMessage(content=(
            f"제목: {state['title']}\n내용: {state['content']}\n"
            f"감정: {state.get('sentiment', '알 수 없음')}"
        )),
    ])
    data = json.loads(response.content)
    return {"urgency": data["urgency"]}


def extract_keywords(state: InquiryState) -> dict:
    """핵심 키워드를 추출한다."""
    response = llm.invoke([
        SystemMessage(content=(
            "당신은 텍스트에서 핵심 키워드를 추출하는 전문가입니다. "
            "주어진 문의 글에서 중요한 키워드를 3~5개 추출하세요.\n"
            '반드시 {"keywords": ["키워드1", "키워드2", ...]} 형식으로만 답하세요. '
            "다른 텍스트는 포함하지 마세요."
        )),
        HumanMessage(content=f"제목: {state['title']}\n내용: {state['content']}"),
    ])
    data = json.loads(response.content)
    return {"keywords": data["keywords"]}


# ---------------------------------------------------------------------------
# 그래프 빌드
# ---------------------------------------------------------------------------

graph_builder = StateGraph(InquiryState)

graph_builder.add_node("analyze_content", analyze_content)
graph_builder.add_node("classify_category", classify_category)
graph_builder.add_node("assess_urgency", assess_urgency)
graph_builder.add_node("extract_keywords", extract_keywords)

graph_builder.add_edge(START, "analyze_content")
graph_builder.add_edge("analyze_content", "classify_category")
graph_builder.add_edge("classify_category", "assess_urgency")
graph_builder.add_edge("assess_urgency", "extract_keywords")
graph_builder.add_edge("extract_keywords", END)

graph = graph_builder.compile()


# ---------------------------------------------------------------------------
# Flask API 서버
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/analyze", methods=["POST"])
def analyze():
    body = request.get_json()
    title = body.get("title", "")
    content = body.get("content", "")

    if not title and not content:
        return jsonify({"error": "title 또는 content가 필요합니다."}), 400

    initial_state: InquiryState = {
        "title": title,
        "content": content,
        "ai_category": "",
        "sentiment": "",
        "urgency": "",
        "keywords": [],
        "summary": "",
    }

    result = graph.invoke(initial_state)

    return jsonify({
        "ai_category": result["ai_category"],
        "sentiment": result["sentiment"],
        "urgency": result["urgency"],
        "keywords": result["keywords"],
        "summary": result["summary"],
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

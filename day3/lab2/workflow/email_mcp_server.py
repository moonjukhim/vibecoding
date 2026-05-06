"""
Email Classifier MCP Server
===========================

FastMCP 기반의 이메일 분류 서버. 다음 4개 도구를 노출한다.

  1) load_emails(csv_path)                 → CSV 로드
  2) classify_email(from, subject, body)   → OpenAI(gpt-4o-mini) 4-class 분류
  3) save_labeled_csv(input, output)       → predicted_label 컬럼 추가 후 저장
  4) evaluate_accuracy(labeled_csv_path)   → true_label vs predicted_label 평가

환경변수 OPENAI_API_KEY 가 필요하다 (.env 사용).
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastmcp import FastMCP
from openai import OpenAI

# Windows 콘솔(cp949)에서 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

load_dotenv()

LABELS = ("URGENT", "GENERAL", "SPAM", "INTERNAL")
DEFAULT_LABEL = "GENERAL"
OPENAI_MODEL = "gpt-4o-mini"

mcp = FastMCP("Email-Classifier-MCP")
_openai_client: OpenAI | None = None


def _client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


SYSTEM_PROMPT = """너는 기업 이메일을 4개 라벨로 분류하는 분류기다.
출력은 반드시 라벨 한 단어만 (URGENT / GENERAL / SPAM / INTERNAL) 출력한다.

[라벨 정의]
- URGENT  : 즉시 대응이 필요한 메일. 장애/SEV1/P1, 결제 실패, 보안 사고,
            고객 컴플레인(긴급/환불/이중결제) 등.
- GENERAL : 일반 외부 업무 메일. 회의 요청, 견적/제안, 협업·일정 조율,
            인터뷰, 비즈니스 문의 등.
- SPAM    : 광고·피싱·자동 발송 마케팅. 프로모션 쿠폰, 당첨/상금,
            의심 링크/단축 URL, 스미싱 문구 등.
- INTERNAL: 사내 공지·HR·정책. 총무, 복지, 사내 규정, 교육, 전사 알림 등.
            보통 회사 도메인(@acme.com 등)에서 발신.

[Few-shot 예시]
예시 1)
From: alerts@datadog.com
Subject: [P1] DB latency spike on prod-mysql-01
Body: Production p95 > 2.4s for the last 12 minutes. PagerDuty already escalated.
Label: URGENT

예시 2)
From: pm@partner.co
Subject: 다음 주 화요일 협업 미팅 일정 조율 부탁드립니다
Body: 2종 견적 비교 후 회신 드리겠습니다. 가능하신 시간대 알려주세요.
Label: GENERAL

예시 3)
From: promo@deal-shop.top
Subject: 🎉 축하합니다! 100만원 상품권 당첨!!! 지금 클릭
Body: 아래 링크에서 본인 인증만 하면 즉시 지급됩니다 http://bit.ly/xxxx
Label: SPAM

예시 4)
From: hr@acme.com
Subject: [사내공지] 2026년 상반기 복지포인트 사용 안내
Body: 사내 임직원 대상 복지포인트 사용 기한 및 사용처 안내드립니다.
Label: INTERNAL
"""


def _extract_label(text: str) -> str:
    if not text:
        return DEFAULT_LABEL
    upper = text.upper()
    # 정확 매칭 우선
    for label in LABELS:
        if re.search(rf"\b{label}\b", upper):
            return label
    return DEFAULT_LABEL


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

@mcp.tool()
def load_emails(csv_path: str) -> List[Dict[str, Any]]:
    """CSV 파일을 읽어 row dict 리스트로 반환한다.

    Args:
        csv_path: 읽을 CSV 파일의 절대경로
    Returns:
        각 행을 dict 로 변환한 리스트
    """
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


@mcp.tool()
def classify_email(from_addr: str, subject: str, body: str) -> str:
    """OpenAI gpt-4o-mini 로 4-class 분류 수행.

    Args:
        from_addr: 발신자 이메일
        subject  : 제목
        body     : 본문
    Returns:
        URGENT / GENERAL / SPAM / INTERNAL 중 하나
    """
    user_msg = (
        f"From: {from_addr}\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n\n"
        "위 이메일의 라벨 한 단어만 답하라."
    )
    resp = _client().chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _extract_label(raw)


@mcp.tool()
def save_labeled_csv(input_path: str, output_path: str) -> Dict[str, Any]:
    """입력 CSV 의 각 행을 분류해서 predicted_label 컬럼을 추가한 뒤 저장한다.

    Args:
        input_path : 원본 CSV 경로
        output_path: 라벨이 추가되어 저장될 CSV 경로
    Returns:
        {"saved": output_path, "rows": N}
    """
    with open(input_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(row) for row in reader]

    if not rows:
        # 빈 파일이라도 헤더만 작성
        fieldnames = ["id", "from", "subject", "body", "received_at",
                      "true_label", "predicted_label"]
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        return {"saved": output_path, "rows": 0}

    base_fields = list(rows[0].keys())
    if "predicted_label" not in base_fields:
        base_fields.append("predicted_label")

    for i, row in enumerate(rows, start=1):
        label = classify_email(
            from_addr=row.get("from", ""),
            subject=row.get("subject", ""),
            body=row.get("body", ""),
        )
        row["predicted_label"] = label
        # 진행 상황은 stderr 로 (stdio 트랜스포트 stdout 오염 방지)
        print(f"  [server] {i:3d}/{len(rows)}  pred={label:<8}  "
              f"subj={row.get('subject', '')[:40]}", file=sys.stderr, flush=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=base_fields)
        writer.writeheader()
        writer.writerows(rows)

    return {"saved": output_path, "rows": len(rows)}


@mcp.tool()
def evaluate_accuracy(labeled_csv_path: str) -> Dict[str, Any]:
    """labeled CSV 의 true_label vs predicted_label 을 비교하여 평가지표 반환.

    Args:
        labeled_csv_path: predicted_label 이 포함된 CSV 경로
    Returns:
        total / correct / accuracy / per_class / mistakes
    """
    with open(labeled_csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(row) for row in reader]

    total = 0
    correct = 0
    per_class: Dict[str, Dict[str, int]] = {
        lbl: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for lbl in LABELS
    }
    # 정의되지 않은 라벨이 등장해도 누락되지 않도록 동적 보강
    def _slot(label: str) -> Dict[str, int]:
        if label not in per_class:
            per_class[label] = {"tp": 0, "fp": 0, "fn": 0, "support": 0}
        return per_class[label]

    mistakes: List[Dict[str, Any]] = []
    for row in rows:
        true_lbl = (row.get("true_label") or "").strip()
        pred_lbl = (row.get("predicted_label") or "").strip()
        if not true_lbl:
            continue
        total += 1
        _slot(true_lbl)["support"] += 1
        if pred_lbl == true_lbl:
            correct += 1
            _slot(true_lbl)["tp"] += 1
        else:
            _slot(pred_lbl)["fp"] += 1
            _slot(true_lbl)["fn"] += 1
            subj = (row.get("subject") or "")[:60]
            mistakes.append({
                "id": row.get("id", ""),
                "subject": subj,
                "true": true_lbl,
                "pred": pred_lbl,
            })

    accuracy = (correct / total) if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "per_class": per_class,
        "mistakes": mistakes,
    }


if __name__ == "__main__":
    mcp.run()

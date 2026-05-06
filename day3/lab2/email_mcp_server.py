from fastmcp import FastMCP
from typing import Annotated, List, Dict, Any
from pydantic import Field
from openai import OpenAI
from dotenv import load_dotenv
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

mcp = FastMCP(name="Email-Classifier-MCP")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LABELS = ["URGENT", "GENERAL", "SPAM", "INTERNAL"]

FEW_SHOT_PROMPT = """당신은 이메일을 4개 카테고리로 분류하는 전문가입니다.

[라벨 정의]
- URGENT: 즉시 대응 필요 (장애·고객 컴플레인, P1/SEV1, 결제/보안 사고)
- GENERAL: 일반 업무 메일·문의·요청 (회의, 견적, 협업, 일정 조율)
- SPAM: 광고·피싱·자동 발송 (마케팅, 프로모션, 의심 링크)
- INTERNAL: 사내 공지·HR·인사·정책 (총무, 복지, 사내 규정, 교육)

[Few-shot 예시]
EMAIL:
from: alerts@datadog.com
subject: [P1] DB latency spike on prod-mysql-01
body: Production p95 > 2.4s for the last 12 minutes. PagerDuty already escalated.
LABEL: URGENT

EMAIL:
from: pm.lee@acme.com
subject: Q3 로드맵 리뷰 미팅 일정 조율
body: 다음 주 화/수 중 1시간 가능하신 시간 알려주세요. 어젠다는 첨부 참조.
LABEL: GENERAL

EMAIL:
from: deals@shoppingmall.com
subject: 🎁 오늘만! 전 상품 80% 할인 쿠폰 도착
body: 클릭 한 번으로 즉시 사용 가능한 쿠폰을 받아가세요. 수신거부는 하단 링크.
LABEL: SPAM

EMAIL:
from: hr@acme.com
subject: [공지] 2026년 하반기 건강검진 안내    
body: 전 임직원 대상 건강검진 일정과 신청 방법을 안내드립니다. 마감 5/20.
LABEL: INTERNAL

이제 다음 이메일을 분류하세요. 반드시 URGENT, GENERAL, SPAM, INTERNAL 중 하나의 단어만 출력하세요.
"""


@mcp.tool(
    name="load_emails",
    description="Load emails from CSV file. Returns list of email dicts with id/from/subject/body/received_at.",
)
def load_emails(
    csv_path: Annotated[str, Field(description="Absolute path to the emails CSV file.")]
) -> List[Dict[str, Any]]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


@mcp.tool(
    name="classify_email",
    description="Classify a single email into one of: URGENT, GENERAL, SPAM, INTERNAL using few-shot prompting.",
)
def classify_email(
    from_addr: Annotated[str, Field(description="Sender email address.")],
    subject: Annotated[str, Field(description="Email subject line.")],
    body: Annotated[str, Field(description="Email body text.")],
) -> str:
    user_msg = f"EMAIL:\nfrom: {from_addr}\nsubject: {subject}\nbody: {body}\nLABEL:"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": FEW_SHOT_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=8,
    )
    label = resp.choices[0].message.content.strip().upper()
    for valid in LABELS:
        if valid in label:
            return valid
    return "GENERAL"


@mcp.tool(
    name="save_labeled_csv",
    description="Load emails, classify each, append predicted_label column, and save to output path. Returns row count.",
)
def save_labeled_csv(
    input_path: Annotated[str, Field(description="Source emails CSV path.")],
    output_path: Annotated[str, Field(description="Destination CSV path with predicted_label column.")],
) -> Dict[str, Any]:
    rows = load_emails(input_path)
    for row in rows:
        row["predicted_label"] = classify_email(
            from_addr=row.get("from", ""),
            subject=row.get("subject", ""),
            body=row.get("body", ""),
        )

    fieldnames = list(rows[0].keys()) if rows else []
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {"saved": output_path, "rows": len(rows)}


@mcp.tool(
    name="evaluate_accuracy",
    description="Evaluate predicted_label vs true_label in a labeled CSV. Returns accuracy and per-class confusion stats.",
)
def evaluate_accuracy(
    labeled_csv_path: Annotated[str, Field(description="CSV with both true_label and predicted_label columns.")]
) -> Dict[str, Any]:
    rows = load_emails(labeled_csv_path)
    total = len(rows)
    correct = 0
    per_class: Dict[str, Dict[str, int]] = {l: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for l in LABELS}
    mistakes: List[Dict[str, str]] = []

    for row in rows:
        true_l = row.get("true_label", "").strip().upper()
        pred_l = row.get("predicted_label", "").strip().upper()
        if true_l in per_class:
            per_class[true_l]["support"] += 1
        if true_l == pred_l:
            correct += 1
            if true_l in per_class:
                per_class[true_l]["tp"] += 1
        else:
            if pred_l in per_class:
                per_class[pred_l]["fp"] += 1
            if true_l in per_class:
                per_class[true_l]["fn"] += 1
            mistakes.append({
                "id": row.get("id", ""),
                "subject": row.get("subject", "")[:60],
                "true": true_l,
                "pred": pred_l,
            })

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "per_class": per_class,
        "mistakes": mistakes,
    }


if __name__ == "__main__":
    mcp.run()

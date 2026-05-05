"""
MCP Client Agent: 이메일 분류 에이전트
- stdio 로 mcp_server.py 를 띄워 도구를 호출
- 분류 자체는 OpenAI 모델로 수행 (LLM 로직)
- I/O (CSV 읽기 / Postgres 쓰기) 는 모두 MCP 서버 도구를 통해서만

흐름:
    [server.read_emails_csv] -> for each row -> [OpenAI 분류]
        -> [server.insert_classified_email]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Windows 콘솔 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()


CATEGORIES = ["URGENT", "GENERAL", "INTERNAL", "SPAM"]

CLASSIFY_SYSTEM = f"""너는 이메일 분류기다. 이메일을 다음 네 카테고리 중 하나로 분류한다.
- URGENT   : 즉시 대응이 필요한 장애/보안/결제/SLA 위반 등
- GENERAL  : 외부 고객/파트너의 일반 문의·요청
- INTERNAL : 내부 직원/팀의 일상적 업무 메일
- SPAM     : 광고/피싱/무관한 마케팅

반드시 JSON 만 출력한다. 설명·코드펜스 금지.
출력 스키마: {{"category": "{'|'.join(CATEGORIES)}", "confidence": 0..1, "reason": "한 문장"}}
"""

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def classify_email(openai: OpenAI, email: dict) -> dict:
    """OpenAI 한 번 호출로 카테고리 + 신뢰도 + 근거를 받는다."""
    user = (
        f"From: {email.get('from','')}\n"
        f"Subject: {email.get('subject','')}\n"
        f"Received: {email.get('received_at','')}\n"
        f"Body:\n{email.get('body','')}"
    )
    resp = openai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user",   "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(resp.choices[0].message.content)
    cat = data.get("category", "GENERAL")
    if cat not in CATEGORIES:
        cat = "GENERAL"
    return {
        "category":   cat,
        "confidence": float(data.get("confidence", 0.0)),
        "reason":     str(data.get("reason", ""))[:500],
    }


async def run(csv_path: str, limit: int | None = None) -> None:
    openai = OpenAI()  # OPENAI_API_KEY env 사용

    # 같은 파이썬 인터프리터로 서버 스크립트 실행
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("mcp_server.py"))],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"[mcp] tools = {[t.name for t in tools.tools]}")

            # 1) 테이블 준비
            await session.call_tool("init_email_table", {})
            print("[db] classified_emails table ready")

            # 2) CSV 를 서버 도구로 읽기
            res = await session.call_tool(
                "read_emails_csv", {"file_path": csv_path}
            )
            emails = json.loads(res.content[0].text)
            if limit is not None:
                emails = emails[:limit]
            print(f"[csv] loaded {len(emails)} emails from {csv_path}")

            # 3) 분류 + DB 적재
            ok, fail = 0, 0
            for e in emails:
                eid = str(e.get("id", "")).strip()
                if not eid:
                    continue
                try:
                    cls = classify_email(openai, e)
                    await session.call_tool("insert_classified_email", {
                        "email_id":    eid,
                        "sender":      e.get("from", ""),
                        "subject":     e.get("subject", ""),
                        "body":        e.get("body", ""),
                        "received_at": e.get("received_at", ""),
                        "true_label":  e.get("true_label", ""),
                        "category":    cls["category"],
                        "confidence":  cls["confidence"],
                        "reason":      cls["reason"],
                    })
                    ok += 1
                    mark = "✓" if cls["category"] == e.get("true_label") else " "
                    print(
                        f"  [{mark}] id={eid:>3}  "
                        f"pred={cls['category']:<8} "
                        f"true={e.get('true_label',''):<8} "
                        f"conf={cls['confidence']:.2f}  "
                        f"{e.get('subject','')[:50]}"
                    )
                except Exception as ex:
                    fail += 1
                    print(f"  [!] id={eid} failed: {ex}")

            print(f"\n[done] inserted={ok}  failed={fail}")


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "emails.csv"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    asyncio.run(run(csv_file, limit))

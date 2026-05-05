"""
MCP Server: 이메일 분류 시스템의 I/O 계층
- stdio 트랜스포트로 클라이언트 에이전트와 통신
- 노출 도구:
    1) read_emails_csv         : CSV 파일 → JSON 배열
    2) init_email_table        : Postgres 테이블 생성 (idempotent)
    3) insert_classified_email : 분류 결과 1건 upsert
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from typing import Any

import psycopg2
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()

# stdio 트랜스포트에서는 stdout 이 MCP 프로토콜 전용이므로
# 서버 측 로그/에러는 반드시 stderr 로만 보낸다.
def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "mysecret"),
    "dbname": os.getenv("PG_DB", "mcp_emails"),
}


def _conn():
    return psycopg2.connect(**DB_CONFIG)


# ---------- 도구 구현 ----------

def _read_emails_csv(file_path: str) -> list[dict[str, str]]:
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _init_email_table() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS classified_emails (
        id            SERIAL PRIMARY KEY,
        email_id      TEXT UNIQUE NOT NULL,
        sender        TEXT,
        subject       TEXT,
        body          TEXT,
        received_at   TEXT,
        true_label    TEXT,
        category      TEXT NOT NULL,
        confidence    REAL,
        reason        TEXT,
        classified_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql)


def _insert_classified_email(payload: dict[str, Any]) -> None:
    sql = """
    INSERT INTO classified_emails
        (email_id, sender, subject, body, received_at, true_label,
         category, confidence, reason)
    VALUES
        (%(email_id)s, %(sender)s, %(subject)s, %(body)s, %(received_at)s,
         %(true_label)s, %(category)s, %(confidence)s, %(reason)s)
    ON CONFLICT (email_id) DO UPDATE SET
        category      = EXCLUDED.category,
        confidence    = EXCLUDED.confidence,
        reason        = EXCLUDED.reason,
        classified_at = NOW();
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, payload)


# ---------- MCP Server ----------

server = Server("email-classifier")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_emails_csv",
            description=(
                "CSV 파일을 읽어 이메일 레코드 목록을 JSON 으로 반환한다. "
                "기대 컬럼: id, from, subject, body, received_at, true_label."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "CSV 파일의 절대/상대 경로",
                    }
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="init_email_table",
            description="Postgres 에 classified_emails 테이블을 (없을 때만) 생성한다.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="insert_classified_email",
            description=(
                "분류된 이메일 1건을 Postgres 에 upsert 한다. "
                "category 는 URGENT|GENERAL|INTERNAL|SPAM 중 하나."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email_id":    {"type": "string"},
                    "sender":      {"type": "string"},
                    "subject":     {"type": "string"},
                    "body":        {"type": "string"},
                    "received_at": {"type": "string"},
                    "true_label":  {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["URGENT", "GENERAL", "INTERNAL", "SPAM"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason":     {"type": "string"},
                },
                "required": ["email_id", "category"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "read_emails_csv":
            rows = _read_emails_csv(arguments["file_path"])
            return [TextContent(
                type="text",
                text=json.dumps(rows, ensure_ascii=False),
            )]

        if name == "init_email_table":
            _init_email_table()
            return [TextContent(type="text", text="ok")]

        if name == "insert_classified_email":
            # 누락 키는 None 으로 채워서 SQL 바인딩 안전하게
            payload = {
                "email_id":    arguments["email_id"],
                "sender":      arguments.get("sender"),
                "subject":     arguments.get("subject"),
                "body":        arguments.get("body"),
                "received_at": arguments.get("received_at"),
                "true_label":  arguments.get("true_label"),
                "category":    arguments["category"],
                "confidence":  arguments.get("confidence"),
                "reason":      arguments.get("reason"),
            }
            _insert_classified_email(payload)
            return [TextContent(type="text", text="inserted")]

        raise ValueError(f"unknown tool: {name}")

    except Exception as e:
        _log(f"[server] tool {name} failed: {e!r}")
        return [TextContent(type="text", text=f"ERROR: {e}")]


async def main() -> None:
    _log("[server] email-classifier MCP server starting on stdio")
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

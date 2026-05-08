"""
Cognito IdToken으로 보호된 API Gateway 엔드포인트 호출 테스트.
python C:\mcp\api_test.py \
    --url https://[GATEWAY_ID].execute-api.us-east-1.amazonaws.com/production/ses/send-email \
    --region us-east-1 \
    --client-id [CLIENT_ID] \
    --username [EMAIL] \
    --password [PASSWORD] \
    --to [TO_EMAIL_ADDRESS] \
    --subject [제목] \
    --message [내용]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

from cognito_test import sign_in

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def call_api(url: str, id_token: str, body: dict) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        },
    )
    print(f"\n[API 호출] POST {url}")
    print(f"  Headers : Authorization=Bearer {id_token[:30]}..., Content-Type=application/json")
    print(f"  Body    : {body}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            headers = dict(resp.headers.items())
            body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        headers = dict(e.headers.items())
        body_bytes = e.read()
    except urllib.error.URLError as e:
        print(f"  ✗ 연결 실패: {e}")
        return

    print(f"\n  ← Status : {status}")
    print(f"  ← Headers:")
    for k, v in headers.items():
        print(f"      {k}: {v}")
    body_text = body_bytes.decode("utf-8", errors="replace")
    print(f"  ← Body   :")
    try:
        parsed = json.loads(body_text)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(f"      {body_text}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", default=None)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    print(f"[1] Cognito 로그인으로 IdToken 획득 ...")
    tokens = sign_in(
        username=args.username,
        password=args.password,
        client_id=args.client_id,
        client_secret=args.client_secret,
        region=args.region,
    )
    id_token = tokens["IdToken"]
    print(f"  ✓ IdToken 획득 ({len(id_token)} chars)")

    call_api(
        url=args.url,
        id_token=id_token,
        body={"to": args.to, "subject": args.subject, "message": args.message},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

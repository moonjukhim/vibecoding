import asyncio
import json
import sys
from fastmcp import Client

sys.stdout.reconfigure(encoding="utf-8")

INPUT_CSV = r"C:\claude\mcp\day3\emails.csv"
OUTPUT_CSV = r"C:\claude\mcp\day3\emails_labeled.csv"
SERVER_SCRIPT = r"C:\claude\mcp\day3\email_mcp_server.py"


def unwrap(result):
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content"):
        for c in result.content:
            if hasattr(c, "text"):
                try:
                    return json.loads(c.text)
                except Exception:
                    return c.text
    return result


async def main():
    async with Client(SERVER_SCRIPT) as mcp:
        print("=" * 60)
        print("[1/4] Loader: emails.csv 로드")
        print("=" * 60)
        loaded = unwrap(await mcp.call_tool("load_emails", {"csv_path": INPUT_CSV}))
        print(f"로드된 이메일: {len(loaded)}건")
        print(f"컬럼: {list(loaded[0].keys()) if loaded else '없음'}")

        print()
        print("=" * 60)
        print("[2/4] Classifier + [3/4] Labeler: 4분류 + 라벨링 + 저장")
        print("=" * 60)
        result = unwrap(await mcp.call_tool(
            "save_labeled_csv",
            {"input_path": INPUT_CSV, "output_path": OUTPUT_CSV},
        ))
        print(f"저장 완료: {result['saved']} ({result['rows']}건)")

        print()
        print("=" * 60)
        print("[4/4] Evaluator: 정답 대비 정확도 평가")
        print("=" * 60)
        evalr = unwrap(await mcp.call_tool(
            "evaluate_accuracy",
            {"labeled_csv_path": OUTPUT_CSV},
        ))
        print(f"전체: {evalr['total']}건 / 정답: {evalr['correct']}건 / 정확도: {evalr['accuracy'] * 100:.2f}%")
        print()
        print("[클래스별]")
        for label, stat in evalr["per_class"].items():
            tp = stat["tp"]
            support = stat["support"]
            recall = tp / support if support else 0.0
            precision = tp / (tp + stat["fp"]) if (tp + stat["fp"]) else 0.0
            print(f"  {label:8s} support={support:2d}  tp={tp:2d}  fp={stat['fp']:2d}  fn={stat['fn']:2d}  "
                  f"precision={precision:.2f}  recall={recall:.2f}")

        if evalr["mistakes"]:
            print()
            print(f"[오분류 {len(evalr['mistakes'])}건]")
            for m in evalr["mistakes"]:
                print(f"  id={m['id']:>3s}  true={m['true']:8s} pred={m['pred']:8s}  | {m['subject']}")


if __name__ == "__main__":
    asyncio.run(main())

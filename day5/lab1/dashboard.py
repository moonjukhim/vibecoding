"""실습 5-1 — Streamlit 모니터링 대시보드.

agent.py가 만들어낸 metrics.jsonl, scorecard.json, report.md를 시각화한다.
실행:  streamlit run dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
METRICS = ROOT / "metrics.jsonl"
SCORECARD = ROOT / "scorecard.json"
REPORT = ROOT / "report.md"

st.set_page_config(page_title="Lab 5-1 Monitor", layout="wide")
st.title("실습 5-1 — 에이전트 모니터")
st.caption("Planner → Workers(병렬) → Judge → HITL → Publish")

if not METRICS.exists():
    st.warning("아직 메트릭이 없습니다. 먼저 `python agent.py`를 실행하세요.")
    st.stop()

records = [
    json.loads(line)
    for line in METRICS.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
df = pd.DataFrame(records)


def _col(name: str, default=0) -> pd.Series:
    if name in df.columns:
        return df[name].fillna(default)
    return pd.Series([default] * len(df))


total_tokens = int(_col("tokens").sum())
total_seconds = float(_col("seconds").sum())
fail_count = int(_col("failed", False).astype(bool).sum())
worker_count = int((df["event"] == "worker").sum()) if "event" in df.columns else 0
fail_rate = (fail_count / worker_count * 100) if worker_count else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("총 토큰", f"{total_tokens:,}")
c2.metric("누적 소요(초)", f"{total_seconds:.1f}")
c3.metric("Worker 호출", worker_count)
c4.metric("실패 수", fail_count)
c5.metric("실패율", f"{fail_rate:.1f}%")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("이벤트 로그")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if "event" in df.columns and "seconds" in df.columns:
        st.subheader("이벤트별 누적 시간(초)")
        agg = df.groupby("event")["seconds"].sum().sort_values(ascending=False)
        st.bar_chart(agg)

with right:
    st.subheader("Judge 스코어카드")
    if SCORECARD.exists():
        score = json.loads(SCORECARD.read_text(encoding="utf-8"))
        s1, s2 = st.columns(2)
        s1.metric("Overall", f"{score.get('overall', '-')}/5")
        s2.metric("Completeness", f"{score.get('completeness', '-')}/5")
        s3, s4 = st.columns(2)
        s3.metric("Accuracy", f"{score.get('accuracy', '-')}/5")
        s4.metric("Readability", f"{score.get('readability', '-')}/5")
        st.caption(f"Actionability: {score.get('actionability', '-')}/5")
        with st.expander("Rationale"):
            st.write(score.get("rationale", ""))
        issues = score.get("issues") or []
        if issues:
            with st.expander(f"개선점 ({len(issues)})"):
                for i, item in enumerate(issues, 1):
                    st.write(f"{i}. {item}")
    else:
        st.info("scorecard.json 없음 — 아직 Judge가 채점하지 않았습니다.")

st.divider()
st.subheader("최종 리포트 (report.md)")
if REPORT.exists():
    st.markdown(REPORT.read_text(encoding="utf-8"))
else:
    st.info("report.md 없음 — HITL 승인 대기 또는 발행이 거절되었습니다.")

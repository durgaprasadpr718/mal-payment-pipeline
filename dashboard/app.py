"""
Data Quality Monitoring Dashboard for Mal's unified payment platform.

Free stack: Streamlit + Plotly + DuckDB. Deploy free on Streamlit Community Cloud.

Tracks the three things the brief asks for:
  1. Schema compliance rate across the three source systems
  2. Data freshness (time since last successful ingestion)
  3. Anomaly detection (volume drop vs rolling baseline, unexpected null rates)

Run:  streamlit run dashboard/app.py
Reads artifacts produced by run_pipeline.py (output/run_report.json + duckdb).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "output" / "run_report.json"
DB = ROOT / "output" / "mal.duckdb"

# friendly display names so charts never show raw "bill_payments_squad"
NICE = {
    "cards_squad": "Cards",
    "transfers_squad": "Transfers",
    "bill_payments_squad": "Bill Payments",
}
COLOR = {"Cards": "#4F46E5", "Transfers": "#0D9488", "Bill Payments": "#D97706"}

st.set_page_config(page_title="Mal Payment Data Quality",
                   page_icon="\U0001F4CA", layout="wide")

# light styling pass for a cleaner, less default look
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      h1 {font-weight: 700;}
      [data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #ECECF1; border-radius: 14px;
        padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      }
      [data-testid="stMetricLabel"] {color:#6B7280; font-weight:600;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Mal Payment Platform: Data Quality")
st.caption("Unified canonical model across Cards, Transfers and Bill Payments squads")

if not REPORT.exists():
    st.error("No run found. Run `python run_pipeline.py` first.")
    st.stop()

report = json.loads(REPORT.read_text())
run_at = datetime.fromisoformat(report["run_at"])
age_min = (datetime.now(timezone.utc) - run_at).total_seconds() / 60

# ---------------------------------------------------------------------------
# compliance frame (built once, reused)
rows = []
for src, s in report["sources"].items():
    rows.append({
        "Source": NICE.get(src, src),
        "Rows in": s["rows_in"], "Valid": s["valid"],
        "Rejected": s["rejected"],
        "Compliance %": round(s["compliance_rate"] * 100, 2),
    })
comp = pd.DataFrame(rows)
overall_compliance = round(100 * comp["Valid"].sum() /
                           max(comp["Rows in"].sum(), 1), 2)

# ---------------------------------------------------------------------------
# 1. headline KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Canonical events", f"{report['total_events']:,}")
k2.metric("Overall compliance", f"{overall_compliance:.1f}%")
k3.metric("Rejected rows", f"{int(comp['Rejected'].sum()):,}")
k4.metric("Data freshness", f"{age_min:.0f} min ago",
          delta="stale" if age_min > 60 else "fresh",
          delta_color="inverse" if age_min > 60 else "normal")

st.divider()

# ---------------------------------------------------------------------------
# 2. schema compliance by source (horizontal bars = always readable labels)
st.subheader("Schema compliance by source")
left, right = st.columns([3, 2])

with left:
    fig = px.bar(comp.sort_values("Compliance %"), x="Compliance %", y="Source",
                 orientation="h", text="Compliance %",
                 color="Source", color_discrete_map=COLOR, range_x=[0, 105])
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside",
                      cliponaxis=False)
    fig.update_layout(showlegend=False, height=260,
                      margin=dict(l=10, r=30, t=10, b=10),
                      yaxis_title="", xaxis_title="Compliance %",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.dataframe(comp, use_container_width=True, hide_index=True)

# rejection drill-down
for src, s in report["sources"].items():
    if s["rejected"]:
        with st.expander(f"{s['rejected']} rejected row(s) in {NICE.get(src, src)}"):
            sample = s["rejections"][:15]
            for r in sample:
                reason = r["reason"].splitlines()[0]
                st.write(f"`{r['source_event_id']}` {reason}")
            if s["rejected"] > len(sample):
                st.caption(f"showing {len(sample)} of {s['rejected']}")

st.divider()

# ---------------------------------------------------------------------------
# 3. anomaly detection
st.subheader("Anomaly detection")

if DB.exists():
    con = duckdb.connect(str(DB))
    daily = con.execute("""
        SELECT CAST(event_timestamp AS DATE) AS day, source_system, COUNT(*) n
        FROM payment_events GROUP BY 1, 2 ORDER BY 1""").df()
    vol = con.execute(
        "SELECT source_system, COUNT(*) n FROM payment_events GROUP BY 1").df()
    nulls = con.execute("""
        SELECT ROUND(100.0*COUNT(*) FILTER (
            WHERE customer_id IS NULL OR customer_id = '')/COUNT(*), 2) pct
        FROM payment_events""").fetchone()[0]
    con.close()

    daily["Source"] = daily["source_system"].map(NICE).fillna(daily["source_system"])
    vol["Source"] = vol["source_system"].map(NICE).fillna(vol["source_system"])

    # volume anomaly: a day below 50% of that source's median day
    alerts = []
    for src in daily["Source"].unique():
        s = daily[daily["Source"] == src]
        median = s["n"].median()
        for _, row in s.iterrows():
            if median and row["n"] < 0.5 * median:
                alerts.append(f"Volume drop: {src} had {int(row['n'])} events on "
                              f"{row['day']} (median day is {int(median)})")
    if nulls and nulls > 0:
        alerts.append(f"Data quality: {nulls}% of events have an empty or null "
                      f"customer_id (schema valid but worth investigating)")

    a1, a2 = st.columns([1, 1])
    with a1:
        if alerts:
            st.markdown(f"**{len(alerts)} alert(s)**")
            for a in alerts:
                st.warning(a, icon="\u26A0\uFE0F")
        else:
            st.success("No anomalies detected.", icon="\u2705")
    with a2:
        bar = px.bar(vol, x="Source", y="n", color="Source",
                     color_discrete_map=COLOR, text="n")
        bar.update_traces(textposition="outside", cliponaxis=False)
        bar.update_layout(showlegend=False, height=300, yaxis_title="Events",
                          xaxis_title="", margin=dict(l=10, r=10, t=30, b=10),
                          plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(bar, use_container_width=True)

    st.markdown("**Daily event volume (trend)**")
    line = go.Figure()
    for src in daily["Source"].unique():
        s = daily[daily["Source"] == src].sort_values("day")
        line.add_trace(go.Scatter(x=s["day"], y=s["n"], mode="lines+markers",
                                   name=src, line=dict(color=COLOR.get(src),
                                   width=2.5)))
    line.update_layout(height=340, hovermode="x unified",
                       legend=dict(orientation="h", y=1.12, x=0),
                       margin=dict(l=10, r=10, t=10, b=10),
                       yaxis_title="Events per day", xaxis_title="",
                       plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)")
    line.update_xaxes(showgrid=False)
    line.update_yaxes(gridcolor="#F0F0F3")
    st.plotly_chart(line, use_container_width=True)

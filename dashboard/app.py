"""
Mal payment platform demo dashboard (free stack: Streamlit + Plotly + DuckDB).

Two tabs:
  1. Overview and pipeline outputs: the unified canonical model in action
     (volume by payment type, success rates, top cross-product customers,
     currency mix, sample canonical rows).
  2. Data quality monitoring: schema compliance, freshness, anomaly detection.

Deploy free on Streamlit Community Cloud. Run locally:
  streamlit run dashboard/app.py
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

SRC_NICE = {"cards_squad": "Cards", "transfers_squad": "Transfers",
            "bill_payments_squad": "Bill Payments"}
TYPE_NICE = {"card_transaction": "Card", "transfer": "Transfer",
             "bill_payment": "Bill Payment"}
COLOR = {"Cards": "#4F46E5", "Transfers": "#0D9488", "Bill Payments": "#D97706",
         "Card": "#4F46E5", "Transfer": "#0D9488", "Bill Payment": "#D97706"}

st.set_page_config(page_title="Mal Payment Platform",
                   page_icon="\U0001F4B3", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      h1 {font-weight: 700;}
      [data-testid="stMetric"] {
        background:#fff; border:1px solid #ECECF1; border-radius:14px;
        padding:16px 18px; box-shadow:0 1px 3px rgba(0,0,0,0.04);
      }
      [data-testid="stMetricLabel"] {color:#6B7280; font-weight:600;}
      button[data-baseweb="tab"] {font-size:15px; font-weight:600;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Mal Payment Platform")
st.caption("One canonical model unifying Cards, Transfers and Bill Payments")

if not REPORT.exists() or not DB.exists():
    st.error("No run found. Run `python run_pipeline.py` first.")
    st.stop()

report = json.loads(REPORT.read_text())


def q(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def transparent(fig, height=320, legend=False):
    fig.update_layout(height=height, showlegend=legend,
                      margin=dict(l=10, r=10, t=30, b=10),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


tab_out, tab_dq = st.tabs(["Overview and pipeline outputs",
                           "Data quality monitoring"])

# ===========================================================================
# TAB 1: pipeline outputs (the unified model in action)
# ===========================================================================
with tab_out:
    totals = q("""
        SELECT COUNT(*) events,
               COUNT(DISTINCT customer_id) customers,
               COUNT(DISTINCT payment_type) type_count,
               SUM(amount) FILTER (WHERE status = 'completed') total_value
        FROM payment_events""").iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Canonical events", f"{int(totals['events']):,}")
    k2.metric("Value processed (AED)", f"{totals['total_value']:,.0f}")
    k3.metric("Unique customers", f"{int(totals['customers']):,}")
    k4.metric("Payment types unified", int(totals["type_count"]))
    st.divider()

    c1, c2 = st.columns([2, 3])

    # events by payment type (donut): proves three sources land in one model
    with c1:
        st.markdown("**Events by payment type**")
        bt = q("SELECT payment_type, COUNT(*) n FROM payment_events GROUP BY 1")
        bt["Type"] = bt["payment_type"].map(TYPE_NICE).fillna(bt["payment_type"])
        pie = px.pie(bt, names="Type", values="n", hole=0.55,
                     color="Type", color_discrete_map=COLOR)
        pie.update_traces(textposition="outside", textinfo="label+percent")
        st.plotly_chart(transparent(pie, 300), width="stretch")

    # success rate by source
    with c2:
        st.markdown("**Success rate by source**")
        sr = q("""
            SELECT source_system,
                   ROUND(100.0*COUNT(*) FILTER (WHERE status='completed')
                         /COUNT(*), 1) success_pct
            FROM payment_events GROUP BY 1""")
        sr["Source"] = sr["source_system"].map(SRC_NICE).fillna(sr["source_system"])
        bar = px.bar(sr.sort_values("success_pct"), x="success_pct", y="Source",
                     orientation="h", text="success_pct", range_x=[0, 105],
                     color="Source", color_discrete_map=COLOR)
        bar.update_traces(texttemplate="%{text}%", textposition="outside",
                          cliponaxis=False)
        bar.update_layout(xaxis_title="Success %", yaxis_title="")
        st.plotly_chart(transparent(bar, 300), width="stretch")

    # daily volume by payment type (stacked area)
    st.markdown("**Daily payment volume by type**")
    dv = q("""
        SELECT CAST(event_timestamp AS DATE) event_day, payment_type, COUNT(*) n
        FROM payment_events GROUP BY 1, 2 ORDER BY 1""")
    dv["Type"] = dv["payment_type"].map(TYPE_NICE).fillna(dv["payment_type"])
    area = px.area(dv, x="event_day", y="n", color="Type",
                   color_discrete_map=COLOR)
    area.update_layout(xaxis_title="", yaxis_title="Events per day",
                       legend=dict(orientation="h", y=1.12, x=0))
    st.plotly_chart(transparent(area, 340, legend=True), width="stretch")

    c3, c4 = st.columns(2)

    # top cross-product customers (the customer-360 win of unification)
    with c3:
        st.markdown("**Top customers by cross-product spend**")
        top = q("""
            SELECT customer_id,
                   SUM(amount) FILTER (WHERE status='completed') total_value,
                   COUNT(DISTINCT payment_type) products
            FROM payment_events WHERE customer_id <> ''
            GROUP BY 1 ORDER BY total_value DESC NULLS LAST LIMIT 10""")
        tb = px.bar(top.sort_values("total_value"), x="total_value", y="customer_id",
                    orientation="h", color="products",
                    color_continuous_scale=["#C7D2FE", "#4F46E5"])
        tb.update_layout(xaxis_title="Completed value (AED)", yaxis_title="",
                         coloraxis_colorbar=dict(title="Products"))
        st.plotly_chart(transparent(tb, 340), width="stretch")

    # currency mix (matters for a UAE neobank with FX)
    with c4:
        st.markdown("**Currency mix (completed value)**")
        cur = q("""
            SELECT currency, SUM(amount) total FROM payment_events
            WHERE status='completed' GROUP BY 1 ORDER BY total DESC""")
        cp = px.pie(cur, names="currency", values="total", hole=0.55)
        cp.update_traces(textposition="outside", textinfo="label+percent")
        st.plotly_chart(transparent(cp, 340), width="stretch")

    # sample of the canonical output
    st.markdown("**Sample canonical events (the unified output rows)**")
    sample = q("""
        SELECT event_id, source_system, payment_type, status, amount, currency,
               customer_id, is_shariah_compliant, event_timestamp
        FROM payment_events ORDER BY event_timestamp DESC LIMIT 25""")
    sample["source_system"] = sample["source_system"].map(SRC_NICE).fillna(
        sample["source_system"])
    sample["payment_type"] = sample["payment_type"].map(TYPE_NICE).fillna(
        sample["payment_type"])
    st.dataframe(sample, width="stretch", hide_index=True)

# ===========================================================================
# TAB 2: data quality monitoring
# ===========================================================================
with tab_dq:
    run_at = datetime.fromisoformat(report["run_at"])
    age_min = (datetime.now(timezone.utc) - run_at).total_seconds() / 60

    rows = []
    for src, s in report["sources"].items():
        rows.append({"Source": SRC_NICE.get(src, src), "Rows in": s["rows_in"],
                     "Valid": s["valid"], "Rejected": s["rejected"],
                     "Compliance %": round(s["compliance_rate"] * 100, 2)})
    comp = pd.DataFrame(rows)
    overall = round(100 * comp["Valid"].sum() / max(comp["Rows in"].sum(), 1), 2)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Canonical events", f"{report['total_events']:,}")
    k2.metric("Overall compliance", f"{overall:.1f}%")
    k3.metric("Rejected rows", f"{int(comp['Rejected'].sum()):,}")
    k4.metric("Data freshness", f"{age_min:.0f} min ago",
              delta="stale" if age_min > 60 else "fresh",
              delta_color="inverse" if age_min > 60 else "normal")
    st.divider()

    st.subheader("Schema compliance by source")
    left, right = st.columns([3, 2])
    with left:
        fig = px.bar(comp.sort_values("Compliance %"), x="Compliance %",
                     y="Source", orientation="h", text="Compliance %",
                     color="Source", color_discrete_map=COLOR, range_x=[0, 105])
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside",
                          cliponaxis=False)
        fig.update_layout(yaxis_title="", xaxis_title="Compliance %")
        st.plotly_chart(transparent(fig, 260), width="stretch")
    with right:
        st.dataframe(comp, width="stretch", hide_index=True)

    for src, s in report["sources"].items():
        if s["rejected"]:
            with st.expander(
                    f"{s['rejected']} rejected row(s) in {SRC_NICE.get(src, src)}"):
                for r in s["rejections"][:15]:
                    st.write(f"`{r['source_event_id']}` "
                             f"{r['reason'].splitlines()[0]}")
                if s["rejected"] > 15:
                    st.caption(f"showing 15 of {s['rejected']}")

    st.divider()
    st.subheader("Anomaly detection")

    daily = q("""
        SELECT CAST(event_timestamp AS DATE) event_day, source_system, COUNT(*) n
        FROM payment_events GROUP BY 1, 2 ORDER BY 1""")
    nulls = q("""
        SELECT ROUND(100.0*COUNT(*) FILTER (
            WHERE customer_id IS NULL OR customer_id='')/COUNT(*), 2) pct
        FROM payment_events""").iloc[0]["pct"]
    daily["Source"] = daily["source_system"].map(SRC_NICE).fillna(
        daily["source_system"])

    alerts = []
    for src in daily["Source"].unique():
        s = daily[daily["Source"] == src]
        med = s["n"].median()
        for _, row in s.iterrows():
            if med and row["n"] < 0.5 * med:
                alerts.append(f"Volume drop: {src} had {int(row['n'])} events on "
                              f"{row['event_day']} (median day is {int(med)})")
    if nulls and nulls > 0:
        alerts.append(f"Data quality: {nulls}% of events have an empty or null "
                      f"customer_id (schema valid but worth investigating)")

    if alerts:
        st.markdown(f"**{len(alerts)} alert(s)**")
        for a in alerts:
            st.warning(a, icon="\u26A0\uFE0F")
    else:
        st.success("No anomalies detected.", icon="\u2705")

    st.markdown("**Daily event volume (trend)**")
    line = go.Figure()
    for src in daily["Source"].unique():
        s = daily[daily["Source"] == src].sort_values("event_day")
        line.add_trace(go.Scatter(x=s["event_day"], y=s["n"],
                                   mode="lines+markers", name=src,
                                   line=dict(color=COLOR.get(src), width=2.5)))
    line.update_layout(hovermode="x unified", yaxis_title="Events per day",
                       xaxis_title="", legend=dict(orientation="h", y=1.12, x=0))
    line.update_yaxes(gridcolor="#F0F0F3")
    st.plotly_chart(transparent(line, 340, legend=True), width="stretch")

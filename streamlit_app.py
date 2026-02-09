"""
Traksys OEE Analyzer — Web Interface
=====================================
Upload your Traksys OEE export, get back a formatted analysis workbook.

Supports both:
  - Raw Traksys exports (OEE Period Detail + Event Summary)
  - Pre-processed OEE workbooks (DayShiftHour format)

Usage:
  streamlit run streamlit_app.py
"""

import streamlit as st
import tempfile
import os
from datetime import datetime

import pandas as pd

from analyze import load_oee_data, load_downtime_data, analyze, write_excel
from parse_traksys import parse_oee_period_detail, parse_event_summary, detect_file_type
from history import save_run, load_history

st.set_page_config(
    page_title="Traksys OEE Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("Traksys OEE Analyzer")
st.markdown("Upload your OEE export. Get back a formatted analysis workbook with shift deep dives, loss breakdowns, and prioritized actions.")

# --- Tab navigation ---
tab_analyze, tab_history = st.tabs(["Analyze", "Plant History"])

# =====================================================================
# TAB 1: ANALYZE (original functionality)
# =====================================================================
with tab_analyze:
    # --- File uploads ---
    col1, col2 = st.columns(2)

    with col1:
        oee_file = st.file_uploader(
            "OEE Data (Excel)",
            type=["xlsx", "xls"],
            help="Traksys 'OEE Period Detail' export OR processed workbook with DayShiftHour sheets",
        )

    with col2:
        downtime_file = st.file_uploader(
            "Downtime Data (Excel or JSON) — optional",
            type=["json", "xlsx", "xls"],
            help="Traksys 'Event Summary' export (.xlsx) or knowledge base (.json)",
        )

    # --- Analyze ---
    if oee_file is not None:
        if st.button("Analyze", type="primary", use_container_width=True):
            with st.spinner("Running analysis..."):
                # Write uploaded files to temp directory
                tmp_dir = tempfile.mkdtemp()
                oee_path = os.path.join(tmp_dir, oee_file.name)
                with open(oee_path, "wb") as f:
                    f.write(oee_file.getbuffer())

                # Detect OEE file format and load accordingly
                file_type = detect_file_type(oee_path)

                try:
                    if file_type == "oee_period_detail":
                        st.info("Detected: Traksys OEE Period Detail export")
                        hourly, shift_summary, overall, hour_avg = parse_oee_period_detail(oee_path)
                    else:
                        hourly, shift_summary, overall, hour_avg = load_oee_data(oee_path)

                    # Load downtime / event data
                    downtime = None
                    if downtime_file is not None:
                        dt_path = os.path.join(tmp_dir, downtime_file.name)
                        with open(dt_path, "wb") as f:
                            f.write(downtime_file.getbuffer())
                        try:
                            if downtime_file.name.lower().endswith(".json"):
                                downtime = load_downtime_data(dt_path)
                            else:
                                dt_type = detect_file_type(dt_path)
                                if dt_type == "event_summary":
                                    st.info("Detected: Traksys Event Summary export")
                                    downtime = parse_event_summary(dt_path)
                                else:
                                    st.warning("Unrecognized downtime file format")
                        except Exception as e:
                            st.warning(f"Could not load downtime data: {e}")

                    # Run analysis
                    results = analyze(hourly, shift_summary, overall, hour_avg, downtime)

                    # Write output
                    basename = os.path.splitext(oee_file.name)[0]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                    suffix = "_FULL_ANALYSIS" if downtime else "_ANALYSIS"
                    output_name = f"{basename}{suffix}_{timestamp}.xlsx"
                    output_path = os.path.join(tmp_dir, output_name)
                    write_excel(results, output_path)

                    # Save to history
                    try:
                        save_run(results, hourly, shift_summary, overall, downtime)
                    except Exception:
                        pass  # history save should never block the main workflow

                    # Read back for download
                    with open(output_path, "rb") as f:
                        output_bytes = f.read()

                    st.success(f"Analysis complete — {len(results)} sheets generated")

                    # Download button
                    st.download_button(
                        label=f"Download {output_name}",
                        data=output_bytes,
                        file_name=output_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

                    # --- Quick summary ---
                    st.markdown("---")
                    st.subheader("Quick Summary")

                    exec_df = results.get("Executive Summary")
                    if exec_df is not None:
                        metrics = exec_df[exec_df["Metric"].astype(str).str.strip() != ""]
                        cols = st.columns(min(4, len(metrics)))
                        for i, (_, row) in enumerate(metrics.iterrows()):
                            if i < len(cols):
                                cols[i % len(cols)].metric(str(row["Metric"]), str(row["Value"]))

                    # Fault summary
                    fault_df = results.get("Fault Summary")
                    if fault_df is not None:
                        st.subheader("Fault Classification")
                        st.dataframe(
                            fault_df[["Fault Category", "Total Hours", "% of All Downtime", "Who Owns This"]],
                            use_container_width=True,
                            hide_index=True,
                        )

                    # Downtime Pareto
                    pareto_df = results.get("Downtime Pareto")
                    if pareto_df is not None:
                        st.subheader("Top Downtime Causes")
                        display_cols = [c for c in ["Cause", "Fault Type", "Total Minutes", "Events", "% of Total", "Cumulative %"] if c in pareto_df.columns]
                        st.dataframe(
                            pareto_df[display_cols].head(10),
                            use_container_width=True,
                            hide_index=True,
                        )

                    # Top actions
                    focus_df = results.get("What to Focus On")
                    if focus_df is not None:
                        st.subheader("Top Actions")
                        for _, row in focus_df.head(5).iterrows():
                            st.markdown(f"**#{row['Priority']}:** {row['Finding']}")
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Step 1: {row['Step 1']}")

                    # Sheet list
                    st.markdown("---")
                    st.caption(f"Sheets in output: {', '.join(results.keys())}")

                except ValueError as e:
                    err_msg = str(e)
                    if "worksheet" in err_msg.lower() or "sheet" in err_msg.lower():
                        st.error("**Sheet mismatch** — your Excel file doesn't have the expected sheet names.")
                        st.info(
                            "The analyzer expects these sheets in your Traksys OEE export:\n\n"
                            "| Sheet | Columns |\n"
                            "|---|---|\n"
                            "| **DayShiftHour** | 14 columns — Date, Shift, StartTime, Hour, DurationHours, ProductCode, Job, GoodCases, BadCases, TotalCases, Availability, Performance, Quality, OEE |\n"
                            "| **DayShift_Summary** | 7 columns — Date, Shift, Hours, GoodCases, BadCases, TotalCases, AvgOEE |\n"
                            "| **Shift_Summary** | 6 columns — Shift, Hours, GoodCases, BadCases, TotalCases, AvgOEE |\n"
                            "| **ShiftHour_Summary** | 5 columns — Shift, Hour, AvgAvailability, AvgPerformance, AvgOEE |\n\n"
                            "**Fix options:**\n"
                            "1. Rename your sheets to match the names above\n"
                            "2. Check that you're uploading the correct Traksys OEE export file"
                        )
                        st.code(err_msg, language=None)
                    else:
                        st.error(f"Analysis failed: {e}")
                        st.exception(e)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                    st.exception(e)
    else:
        st.info("Upload a Traksys OEE export (.xlsx) to get started.")

# =====================================================================
# TAB 2: PLANT HISTORY
# =====================================================================
with tab_history:
    history = load_history()

    if history is None:
        st.info("No history yet. Run an analysis on the Analyze tab to start building your trend data.")
    else:
        runs = history["runs"]
        shifts = history["shifts"]
        downtime_hist = history["downtime"]

        n_runs = len(runs)
        total_days = int(runs["n_days"].sum())
        latest_oee = runs.iloc[-1]["avg_oee"]
        first_oee = runs.iloc[0]["avg_oee"]
        oee_delta = latest_oee - first_oee

        if oee_delta > 1:
            trend_dir = "Improving"
        elif oee_delta < -1:
            trend_dir = "Declining"
        else:
            trend_dir = "Flat"

        # --- Key stats ---
        st.subheader("Overview")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Runs Analyzed", n_runs)
        c2.metric("Total Days Covered", total_days)
        c3.metric("Latest OEE", f"{latest_oee:.1f}%")
        c4.metric("OEE Trend", trend_dir, delta=f"{oee_delta:+.1f} pts" if n_runs > 1 else None)

        # --- OEE Trend Chart ---
        st.subheader("OEE Over Time")
        oee_chart = runs[["date_from", "avg_oee"]].copy()
        oee_chart = oee_chart.rename(columns={"date_from": "Period Start", "avg_oee": "OEE %"})
        oee_chart = oee_chart.set_index("Period Start")

        if n_runs >= 7:
            oee_chart["7-Run Avg"] = oee_chart["OEE %"].rolling(7, min_periods=1).mean()

        st.line_chart(oee_chart)

        # --- A / P / Q Breakdown ---
        if n_runs > 1:
            st.subheader("Availability / Performance / Quality")
            apq_chart = runs[["date_from", "avg_availability", "avg_performance", "avg_quality"]].copy()
            apq_chart = apq_chart.rename(columns={
                "date_from": "Period Start",
                "avg_availability": "Availability %",
                "avg_performance": "Performance %",
                "avg_quality": "Quality %",
            })
            apq_chart = apq_chart.set_index("Period Start")
            st.line_chart(apq_chart)

        # --- Shift OEE Comparison ---
        if len(shifts) > 0 and n_runs > 1:
            st.subheader("Shift OEE Comparison")
            shift_pivot = shifts.pivot_table(
                index="date_from", columns="shift", values="oee_pct", aggfunc="first"
            )
            shift_pivot.index.name = "Period Start"
            st.line_chart(shift_pivot)

        # --- Recurring Downtime Causes ---
        if len(downtime_hist) > 0:
            st.subheader("Recurring Downtime Causes (Across All Runs)")
            agg_dt = (
                downtime_hist.groupby("cause")
                .agg(total_minutes=("minutes", "sum"), appearances=("run_id", "nunique"))
                .sort_values("total_minutes", ascending=False)
                .head(10)
                .reset_index()
            )
            agg_dt.columns = ["Cause", "Total Minutes (All Runs)", "# Runs Appeared"]
            st.dataframe(agg_dt, use_container_width=True, hide_index=True)

            # Bar chart of top causes
            bar_data = agg_dt.set_index("Cause")["Total Minutes (All Runs)"].head(7)
            st.bar_chart(bar_data)

        # --- Run History Table ---
        st.subheader("Run Log")
        display_runs = runs[["run_id", "date_from", "date_to", "n_days",
                             "avg_oee", "avg_cph", "total_cases", "cases_lost"]].copy()
        display_runs.columns = ["Run", "From", "To", "Days", "OEE %", "CPH", "Cases", "Cases Lost"]
        display_runs["Run"] = display_runs["Run"].str[:19]  # trim to readable timestamp
        st.dataframe(display_runs, use_container_width=True, hide_index=True)

# --- Footer ---
st.markdown("---")
st.caption("Built by Brian Crusoe | Numbers from the machine, not opinions")

"""
History persistence for Traksys OEE Analyzer
=============================================
Appends key metrics from each analysis run to history.jsonl (one JSON object
per line). No extra dependencies — uses json + pandas.
"""

import json
import os
from datetime import datetime

import pandas as pd

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.jsonl")


def save_run(results, hourly, shift_summary, overall, downtime=None):
    """Extract key metrics from an analysis run and append to history.jsonl."""

    date_min = hourly["date"].min()
    date_max = hourly["date"].max()
    n_days = hourly["date_str"].nunique()
    total_cases = float(hourly["total_cases"].sum())
    total_hours = float(hourly["total_hours"].sum())
    avg_cph = total_cases / total_hours if total_hours > 0 else 0.0

    # Pull OEE components from Executive Summary (already computed)
    exec_df = results.get("Executive Summary")
    avg_oee = avg_avail = avg_perf = avg_qual = 0.0
    cases_lost = 0.0
    if exec_df is not None:
        lookup = dict(zip(exec_df["Metric"].astype(str).str.strip(), exec_df["Value"]))
        avg_oee = _parse_pct(lookup.get("Average OEE", "0"))
        avg_avail = _parse_pct(lookup.get("Average Availability", "0"))
        avg_perf = _parse_pct(lookup.get("Average Performance", "0"))
        avg_qual = _parse_pct(lookup.get("Average Quality", "0"))
        cases_lost = _parse_num(lookup.get("Est. Cases Lost vs Benchmark", "0"))

    # Per-shift summary
    shifts = []
    loss_df = results.get("Loss Breakdown")
    for _, row in overall.iterrows():
        shift_rec = {
            "shift": str(row["shift"]),
            "oee_pct": round(float(row["oee_pct"]), 1),
            "cases_per_hour": round(float(row.get("cases_per_hour", 0)), 0),
            "total_cases": round(float(row.get("total_cases", 0)), 0),
        }
        # Add primary loss from Loss Breakdown if available
        if loss_df is not None:
            match = loss_df[loss_df["Shift"] == row["shift"]]
            if len(match) > 0:
                shift_rec["primary_loss"] = str(match.iloc[0].get("Primary Loss Driver", ""))
        shifts.append(shift_rec)

    # Top 5 downtime causes (if available)
    top_downtime = []
    pareto_df = results.get("Downtime Pareto")
    if pareto_df is not None and len(pareto_df) > 0:
        for _, row in pareto_df.head(5).iterrows():
            top_downtime.append({
                "cause": str(row["Cause"]),
                "minutes": round(float(row["Total Minutes"]), 0),
                "pct_of_total": round(float(row["% of Total"]), 1),
            })

    record = {
        "run_id": datetime.now().isoformat(),
        "date_from": date_min.strftime("%Y-%m-%d"),
        "date_to": date_max.strftime("%Y-%m-%d"),
        "n_days": int(n_days),
        "avg_oee": round(avg_oee, 1),
        "avg_availability": round(avg_avail, 1),
        "avg_performance": round(avg_perf, 1),
        "avg_quality": round(avg_qual, 1),
        "avg_cph": round(avg_cph, 0),
        "total_cases": round(total_cases, 0),
        "total_hours": round(total_hours, 1),
        "cases_lost": round(cases_lost, 0),
        "shifts": shifts,
        "top_downtime": top_downtime,
    }

    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return record


def load_history():
    """Read history.jsonl and return structured DataFrames.

    Returns dict with keys:
      - runs: one row per analysis run (plant-level metrics)
      - shifts: one row per shift per run
      - downtime: one row per downtime cause per run
    Returns None if no history file exists or it's empty.
    """
    if not os.path.exists(HISTORY_FILE) or os.path.getsize(HISTORY_FILE) == 0:
        return None

    records = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        return None

    # Runs table
    runs = pd.DataFrame([{
        "run_id": r["run_id"],
        "date_from": r["date_from"],
        "date_to": r["date_to"],
        "n_days": r["n_days"],
        "avg_oee": r["avg_oee"],
        "avg_availability": r["avg_availability"],
        "avg_performance": r["avg_performance"],
        "avg_quality": r["avg_quality"],
        "avg_cph": r["avg_cph"],
        "total_cases": r["total_cases"],
        "total_hours": r["total_hours"],
        "cases_lost": r["cases_lost"],
    } for r in records])

    # Shifts table
    shift_rows = []
    for r in records:
        for s in r.get("shifts", []):
            shift_rows.append({
                "run_id": r["run_id"],
                "date_from": r["date_from"],
                "shift": s["shift"],
                "oee_pct": s["oee_pct"],
                "cases_per_hour": s.get("cases_per_hour", 0),
                "total_cases": s.get("total_cases", 0),
                "primary_loss": s.get("primary_loss", ""),
            })
    shifts = pd.DataFrame(shift_rows) if shift_rows else pd.DataFrame()

    # Downtime table
    dt_rows = []
    for r in records:
        for d in r.get("top_downtime", []):
            dt_rows.append({
                "run_id": r["run_id"],
                "date_from": r["date_from"],
                "cause": d["cause"],
                "minutes": d["minutes"],
                "pct_of_total": d["pct_of_total"],
            })
    downtime = pd.DataFrame(dt_rows) if dt_rows else pd.DataFrame()

    return {"runs": runs, "shifts": shifts, "downtime": downtime}


def _parse_pct(val):
    """Parse '29.5%' or '85.3%' to float."""
    s = str(val).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_num(val):
    """Parse '1,234' or '1234.5' to float."""
    s = str(val).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0

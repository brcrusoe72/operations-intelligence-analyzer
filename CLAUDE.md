# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Traksys OEE Analyzer** — Production-grade OEE (Overall Equipment Effectiveness) analysis suite for food manufacturing. Reads Traksys/MES data exports and generates multi-sheet Excel reports with shift deep dives, downtime Pareto analysis, fault classification, and prioritized action recommendations. Includes a Streamlit web interface.

All code lives in `traksys-oee-analyzer/`.

## Commands

```bash
# Install dependencies
pip install -r traksys-oee-analyzer/requirements.txt

# Run tests
python -m pytest traksys-oee-analyzer/test_core.py -v
python -m pytest traksys-oee-analyzer/test_analysis_report.py -v
python -m pytest traksys-oee-analyzer/ -v          # all tests

# Run Streamlit app locally
streamlit run traksys-oee-analyzer/streamlit_app.py

# CLI usage
python traksys-oee-analyzer/analyze.py <oee_export.xlsx> [--downtime kb.json]
python traksys-oee-analyzer/third_shift_report.py <oee_export.xlsx> [--downtime kb.json] [--product product_data.json]
python traksys-oee-analyzer/third_shift_targets.py [--product product_data.json] [--downtime kb.json]
```

No linter, formatter, or CI pipeline is configured.

## Architecture

```
Input (Excel/JSON) → Parsing → Analysis Engine → Reporting (Excel/PDF/Web)
```

### Core Modules

- **`analyze.py`** (2400 lines) — Main OEE analysis engine. Loads data with fuzzy sheet/column matching, calculates production-weighted OEE, builds shift summaries, dead hour narratives, fault classification, and writes 5+ sheet Excel workbooks. Entry point: `analyze()` orchestrates the pipeline, `write_excel()` generates output.

- **`shared.py`** — Single source of truth for fault classification keywords (Equipment, Process, Scheduled), product normalization (operator-entered variants → clean names), rated speeds (CPH), pack types, per-shift case targets, and equipment scanning keywords. All other modules import from here.

- **`parse_traksys.py`** — Converts raw Traksys OEE Period Detail exports (block-based, 13 rows per time period) into the standard DataFrame format that `analyze.py` expects. Handles timestamp parsing, shift start offsets, and `#DIV/0!` recovery.

- **`parse_passdown.py`** — Parses operator shift passdown spreadsheets (Area/Issue/Time/Notes format) with auto-format detection. Output matches `parse_event_summary()` shape so it plugs directly into the analysis pipeline.

- **`oee_history.py`** — Append-only JSONL history log + SPC engine. `save_run()` appends KPIs, `tend_garden()` calculates control limits (mean ± 3σ), runs Nelson Rules violation detection, and classifies chronic vs acute downtime trends.

- **`analysis_report.py`** — Generates 2-page PDF analysis reports. Consolidates up to 6 daily analysis workbooks into a scorecard (page 1) + root cause/actions (page 2). Uses `fpdf2`.

- **`third_shift_report.py`** — 13-sheet deep dive for a specific shift: hour-by-hour patterns, product-level granularity, day-of-week breakdowns, equipment issue correlations, consistency scores.

- **`third_shift_targets.py`** — Weekly target tracker with email summary generation. Product-aware targets from plant standards.

- **`streamlit_app.py`** — Web interface with 4 tabs: Analyze, Shift Deep Dive, Analysis Report, Plant History. Deployed on Streamlit Cloud.

### Key Design Patterns

**Production-weighted metrics:** OEE is always calculated as `sum(metric × hours) / sum(hours)`, never simple averages. This prevents short intervals with bad OEE from skewing results.

**Fuzzy sheet/column matching:** `_smart_rename()` maps 50+ header variants to internal names with positional fallback. `_match_sheet()` uses aliases to find sheets regardless of naming. This makes the tool resilient to Traksys export format variations.

**Fault classification hierarchy** (in `shared.py:classify_fault()`): Unassigned → Scheduled → Micro Stops → Process → Equipment → dash-contains fallback → Unclassified. Order matters.

**File type auto-detection:** `detect_file_type()` in `parse_traksys.py` distinguishes raw Traksys exports from pre-processed workbooks by checking sheet names.

## Data Flow

Input formats: OEE Excel exports (DayShiftHour sheet or raw OEE Period Detail), optional downtime JSON knowledge bases, optional shift passdown spreadsheets, optional product data JSON.

Output formats: Multi-sheet Excel (.xlsx via xlsxwriter), 2-page PDF (via fpdf2), email text templates.

Runtime data: `history.jsonl` (append-only run log), `plant_trends.json` (SPC intelligence, auto-generated).

## Tech Stack

Python 3, pandas, numpy, openpyxl (read), xlsxwriter (write), fpdf2 (PDF), Streamlit (web UI). No database — all file-based.

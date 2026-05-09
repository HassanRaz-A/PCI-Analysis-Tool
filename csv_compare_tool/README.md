# CSV / Excel Comparison Tool

A desktop tool for comparing tabular data files against a reference, with
GUI and CLI modes. Built for RF / NOC / KPI workflows but works on any
CSV / TSV / XLSX data.

## Why this exists

You have a "reference" — planned cell list, golden config, last week's KPI
snapshot — and a pile of "main" files coming out of TEMS, Gladiator, or some
export. You want to know:

- Which rows in main are present in reference? (lookup)
- Where do values disagree between main and reference? (diff)
- Where has a numeric KPI drifted beyond a threshold? (threshold)

This tool answers all three, on a *composite* key (e.g. `eNodeB+Cell+PCI`),
across many files, in one pass — and gives you a color-coded XLSX.

## Install

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10+ recommended.

## Run the GUI

```bash
python main.py
```

Workflow:

1. **Add main files** — drag a folder onto the list, or use the buttons.
2. **Pick a reference file** and (if Excel) the sheet.
3. **Set comparison config**:
   - Mode: `exists`, `diff`, or `threshold`
   - Key columns (comma-separated, in matching order on each side)
   - For `diff`: the columns whose values you want to compare
   - For `threshold`: the numeric columns and the |Δ| trigger
4. **Run** — progress bar shows per-sheet progress.
5. **Save the report** — XLSX with one Summary sheet plus per-file detail
   sheets (matched in green, unmatched in red, diffs/breaches in amber).

The last-used config is saved to `~/.csv_compare_tool/config.json`. Logs
go to `~/.csv_compare_tool/logs/app.log` (rotating).

## Run from the command line

Same engine, no GUI. Useful for scheduled / cron / CI runs.

```bash
# Simple existence check
python cli.py \
  --main ./exports --ref reference.xlsx \
  --keys-main eNodeB_ID,Cell_ID,PCI \
  --keys-ref  eNodeB,Cell,PCI \
  --out report.xlsx

# RSRP drift detection
python cli.py \
  --main today.csv --ref baseline.xlsx \
  --keys-main eNodeB_ID,Cell_ID,PCI \
  --keys-ref  eNodeB,Cell,PCI \
  --mode threshold --thr-main RSRP --thr-ref RSRP --thr 10 \
  --out drift_report.xlsx

# Per-column DIFF
python cli.py \
  --main current.xlsx --ref planned.xlsx \
  --keys-main Site,Sector --keys-ref Site,Sector \
  --mode diff --diff-cols Azimuth,Tilt,PCI \
  --out config_drift.xlsx
```

## Architecture

```
core/                 # pure logic, no Qt dependency
├── loaders.py        # CSV / XLSX / TSV → DataFrame
├── normalizer.py     # whitespace, case, NaN handling
├── comparator.py     # the four comparison modes
└── exporter.py       # color-coded XLSX writer

gui/                  # PyQt6 layer
├── main_window.py    # the UI
└── workers.py        # QThread wrappers around core

cli.py                # CLI on top of the same core
main.py               # GUI entry point
tests/smoke.py        # end-to-end engine test (run anytime)
```

The `core/` package is import-clean of Qt — the engine can be reused in
notebooks, scripts, automated pipelines, etc.

## Testing the engine

```bash
python tests/smoke.py
```

This builds synthetic RF-style data and exercises every mode + the export.
If this passes, the engine is healthy regardless of GUI state.

## Comparison modes — what they actually do

| Mode | Output | When to use |
|---|---|---|
| `exists` | `matched` + `unmatched` rows | "Is this cell in our planned list?" |
| `diff` | `matched`/`unmatched` + per-column value differences | "Has the configured tilt/azimuth/PCI changed?" |
| `threshold` | `matched`/`unmatched` + rows where `|main − ref| > X` | "Has RSRP/SINR drifted by more than 10 dB?" |

All three use the same composite-key matching, so you can match on
`(eNodeB, Cell, PCI)` and not worry about per-column collisions.

## Roadmap (next-version ideas)

- Multi-column threshold profiles loaded from a JSON file (so a NOC
  team can ship "RSRP < −110 + SINR < 0 + Throughput drop > 30%" as one rule)
- PCI conflict / mod-3 / mod-6 analyzer (single-file mode, no reference)
- Neighbor-list delta (planned vs. actual ANR neighbors per cell)
- Site-level rollup view in the GUI

## License

Use it however you like in your own work.

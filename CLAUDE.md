# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python -m streamlit run app.py
```

The dev container auto-runs this on port 8501. For Streamlit Cloud the `Procfile` and `railway.toml` handle deployment — any push to `main` redeploys the live app at **https://blackfoilstrafficlight.streamlit.app**.

Credentials (`ORG_ID`, `TOKEN`, `URL`) are loaded from Streamlit Cloud secrets in production and from `.env` locally (see `config.py`). The `.env` file is gitignored — never commit it.

## Architecture

### Data Pipeline (end-to-end)

```
InfluxDB (data.sailgp.tech)
  → data.flux query (templated with boat, time range, measurement filter)
  → SGPDataProvider.get_data()        # raw pivot table, GPS scaling, linear interpolation
  → SGPDataProvider.process_data()    # rename → normalize → filter → period detection
  → app.py                            # display period aggregates as traffic-light cards
```

### Module responsibilities

| File | Role |
|---|---|
| `app.py` | Streamlit UI — sidebar controls, preset management, rendering 14 metric cards |
| `data_fetcher.py` | `SGPDataProvider` class — InfluxDB client, orchestrates all processing |
| `col_mapping.py` | `RENAMING_DICT` (InfluxDB field names → internal names) and `COLS_360` (angle columns needing circular mean) |
| `utils.py` | Pure data transforms: windward/leeward derivation, angle normalization, GPS→UTM, IMU travel filter |
| `period_analysis.py` | Straight-line detection, 6-second period segmentation, per-period metric aggregation |
| `maneuver_analysis.py` | Tack/gybe detection and metrics — implemented but not yet wired into the dashboard |
| `presets.json` | Named target configurations (target value + tolerance per metric, per sailing direction) |
| `data.flux` | Flux query template with `{startTime}`, `{stopTime}`, `{boat}`, `{measurementFilter}` placeholders |

### Key conventions

**Column naming:** `RENAMING_DICT` in `col_mapping.py` is the single source of truth for all field names. Adding a new sensor field means adding an entry there first. Columns that are angles needing circular statistics must also be added to `COLS_360`.

**Angle normalization (`_n` suffix):** `utils.normalize_columns()` multiplies angular columns by `sign(twa)` to produce port/starboard-agnostic values. The resulting `twa_n`, `heel_n`, etc. are what the period filters and dashboard display. The `_n` suffix distinguishes normalized from raw angles.

**Windward/leeward abstraction:** `utils.add_windward_leeward_metrics()` auto-generates `windward_*` and `leeward_*` columns from every `port_*`/`stbd_*` pair, switching based on TWA sign. The dashboard uses `windward_cant`, `leeward_cant`, etc. rather than port/stbd directly.

**Straight-line detection:** A row is "straight line" when yaw rate is low, board state is foiling (leeward board down, windward board up), and speed meets the upwind or downwind threshold. Rows not meeting all conditions are excluded from period analysis.

**Period aggregation:** `compute_period_metrics()` uses `plmean_expr()` from `utils.py` for aggregation — regular `mean` for most columns, `scipy.stats.circmean` for columns in `COLS_360`. Always use `plmean_expr()` when aggregating angles.

**Traffic-light logic in `app.py`:**
```
diff = |actual - target|
diff ≤ tolerance        → GREEN  ("ON TGT")
diff ≤ 1.5 × tolerance  → ORANGE ("EDGE")
else                    → RED    ("OUT")
null value              → GREY   ("N/A")
```

**Presets:** Loaded from `presets.json` at startup, written back on save. Each preset contains separate `upwind` and `downwind` dicts keyed by internal metric name (e.g., `"cant"`, `"ride_height"`). The structure must match what `app.py` reads — check existing presets before adding new metrics.

## Git & Deployment Workflow

After every change: commit with a conventional prefix (`feat/fix/refactor/chore`) and push to `main`. The live Streamlit Cloud app redeploys automatically.

```bash
git add <files>
git commit -m "feat: description of what and why"
git push
```

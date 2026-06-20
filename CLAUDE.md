# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python -m streamlit run app.py
```

Credentials (`ORG_ID`, `TOKEN`, `URL`) are loaded from Streamlit Cloud secrets in production and from `.env` locally (see `config.py`). The `.env` file is gitignored — never commit it.

Deploy: push to `main` → Streamlit Cloud redeploys automatically.

## Architecture

### Data Pipeline

```
InfluxDB (data.sailgp.tech)
  → data_fetcher.py
      fetch_mark_positions()   # SL1 + SL2 GPS (level=mdss), averaged over window
      fetch_boat_gps()         # lat, lon, cog, sog, twa per boat (level=strm)
  → start_analysis.py
      detect_practice_starts() # T1 / T2 / Start crossing detection per boat
  → app.py                     # Streamlit UI — timing tables + GPS trail map
```

### Module responsibilities

| File | Role |
|---|---|
| `app.py` | Streamlit UI — sidebar (time window, boat select), timing tables per boat, Plotly map trail viewer |
| `data_fetcher.py` | InfluxDB queries for boat GPS and mark GPS; `ALL_BOATS` roster |
| `start_analysis.py` | Start line geometry, line-crossing detection, tack detection, practice start grouping |
| `config.py` | InfluxDB credentials (Streamlit secrets → `.env` fallback) |

### Key conventions

**Start line:** SL1 and SL2 marks are fetched with `level == "mdss"` and `boat == "SL1"` / `boat == "SL2"`. Boat data uses `level == "strm"`.

**GPS scaling:** `LATITUDE_GPS_unk` and `LONGITUDE_GPS_unk` are stored as integers × 10,000,000. Both `data_fetcher.py` functions divide by 10,000,000 before returning.

**Practice start sequence:**
- **T1** — boat crosses the *extended* start line on port tack (TWA < 0)
- **T2** — TWA sign flips negative→positive (tack/gybe back toward line)
- **Start** — boat crosses the *actual* line segment on starboard tack (TWA > 0)

Timings (T1, T2) are reported as seconds *before* the start crossing.

**GPS trail window:** T1 − 20 s → Start + 10 s, rendered on an OpenStreetMap base layer via Plotly Scattermapbox.

**Boat roster (`ALL_BOATS`):** NZL, AUS, GBR, FRA, DEN, ESP, SUI, CAN, USA, ITA, GER, BRA, SWE.

## Git & Deployment Workflow

```bash
git add <files>
git commit -m "feat: description of what and why"
git push
```

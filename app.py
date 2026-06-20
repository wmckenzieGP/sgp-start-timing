import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import APP_USERNAME, APP_PASSWORD
from data_fetcher import fetch_boat_gps, fetch_mark_positions, ALL_BOATS
from start_analysis import detect_practice_starts, summarise_starts, PracticeStart

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SailGP Start Timing",
    page_icon="⛵",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("SailGP — Start Timing")
    col, _ = st.columns([1, 2])
    with col:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if username == APP_USERNAME and password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    st.stop()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = {}
if "boat_dfs" not in st.session_state:
    st.session_state.boat_dfs = {}
if "marks" not in st.session_state:
    st.session_state.marks = {}
if "selected_ps" not in st.session_state:
    st.session_state.selected_ps = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Session Setup")

    default_start = datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0)
    default_end = default_start + timedelta(hours=3)

    start_date = st.date_input("Start date", value=default_start.date())
    start_time_input = st.time_input("Start time (UTC)", value=default_start.time())
    end_date = st.date_input("End date", value=default_end.date())
    end_time_input = st.time_input("End time (UTC)", value=default_end.time())

    start_dt = datetime.combine(start_date, start_time_input)
    end_dt = datetime.combine(end_date, end_time_input)

    st.divider()
    st.subheader("Start Line Marks")

    fetch_marks_btn = st.button("Auto-fetch mark GPS", use_container_width=True)
    if fetch_marks_btn:
        with st.spinner("Fetching SL1/SL2 from InfluxDB…"):
            fetched = fetch_mark_positions(start_dt, end_dt)
        if fetched:
            for k, (lat, lon) in fetched.items():
                st.session_state[f"_{k.lower()}_lat"] = lat
                st.session_state[f"_{k.lower()}_lon"] = lon
            st.success(f"Fetched: {', '.join(fetched.keys())}")
        else:
            st.warning("No mark GPS found in InfluxDB for this window. Enter coordinates manually.")

    sl1_lat = st.number_input("SL1 Latitude",  value=st.session_state.get("_sl1_lat", 0.0), format="%.6f")
    sl1_lon = st.number_input("SL1 Longitude", value=st.session_state.get("_sl1_lon", 0.0), format="%.6f")
    sl2_lat = st.number_input("SL2 Latitude",  value=st.session_state.get("_sl2_lat", 0.0), format="%.6f")
    sl2_lon = st.number_input("SL2 Longitude", value=st.session_state.get("_sl2_lon", 0.0), format="%.6f")

    marks_valid = not (sl1_lat == 0.0 and sl1_lon == 0.0 and sl2_lat == 0.0 and sl2_lon == 0.0)

    st.divider()
    selected_boats = st.multiselect(
        "Boats",
        options=ALL_BOATS,
        default=ALL_BOATS,
    )

    fetch_btn = st.button("Fetch & Analyse", type="primary", use_container_width=True)

    st.divider()
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------
st.title("SailGP — Start Timing Analysis")

# ---------------------------------------------------------------------------
# Fetch & analyse
# ---------------------------------------------------------------------------
if fetch_btn:
    if start_dt >= end_dt:
        st.error("Start time must be before end time.")
        st.stop()
    if not selected_boats:
        st.error("Select at least one boat.")
        st.stop()
    if not marks_valid:
        st.error("Enter SL1 and SL2 GPS coordinates before fetching.")
        st.stop()

    marks = {
        "SL1": (sl1_lat, sl1_lon),
        "SL2": (sl2_lat, sl2_lon),
    }
    st.session_state.marks = marks

    results = {}
    boat_dfs = {}

    progress = st.progress(0, text="Fetching boat data…")
    for i, boat in enumerate(selected_boats):
        progress.progress(i / len(selected_boats), text=f"Fetching {boat}…")
        df = fetch_boat_gps(boat, start_dt, end_dt)
        if df.empty:
            st.warning(f"No data returned for {boat} in this window.")
            continue
        boat_dfs[boat] = df
        starts = detect_practice_starts(df, marks["SL1"], marks["SL2"], boat)
        results[boat] = starts
        progress.progress(
            (i + 1) / len(selected_boats),
            text=f"Analysed {boat} — {len(starts)} start(s) found.",
        )

    progress.empty()
    st.session_state.results = results
    st.session_state.boat_dfs = boat_dfs
    st.session_state.selected_ps = None

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
results = st.session_state.results
boat_dfs = st.session_state.boat_dfs
marks = st.session_state.marks

if not results:
    st.info("Enter mark coordinates, select a time window, and press **Fetch & Analyse** to begin.")
    st.stop()

st.subheader("Practice Start Timings")

for boat, starts in results.items():
    with st.expander(f"🚤 {boat}", expanded=True):
        if not starts:
            st.write("No practice starts detected.")
            continue

        display_rows = []
        for ps in starts:
            display_rows.append({
                "Practice Start": f"PS {ps.number}",
                "Start Time (UTC)": ps.start_time.strftime("%H:%M:%S") if hasattr(ps.start_time, "strftime") else str(ps.start_time),
                "T2 (s before start)": f"{ps.t2_delta:.1f}" if ps.t2_delta is not None else "—",
                "T1 (s before start)": f"{ps.t1_delta:.1f}" if ps.t1_delta is not None else "—",
            })

        t2_vals = [ps.t2_delta for ps in starts if ps.t2_delta is not None]
        t1_vals = [ps.t1_delta for ps in starts if ps.t1_delta is not None]
        display_rows.append({
            "Practice Start": "Average",
            "Start Time (UTC)": "",
            "T2 (s before start)": f"{sum(t2_vals)/len(t2_vals):.1f}" if t2_vals else "—",
            "T1 (s before start)": f"{sum(t1_vals)/len(t1_vals):.1f}" if t1_vals else "—",
        })

        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

        ps_options = [f"PS {ps.number}" for ps in starts]
        selected_label = st.selectbox(
            "View GPS trail for:",
            options=["— select —"] + ps_options,
            key=f"sel_{boat}",
        )
        if selected_label != "— select —":
            ps_num = int(selected_label.split()[1])
            st.session_state.selected_ps = (boat, ps_num)

# ---------------------------------------------------------------------------
# GPS trail viewer
# ---------------------------------------------------------------------------
if st.session_state.selected_ps is not None:
    sel_boat, sel_num = st.session_state.selected_ps

    if sel_boat in st.session_state.results and sel_boat in boat_dfs:
        ps_list = st.session_state.results[sel_boat]
        ps = next((p for p in ps_list if p.number == sel_num), None)

        if ps is not None:
            st.divider()
            st.subheader(f"GPS Trail — {sel_boat} · PS {sel_num}")

            track_df = ps.track_window(boat_dfs[sel_boat])

            if track_df.empty:
                st.warning("No GPS data in the trail window.")
            else:
                sl1 = marks.get("SL1")
                sl2 = marks.get("SL2")

                fig = go.Figure()

                fig.add_trace(go.Scattermapbox(
                    lat=track_df["latitude"].tolist(),
                    lon=track_df["longitude"].tolist(),
                    mode="lines+markers",
                    marker=dict(size=6, color="deepskyblue"),
                    line=dict(width=2, color="deepskyblue"),
                    name=sel_boat,
                    hovertext=[
                        f"{row.timestamp.strftime('%H:%M:%S')}<br>SOG: {row.sog:.1f} km/h<br>TWA: {row.twa:.1f}°"
                        for row in track_df.itertuples()
                    ],
                    hoverinfo="text",
                ))

                if sl1 and sl2:
                    fig.add_trace(go.Scattermapbox(
                        lat=[sl1[0], sl2[0]],
                        lon=[sl1[1], sl2[1]],
                        mode="lines+markers",
                        marker=dict(size=12, color="red", symbol="circle"),
                        line=dict(width=3, color="red"),
                        name="Start Line",
                    ))

                def _nearest_row(df, t):
                    if t is None or df.empty:
                        return None
                    idx = (df["timestamp"] - t).abs().idxmin()
                    return df.loc[idx]

                def _add_event_marker(t, label, color):
                    row = _nearest_row(track_df, t)
                    if row is None:
                        return
                    fig.add_trace(go.Scattermapbox(
                        lat=[row["latitude"]],
                        lon=[row["longitude"]],
                        mode="markers+text",
                        marker=dict(size=16, color=color),
                        text=[label],
                        textposition="top right",
                        textfont=dict(size=13, color=color),
                        name=label,
                        hovertext=[f"{label}: {t}"],
                        hoverinfo="text",
                    ))

                _add_event_marker(ps.t1_time, "T1", "orange")
                _add_event_marker(ps.t2_time, "T2", "yellow")
                _add_event_marker(ps.start_time, "START", "lime")

                fig.update_layout(
                    mapbox=dict(
                        style="open-street-map",
                        center=dict(lat=track_df["latitude"].mean(), lon=track_df["longitude"].mean()),
                        zoom=14,
                    ),
                    margin=dict(l=0, r=0, t=0, b=0),
                    height=500,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )

                st.plotly_chart(fig, use_container_width=True)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("T1 before start", f"{ps.t1_delta:.1f} s" if ps.t1_delta else "—")
                with col2:
                    st.metric("T2 before start", f"{ps.t2_delta:.1f} s" if ps.t2_delta else "—")
                with col3:
                    val = (ps.t1_delta - ps.t2_delta) if (ps.t1_delta and ps.t2_delta) else None
                    st.metric("T2 → T1 gap", f"{val:.1f} s" if val else "—")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

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

st.title("SailGP — Start Timing Analysis")

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

    selected_boats = st.multiselect(
        "Boats",
        options=ALL_BOATS,
        default=ALL_BOATS,
    )

    fetch_btn = st.button("Fetch & Analyse", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = {}          # boat → list[PracticeStart]
if "boat_dfs" not in st.session_state:
    st.session_state.boat_dfs = {}         # boat → DataFrame (GPS track)
if "marks" not in st.session_state:
    st.session_state.marks = {}            # {"SL1": (lat,lon), "SL2": (lat,lon)}
if "selected_ps" not in st.session_state:
    st.session_state.selected_ps = None    # (boat, ps_number)

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

    with st.spinner("Fetching mark positions…"):
        marks = fetch_mark_positions(start_dt, end_dt)

    if "SL1" not in marks or "SL2" not in marks:
        st.warning(
            "Could not retrieve SL1/SL2 mark positions from InfluxDB. "
            "Check that mark data is available for the selected time window."
        )
        st.stop()

    st.session_state.marks = marks

    results = {}
    boat_dfs = {}

    progress = st.progress(0, text="Fetching boat data…")
    for i, boat in enumerate(selected_boats):
        progress.progress((i) / len(selected_boats), text=f"Fetching {boat}…")
        df = fetch_boat_gps(boat, start_dt, end_dt)
        if df.empty:
            st.warning(f"No data returned for {boat} in this window.")
            continue
        boat_dfs[boat] = df
        starts = detect_practice_starts(df, marks["SL1"], marks["SL2"], boat)
        results[boat] = starts
        progress.progress((i + 1) / len(selected_boats), text=f"Analysed {boat} — {len(starts)} start(s) found.")

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
    st.info("Configure a time window and press **Fetch & Analyse** to begin.")
    st.stop()

# ---- Timing tables --------------------------------------------------------

st.subheader("Practice Start Timings")
st.caption("Click a row to view the GPS trail for that practice start.")

for boat, starts in results.items():
    with st.expander(f"🚤 {boat}", expanded=True):
        if not starts:
            st.write("No practice starts detected.")
            continue

        summary_df = summarise_starts(starts)

        # Build display table with averages row
        display_rows = []
        for ps in starts:
            display_rows.append({
                "Practice Start": f"PS {ps.number}",
                "Start Time (UTC)": ps.start_time.strftime("%H:%M:%S") if hasattr(ps.start_time, "strftime") else str(ps.start_time),
                "T2 (s before start)": f"{ps.t2_delta:.1f}" if ps.t2_delta is not None else "—",
                "T1 (s before start)": f"{ps.t1_delta:.1f}" if ps.t1_delta is not None else "—",
            })

        # Average row
        t2_vals = [ps.t2_delta for ps in starts if ps.t2_delta is not None]
        t1_vals = [ps.t1_delta for ps in starts if ps.t1_delta is not None]
        display_rows.append({
            "Practice Start": "**Average**",
            "Start Time (UTC)": "",
            "T2 (s before start)": f"{sum(t2_vals)/len(t2_vals):.1f}" if t2_vals else "—",
            "T1 (s before start)": f"{sum(t1_vals)/len(t1_vals):.1f}" if t1_vals else "—",
        })

        table_df = pd.DataFrame(display_rows)
        st.dataframe(table_df, use_container_width=True, hide_index=True)

        # Row selector for trail viewer
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
                marks_data = st.session_state.marks
                sl1 = marks_data.get("SL1")
                sl2 = marks_data.get("SL2")

                fig = go.Figure()

                # Boat track
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

                # Start line
                if sl1 and sl2:
                    fig.add_trace(go.Scattermapbox(
                        lat=[sl1[0], sl2[0]],
                        lon=[sl1[1], sl2[1]],
                        mode="lines+markers",
                        marker=dict(size=12, color="red", symbol="circle"),
                        line=dict(width=3, color="red"),
                        name="Start Line",
                    ))

                # Event markers
                def _nearest_row(df: pd.DataFrame, t) -> pd.Series | None:
                    if t is None or df.empty:
                        return None
                    idx = (df["timestamp"] - t).abs().idxmin()
                    return df.loc[idx]

                def _add_event_marker(t, label: str, color: str):
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

                center_lat = track_df["latitude"].mean()
                center_lon = track_df["longitude"].mean()

                fig.update_layout(
                    mapbox=dict(
                        style="open-street-map",
                        center=dict(lat=center_lat, lon=center_lon),
                        zoom=14,
                    ),
                    margin=dict(l=0, r=0, t=0, b=0),
                    height=500,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )

                st.plotly_chart(fig, use_container_width=True)

                # Timing summary for this start
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("T1 before start", f"{ps.t1_delta:.1f} s" if ps.t1_delta else "—")
                with col2:
                    st.metric("T2 before start", f"{ps.t2_delta:.1f} s" if ps.t2_delta else "—")
                with col3:
                    st.metric("T2 → T1 gap", f"{(ps.t1_delta - ps.t2_delta):.1f} s" if (ps.t1_delta and ps.t2_delta) else "—")

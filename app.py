import streamlit as st
import polars as pl
import pandas as pd
from datetime import datetime, timedelta, time as datetime_time
import os
import json
import time as time_lib
import hashlib
from data_fetcher import SGPDataProvider
import utils as u
import sheets_client
from sheets_client import WING_OPTIONS

st.set_page_config(
    page_title="F50 Performance Dashboard",
    page_icon="assets/black_foils_logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main { background: #0b0f19 !important; color: #f1f5f9 !important; padding-top: 0.75rem; }
[data-testid="stSidebar"] {
    background: #0d1424 !important;
    border-right: 1px solid #1e2d45;
}
[data-testid="stSidebar"] > div:first-child { padding: 1rem 0.75rem; }

/* ── Sidebar typography ── */
.sidebar-section {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #64748b;
    margin: 1.2rem 0 0.4rem 0;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #1e2d45;
}
[data-testid="stSidebar"] label {
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] .stRadio > div { gap: 0.4rem; }
[data-testid="stSidebar"] .stRadio label { font-size: 0.85rem !important; color: #e2e8f0 !important; }
[data-testid="stSidebar"] .stSlider label { font-size: 0.82rem !important; }
[data-testid="stSidebar"] .stSelectbox label { font-size: 0.85rem !important; }
[data-testid="stSidebar"] .stCheckbox label { font-size: 0.85rem !important; color: #cbd5e1 !important; }
[data-testid="stSidebar"] p { font-size: 0.85rem !important; color: #94a3b8 !important; }

/* ── Page header ── */
.dash-title {
    font-size: 1.9rem;
    font-weight: 700;
    background: linear-gradient(90deg, #38bdf8 0%, #a855f7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
    margin: 0 0 0.25rem 0;
    line-height: 1.2;
}
.config-bar {
    font-size: 0.8rem;
    color: #64748b;
    margin-bottom: 1rem;
    letter-spacing: 0.2px;
}
.config-bar span { color: #94a3b8; font-weight: 500; }

/* ── Category headers ── */
.cat-header {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #475569;
    border-left: 3px solid #7c3aed;
    padding-left: 8px;
    margin: 1.25rem 0 0.6rem 0;
}

/* ── Metric cards ── */
.metric-card {
    background: #111827;
    border: 1px solid #1e2d45;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    min-height: 100px;
    transition: border-color 0.15s;
}
.metric-card:hover { border-color: #334155; }
.metric-left { flex: 1; min-width: 0; }
.metric-name {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f1f5f9;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.metric-tgt {
    font-size: 1.55rem;
    font-weight: 600;
    color: #cbd5e1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.metric-tol {
    font-size: 0.75rem;
    color: #475569;
    margin-top: 3px;
}
.metric-tgt b { color: #64748b; }

/* ── Value boxes ── */
.val-box {
    width: 105px;
    min-width: 105px;
    max-width: 105px;
    text-align: center;
    border-radius: 8px;
    padding: 8px 10px;
    flex-shrink: 0;
}
.val-num { font-size: 1.5rem; font-weight: 700; line-height: 1.15; }
.val-unit { font-size: 1.0rem; font-weight: 500; margin-left: 2px; }
.val-badge {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.8px;
    margin-top: 3px;
}

/* Green */
.val-green { background: linear-gradient(135deg,#052e16,#14532d); border: 1px solid #166534; }
.val-green .val-num, .val-green .val-unit { color: #4ade80; }
.val-green .val-badge { color: #86efac; }

/* Orange */
.val-orange { background: linear-gradient(135deg,#1c1007,#431407); border: 1px solid #9a3412; }
.val-orange .val-num, .val-orange .val-unit { color: #fb923c; }
.val-orange .val-badge { color: #fdba74; }

/* Red */
.val-red { background: linear-gradient(135deg,#1c0607,#450a0a); border: 1px solid #991b1b; }
.val-red .val-num, .val-red .val-unit { color: #f87171; }
.val-red .val-badge { color: #fca5a5; }

/* Grey (no data) */
.val-grey { background: #1e293b; border: 1px solid #334155; }
.val-grey .val-num, .val-grey .val-unit { color: #475569; }
.val-grey .val-badge { color: #334155; }

/* Blue (no target) */
.val-blue { background: linear-gradient(135deg,#0c1a2e,#0c2444); border: 1px solid #1e40af; }
.val-blue .val-num, .val-blue .val-unit { color: #60a5fa; }
.val-blue .val-badge { color: #93c5fd; }

/* ── Replay controls ── */
.replay-time {
    font-size: 0.8rem;
    color: #38bdf8;
    font-weight: 600;
    margin-top: 4px;
}

/* ── Misc ── */
div[data-testid="stNumberInput"] label { font-size: 0.78rem !important; color: #94a3b8 !important; }
.stButton > button {
    border-radius: 6px;
    font-weight: 600;
    font-size: 0.82rem;
}
hr { border-color: #1e2d45 !important; margin: 0.5rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────

TOLERANCES_FILE = 'tolerances.json'

DEFAULT_TOLERANCES = {
    "TWA": 2.0, "BSP": 2.0, "VMG": 0.0,
    "DRP": 0.5, "CANT": 1.0, "Ride Height": 50.0,
    "Rudder Avg": 0.5, "Camber": 1.0, "Wing Twist": 1.0,
    "Clew Position": 20.0, "Wing Rotation": 1.0,
    "Jib Track": 2.0, "Jib Sheet Load": 10.0, "Jib Cunno Load": 5.0,
}

# col: data column in periods dataframe
# unit: display unit string
# fmt: python format string
# type: "one_sided_high" | "symmetric" | "no_target"
# col_up/col_dw: direction-specific columns (used instead of col)
TARGETS_METADATA = {
    "TWS":            {"col": "tws_mean",                  "unit": "kph", "fmt": "{:.1f}", "type": "no_target"},
    "TWA":            {"col": "twa_n_mean",                "unit": "°",   "fmt": "{:.1f}", "type": "twa_direction"},
    "BSP":            {"col": "bsp_mean",                  "unit": "kph", "fmt": "{:.1f}", "type": "one_sided_high"},
    "VMG":            {"col": "vmg_mean",                  "unit": "kph", "fmt": "{:.1f}", "type": "no_target"},
    # DRP reads from the full raw df (not periods) so it captures tack/gybe drop events
    "DRP":            {"raw_col_up": "target_db_cant_drop_upw",
                       "raw_col_dw": "target_db_cant_drop_dw",
                       "use_raw": True,
                                                           "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "CANT":           {"col": "leeward_cant_mean",         "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Ride Height":    {"col": "foil_leeward_sink_mean",    "unit": "mm",  "fmt": "{:.0f}", "type": "symmetric"},
    "Rudder Avg":     {"col": "rudder_avg_mean",            "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Camber":         {"col": "cam1_angle_abs_mean",        "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Wing Twist":     {"col": "wing_twist_n_mean",         "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Clew Position":  {"col": "wing_clew_mean",            "unit": "mm",  "fmt": "{:.0f}", "type": "symmetric", "target_scale": 100},
    "Wing Rotation":  {"col": "wing_rotation_n_mean",      "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Jib Track":      {"col": "jib_sheet_angle_mean",      "unit": "°",   "fmt": "{:.1f}", "type": "symmetric"},
    "Jib Sheet Load": {"col": "jib_sheet_load_mean",       "unit": "kgf", "fmt": "{:.0f}", "type": "symmetric", "scale": 0.01},
    "Jib Cunno Load": {"col": "jib_cunningham_load_mean",  "unit": "kgf", "fmt": "{:.0f}", "type": "symmetric"},
}

DASHBOARD_CATEGORIES = [
    ("Global Performance",      ["TWS", "TWA", "BSP", "VMG"],                    4),
    ("Foil",                    ["DRP", "CANT", "Ride Height", "Rudder Avg"],     4),
    ("Wing",                    ["Camber", "Wing Twist", "Clew Position", "Wing Rotation"], 4),
    ("Jib",                     ["Jib Track", "Jib Sheet Load", "Jib Cunno Load"], 3),
]

# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def get_col(name, upwind, raw=False):
    m = TARGETS_METADATA[name]
    if raw and "raw_col_up" in m:
        return m["raw_col_up"] if upwind else m["raw_col_dw"]
    if "col_up" in m:
        return m["col_up"] if upwind else m["col_dw"]
    return m.get("col")


def get_status_color(value, target, tolerance, metric_type="symmetric"):
    """
    Returns (css_class, badge_text).

    metric_type:
      "one_sided_high"  — actual >= target = green (BSP)
      "one_sided_low"   — actual <= target = green (TWA upwind: less angle is better)
      "symmetric"       — ±tolerance bands
      "no_target"       — blue, always shows actual value
    Note: "twa_direction" is resolved to one_sided_low/high before reaching here.
    """
    if metric_type == "no_target":
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "grey", "N/A"
        return "blue", "LIVE"

    if target is None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "grey", "N/A"
        return "blue", "NO TGT"

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "grey", "N/A"

    tol = max(tolerance, 0.001)

    if metric_type == "one_sided_high":
        if value >= target:
            return "green", "ON TGT"
        diff = target - value
        return ("orange", "EDGE") if diff <= tol else ("red", "OUT")

    if metric_type == "one_sided_low":
        if value <= target:
            return "green", "ON TGT"
        diff = value - target
        return ("orange", "EDGE") if diff <= tol else ("red", "OUT")

    # Symmetric ±tolerance
    diff = abs(value - target)
    if diff <= tol:
        return "green", "ON TGT"
    return ("orange", "EDGE") if diff <= 1.5 * tol else ("red", "OUT")


def render_card(name, value, target, tolerance, upwind_mode=True):
    m = TARGETS_METADATA[name]
    unit = m["unit"]
    fmt = m["fmt"]
    mtype = m["type"]

    # TWA: upwind = less angle is better (one_sided_low)
    #       downwind = more angle is better (one_sided_high)
    if mtype == "twa_direction":
        mtype = "one_sided_low" if upwind_mode else "one_sided_high"

    css, badge = get_status_color(value, target, tolerance, mtype)

    if value is not None and not (isinstance(value, float) and pd.isna(value)):
        val_str = f'<span class="val-num">{fmt.format(value)}</span><span class="val-unit">{unit}</span>'
    else:
        val_str = '<span class="val-num">N/A</span>'

    if target is not None and mtype != "no_target":
        tgt_str = f"{fmt.format(target)} {unit}"
        tol_str = f"<div class='metric-tol'>± {fmt.format(tolerance)}</div>"
    elif mtype == "no_target":
        tgt_str = "LIVE"
        tol_str = ""
    else:
        tgt_str = "NO TGT"
        tol_str = ""

    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-left">
        <div class="metric-name">{name}</div>
        <div class="metric-tgt">{tgt_str}</div>
        {tol_str}
      </div>
      <div class="val-box val-{css}">
        <div>{val_str}</div>
        <div class="val-badge">{badge}</div>
      </div>
    </div>""", unsafe_allow_html=True)


def load_tolerances():
    try:
        if os.path.exists(TOLERANCES_FILE):
            with open(TOLERANCES_FILE) as f:
                saved = json.load(f)
            # Fill in any missing keys from defaults
            return {k: saved.get(k, DEFAULT_TOLERANCES[k]) for k in DEFAULT_TOLERANCES}
    except Exception:
        pass
    return dict(DEFAULT_TOLERANCES)


def save_tolerances(tols):
    try:
        with open(TOLERANCES_FILE, "w") as f:
            json.dump(tols, f, indent=2)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────

def check_password():
    def _entered():
        u_env = os.getenv("APP_USERNAME")
        p_env = os.getenv("APP_PASSWORD")
        if not u_env or not p_env:
            st.session_state["password_correct"] = False
            st.session_state["credentials_missing"] = True
            return
        st.session_state["credentials_missing"] = False
        ph = hashlib.sha256(st.session_state["password"].encode()).hexdigest()
        if st.session_state["username"] == u_env and ph == hashlib.sha256(p_env.encode()).hexdigest():
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False
            st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1

    def _show_login(error_msg=None):
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col, _ = st.columns([1, 1, 1])
        with col:
            st.image("assets/black_foils_logo.png", use_container_width=True)
            st.markdown("<h2 style='text-align:center;color:#fff;margin:1.5rem 0;'>Login</h2>", unsafe_allow_html=True)
            if error_msg:
                st.error(error_msg)
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("Login", on_click=_entered, use_container_width=True, type="primary")

    if "password_correct" not in st.session_state:
        _show_login()
        return False
    if not st.session_state["password_correct"]:
        if st.session_state.get("credentials_missing"):
            _show_login("Server configuration error: credentials not set.")
        elif st.session_state.get("login_attempts", 0) >= 3:
            _show_login(f"Too many failed attempts ({st.session_state['login_attempts']}).")
        else:
            _show_login("Invalid username or password.")
        return False
    return True


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main():
    if 'session_start' not in st.session_state:
        st.session_state['session_start'] = time_lib.time()

    tolerances = load_tolerances()

    # ── SIDEBAR ──────────────────────────────────────────
    with st.sidebar:
        st.image("assets/black_foils_logo.png", use_container_width=True)

        # Configuration
        st.markdown('<div class="sidebar-section">Configuration</div>', unsafe_allow_html=True)
        foils = st.radio("Foils", ["HSB2", "LAB2"], horizontal=True, key="foils")
        wing_opts = WING_OPTIONS[foils]
        # Keep previous wing choice if still valid
        prev_wing = st.session_state.get("_prev_wing", wing_opts[0])
        default_wing = prev_wing if prev_wing in wing_opts else wing_opts[0]
        wing = st.radio("Wing", wing_opts, horizontal=True,
                        index=wing_opts.index(default_wing), key="wing")
        st.session_state["_prev_wing"] = wing
        rudders = st.radio("Rudders", ["LARW", "HSRW"], horizontal=True, key="rudders")
        jib = st.radio("Jib", ["Big", "Small"], horizontal=True, key="jib")

        # Data mode
        st.markdown('<div class="sidebar-section">Data Mode</div>', unsafe_allow_html=True)
        data_mode = st.radio("Mode", ["Live", "Replay"], horizontal=True, key="data_mode")

        is_live = (data_mode == "Live")

        if is_live:
            rolling_window = st.slider("Window (minutes)", 1, 60, 5, key="rolling_window")
            auto_refresh = st.checkbox("Auto-refresh", value=True, key="auto_refresh")
            refresh_rate = st.slider("Refresh rate (seconds)", 5, 60, 10, key="refresh_rate")
        else:
            st.markdown('<p style="margin:0 0 4px 0;">Start date & time (UTC)</p>', unsafe_allow_html=True)
            replay_date = st.date_input("Date", value=datetime(2026, 1, 17), key="replay_date", label_visibility="collapsed")
            replay_time_str = st.text_input("Time (HH:MM:SS)", value="04:15:00", key="replay_time_str")
            rolling_window = st.slider("Window (minutes)", 1, 60, 5, key="replay_window")
            auto_refresh = False

            try:
                t = datetime.strptime(replay_time_str.strip(), "%H:%M:%S").time()
            except ValueError:
                try:
                    t = datetime.strptime(replay_time_str.strip(), "%H:%M").time()
                except ValueError:
                    t = datetime_time(4, 15, 0)
            replay_start_dt = datetime.combine(replay_date, t)

            col_play, col_pause = st.columns(2)
            with col_play:
                play_pressed = st.button("▶ Play", use_container_width=True, type="primary")
            with col_pause:
                pause_pressed = st.button("⏸ Pause", use_container_width=True)

            if play_pressed:
                st.session_state['replay_start_dt'] = replay_start_dt
                st.session_state['replay_playing'] = True
                st.session_state['replay_play_wall'] = time_lib.time()
                st.session_state['replay_elapsed_frozen'] = 0.0
                st.session_state.pop('replay_raw_df', None)
                st.session_state.pop('replay_periods', None)

            if pause_pressed:
                if st.session_state.get('replay_playing'):
                    elapsed = time_lib.time() - st.session_state.get('replay_play_wall', time_lib.time())
                    st.session_state['replay_elapsed_frozen'] = st.session_state.get('replay_elapsed_frozen', 0) + elapsed
                    st.session_state['replay_play_wall'] = time_lib.time()
                st.session_state['replay_playing'] = False

        # Sailing Parameters
        st.markdown('<div class="sidebar-section">Sailing</div>', unsafe_allow_html=True)
        boat = st.selectbox("Boat", ["NZL","SWE","BRA","SUI","CAN","DEN","GBR","ITA","FRA","USA","AUS","ESP","GER"],
                            index=0, key="boat")
        direction = st.radio("Direction", ["Upwind", "Downwind"], horizontal=True, key="direction")
        upwind_mode = (direction == "Upwind")
        period_duration = st.slider("Period duration (s)", 2, 20, 6, key="period_duration")
        min_bsp = st.slider("Min BSP threshold", 0, 100, 30, key="min_bsp")

        # Tolerances
        st.markdown('<div class="sidebar-section">Tolerances</div>', unsafe_allow_html=True)
        with st.expander("Edit tolerances", expanded=False):
            changed = False
            for metric in TARGETS_METADATA:
                if TARGETS_METADATA[metric]["type"] == "no_target":
                    continue
                new_val = st.number_input(
                    metric, value=float(tolerances.get(metric, DEFAULT_TOLERANCES.get(metric, 1.0))),
                    min_value=0.0, step=0.1, format="%.1f",
                    key=f"tol_{metric}"
                )
                if new_val != tolerances.get(metric):
                    tolerances[metric] = new_val
                    changed = True
            if changed:
                save_tolerances(tolerances)

        # Logout
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
            st.session_state["password_correct"] = False
            st.rerun()

    # ── STABLE HEADER (outside fragment so it never flickers) ──
    config_parts = [foils, f"{wing} Wing", f"{rudders} Rudders", f"{jib} Jib"]
    st.markdown('<div class="dash-title">F50 Performance Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="config-bar"><span>{" · ".join(config_parts)}</span>'
        f' &nbsp;|&nbsp; {direction}</div>',
        unsafe_allow_html=True
    )

    # ── LIVE DASHBOARD FRAGMENT ───────────────────────────
    # Each condition produces a *different* decorated function so Streamlit
    # sees a new fragment (and resets the timer) when auto_refresh or
    # refresh_rate changes — fixing both the slider and the on/off toggle.
    def _dashboard():
        periods_df = pl.DataFrame()
        data_label = ""

        raw_df = pl.DataFrame()  # full processed df — used for DRP and other raw metrics

        if is_live:
            end_dt = datetime.utcnow()
            start_dt = end_dt - timedelta(minutes=rolling_window)
            data_label = f"Live — last {rolling_window} min"
            try:
                fetcher = SGPDataProvider(boat=boat)
                raw = fetcher.get_data(
                    start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                )
                if raw.height > 0:
                    fetcher.process_data(raw, period_duration=period_duration,
                                         min_speed_upwind=min_bsp, min_speed_downwind=min_bsp)
                    periods_df = fetcher.periods if fetcher.periods is not None else pl.DataFrame()
                    raw_df = fetcher.df if fetcher.df is not None else pl.DataFrame()
            except Exception as e:
                st.error(f"Live data error: {e}")

        else:
            # Replay mode
            start_dt_key = st.session_state.get('replay_start_dt')
            playing = st.session_state.get('replay_playing', False)

            if start_dt_key is None:
                st.info("Select a date and time in the sidebar, then press ▶ Play.")
                return

            # Advance virtual clock
            if playing:
                wall_elapsed = time_lib.time() - st.session_state.get('replay_play_wall', time_lib.time())
                total_elapsed = st.session_state.get('replay_elapsed_frozen', 0.0) + wall_elapsed
            else:
                total_elapsed = st.session_state.get('replay_elapsed_frozen', 0.0)

            virtual_now = start_dt_key + timedelta(seconds=total_elapsed)
            virtual_start = virtual_now - timedelta(minutes=rolling_window)
            data_label = f"Replay — {virtual_now.strftime('%H:%M:%S')} UTC"

            # Load 2-hour block once and cache in session state
            fetch_hash = (start_dt_key.isoformat(), boat, period_duration, min_bsp)
            if st.session_state.get('replay_fetch_hash') != fetch_hash or 'replay_periods' not in st.session_state:
                with st.spinner(f"Loading replay data from {start_dt_key.strftime('%H:%M')} UTC…"):
                    try:
                        end_fetch = start_dt_key + timedelta(hours=2)
                        fetcher = SGPDataProvider(boat=boat)
                        raw = fetcher.get_data(
                            start_dt_key.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            end_fetch.strftime("%Y-%m-%dT%H:%M:%SZ")
                        )
                        if raw.height > 0:
                            fetcher.process_data(raw, period_duration=period_duration,
                                                  min_speed_upwind=min_bsp, min_speed_downwind=min_bsp)
                            st.session_state['replay_periods'] = fetcher.periods if fetcher.periods is not None else pl.DataFrame()
                            st.session_state['replay_processed_df'] = fetcher.df if fetcher.df is not None else pl.DataFrame()
                        else:
                            st.session_state['replay_periods'] = pl.DataFrame()
                            st.session_state['replay_processed_df'] = pl.DataFrame()
                        st.session_state['replay_fetch_hash'] = fetch_hash
                    except Exception as e:
                        st.error(f"Replay data error: {e}")
                        st.session_state['replay_periods'] = pl.DataFrame()

            # Slice periods to the current virtual window
            all_periods = st.session_state.get('replay_periods', pl.DataFrame())
            if not all_periods.is_empty() and 'timestamp' in all_periods.columns:
                periods_df = all_periods.filter(
                    (pl.col("timestamp") >= virtual_start) &
                    (pl.col("timestamp") <= virtual_now)
                )

            # Slice full processed df to the current virtual window (used for DRP)
            all_raw = st.session_state.get('replay_processed_df', pl.DataFrame())
            if not all_raw.is_empty() and 'timestamp' in all_raw.columns:
                raw_df = all_raw.filter(
                    (pl.col("timestamp") >= virtual_start) &
                    (pl.col("timestamp") <= virtual_now)
                )

            status_icon = "🔴" if playing else "⏸"
            st.markdown(
                f'<div class="replay-time">{status_icon} {virtual_now.strftime("%Y-%m-%d %H:%M:%S")} UTC'
                f' &nbsp;|&nbsp; Window: {rolling_window} min</div>',
                unsafe_allow_html=True
            )

        # ── FILTER ──────────────────────────────────────────
        filtered = pl.DataFrame()
        if not periods_df.is_empty():
            dir_col = "upwind" if upwind_mode else "downwind"
            if dir_col in periods_df.columns:
                filtered = periods_df.filter(
                    pl.col(dir_col) & (pl.col("bsp_mean") >= min_bsp)
                )

        # ── SHEET TARGETS ────────────────────────────────────
        mean_tws = filtered["tws_mean"].mean() if (not filtered.is_empty() and "tws_mean" in filtered.columns) else None
        sheet_targets = sheets_client.get_cheatsheet_targets(
            foils, wing, rudders, jib, upwind_mode, mean_tws or 20.0
        )
        matched_tws = sheet_targets.pop('_matched_tws', None)
        active_targets = {}
        for m, meta in TARGETS_METADATA.items():
            val = sheet_targets.get(m)
            if val is not None and "target_scale" in meta:
                val = val * meta["target_scale"]
            active_targets[m] = val

        # ── ACTUALS ─────────────────────────────────────────
        actuals = {}
        for name, meta in TARGETS_METADATA.items():
            if meta.get("use_raw"):
                # Read from the full raw time-series (not straight-line periods)
                col = get_col(name, upwind_mode, raw=True)
                src = raw_df
            else:
                col = get_col(name, upwind_mode)
                src = filtered

            val = (src[col].mean()
                   if col and not src.is_empty() and col in src.columns
                   else None)
            if val is not None and "scale" in meta:
                val = val * meta["scale"]
            actuals[name] = val

        # ── SUB-HEADER (TWS row + stats) ─────────────────────
        n_periods = len(filtered) if not filtered.is_empty() else 0
        tws_info = f"TWS row {matched_tws}" if matched_tws is not None else "No TWS match"
        st.markdown(
            f'<div class="config-bar">'
            f'{tws_info} &nbsp;|&nbsp; {n_periods} periods &nbsp;|&nbsp; {data_label}'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── METRIC GRID ──────────────────────────────────────
        for cat_name, metrics, n_cols in DASHBOARD_CATEGORIES:
            st.markdown(f'<div class="cat-header">{cat_name}</div>', unsafe_allow_html=True)
            cols = st.columns(n_cols)
            for i, name in enumerate(metrics):
                with cols[i % n_cols]:
                    render_card(
                        name=name,
                        value=actuals.get(name),
                        target=active_targets.get(name),
                        tolerance=tolerances.get(name, DEFAULT_TOLERANCES.get(name, 1.0)),
                        upwind_mode=upwind_mode
                    )

        # ── RAW DATA EXPANDER ────────────────────────────────
        with st.expander("Raw period data", expanded=False):
            if not filtered.is_empty():
                st.dataframe(filtered.to_pandas(), use_container_width=True)
            else:
                st.caption("No period data available.")

    # Apply the correct fragment decorator based on current auto-refresh state.
    # Using a fresh st.fragment() call each time means the run_every timer
    # is always in sync with the slider and the auto-refresh checkbox.
    replay_playing = data_mode == "Replay" and st.session_state.get('replay_playing', False)
    if is_live and auto_refresh:
        st.fragment(run_every=refresh_rate)(_dashboard)()
    elif replay_playing:
        st.fragment(run_every=5)(_dashboard)()
    else:
        st.fragment(_dashboard)()


if __name__ == "__main__" or True:
    if check_password():
        main()

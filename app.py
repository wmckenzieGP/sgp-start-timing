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

# Set page configuration
st.set_page_config(
    page_title="F50 Performance Comparison Dashboard",
    page_icon="assets/black_foils_logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS styling
st.markdown("""
    <style>
    /* Dark premium layout background */
    .main {
        background-color: #0b0f19 !important;
        color: #f1f5f9 !important;
        padding-top: 1rem;
    }
    
    /* Clean sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid #1e293b;
    }
    
    /* Typography */
    h1 {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 700;
        font-size: 2.2rem;
        background: linear-gradient(90deg, #38bdf8 0%, #a855f7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }
    
    .category-header {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-size: 1.25rem;
        font-weight: 600;
        color: #f8fafc;
        border-left: 4px solid #8b5cf6;
        padding-left: 10px;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        letter-spacing: 0.2px;
    }
    
    /* Target Comparison Card */
    .target-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: all 0.2s ease-in-out;
    }
    
    .target-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.3);
        border-color: #475569;
    }
    
    .target-info {
        flex: 1;
    }
    
    .target-name {
        font-size: 0.95rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .target-bounds {
        margin-top: 6px;
        font-size: 0.75rem;
        color: #cbd5e1;
        line-height: 1.4;
    }
    
    .bound-row {
        display: flex;
        justify-content: space-between;
        width: 130px;
    }
    
    .bound-label {
        color: #64748b;
    }
    
    .bound-val {
        font-weight: 500;
        color: #cbd5e1;
    }
    
    .value-box {
        color: #ffffff;
        font-weight: 700;
        font-size: 1.5rem;
        padding: 8px 12px;
        border-radius: 8px;
        min-width: 95px;
        text-align: center;
        box-shadow: inset 0 2px 4px 0 rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    
    .value-box.green {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        border: 1px solid #34d399;
    }
    
    .value-box.orange {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        border: 1px solid #fbbf24;
    }
    
    .value-box.red {
        background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
        border: 1px solid #f87171;
    }
    
    .value-box.grey {
        background: linear-gradient(135deg, #475569 0%, #334155 100%);
        border: 1px solid #64748b;
    }
    
    .status-badge {
        font-size: 0.6rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        opacity: 0.95;
        margin-top: 2px;
    }
    
    /* Form inputs styling */
    input[type="text"],
    input[type="number"],
    select,
    .stTextInput input,
    .stNumberInput input,
    .stSelectbox select,
    .stMultiSelect select {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
    }
    
    /* Data editor override for visibility */
    .stDataFrame {
        border-radius: 8px;
        border: 1px solid #334155;
    }
    </style>
""", unsafe_allow_html=True)

# Presets Management System
PRESETS_FILE = "presets.json"

DEFAULT_PRESETS = {
    "TWS 10-15 kts": {
        "upwind": {
            "BSP": {"target": 35.0, "tolerance": 2.0},
            "TWA": {"target": 45.0, "tolerance": 3.0},
            "VMG": {"target": 25.0, "tolerance": 2.0},
            "CANT": {"target": 4.0, "tolerance": 1.0},
            "CANT Drop Target": {"target": 1.5, "tolerance": 0.5},
            "Ride Height": {"target": 250.0, "tolerance": 50.0},
            "Rudder Average": {"target": 0.0, "tolerance": 1.0},
            "Rudder Differential": {"target": 1.5, "tolerance": 0.5},
            "Camber (CA1)": {"target": 12.0, "tolerance": 2.0},
            "Wing Twist": {"target": 8.0, "tolerance": 1.5},
            "Clew Position": {"target": 850.0, "tolerance": 50.0},
            "Wing Rotation": {"target": 22.0, "tolerance": 2.0},
            "Heel": {"target": 3.0, "tolerance": 1.0},
            "Pitch": {"target": 0.5, "tolerance": 0.3}
        },
        "downwind": {
            "BSP": {"target": 45.0, "tolerance": 3.0},
            "TWA": {"target": 140.0, "tolerance": 5.0},
            "VMG": {"target": 35.0, "tolerance": 3.0},
            "CANT": {"target": 6.0, "tolerance": 1.0},
            "CANT Drop Target": {"target": 2.0, "tolerance": 0.5},
            "Ride Height": {"target": 350.0, "tolerance": 50.0},
            "Rudder Average": {"target": 0.0, "tolerance": 1.0},
            "Rudder Differential": {"target": 2.0, "tolerance": 0.5},
            "Camber (CA1)": {"target": 15.0, "tolerance": 2.0},
            "Wing Twist": {"target": 12.0, "tolerance": 2.0},
            "Clew Position": {"target": 750.0, "tolerance": 50.0},
            "Wing Rotation": {"target": 26.0, "tolerance": 2.0},
            "Heel": {"target": 4.0, "tolerance": 1.0},
            "Pitch": {"target": 1.0, "tolerance": 0.3}
        }
    },
    "Auckland Day 1": {
        "upwind": {
            "BSP": {"target": 36.5, "tolerance": 1.5},
            "TWA": {"target": 46.5, "tolerance": 2.0},
            "VMG": {"target": 26.0, "tolerance": 1.5},
            "CANT": {"target": 4.2, "tolerance": 0.8},
            "CANT Drop Target": {"target": 1.4, "tolerance": 0.4},
            "Ride Height": {"target": 230.0, "tolerance": 40.0},
            "Rudder Average": {"target": 0.2, "tolerance": 0.8},
            "Rudder Differential": {"target": 1.6, "tolerance": 0.4},
            "Camber (CA1)": {"target": 12.5, "tolerance": 1.5},
            "Wing Twist": {"target": 8.5, "tolerance": 1.0},
            "Clew Position": {"target": 830.0, "tolerance": 40.0},
            "Wing Rotation": {"target": 21.5, "tolerance": 1.5},
            "Heel": {"target": 3.2, "tolerance": 0.8},
            "Pitch": {"target": 0.4, "tolerance": 0.2}
        },
        "downwind": {
            "BSP": {"target": 47.0, "tolerance": 2.5},
            "TWA": {"target": 137.5, "tolerance": 4.0},
            "VMG": {"target": 37.0, "tolerance": 2.5},
            "CANT": {"target": 5.8, "tolerance": 0.8},
            "CANT Drop Target": {"target": 1.8, "tolerance": 0.4},
            "Ride Height": {"target": 320.0, "tolerance": 40.0},
            "Rudder Average": {"target": 0.1, "tolerance": 0.8},
            "Rudder Differential": {"target": 1.8, "tolerance": 0.4},
            "Camber (CA1)": {"target": 14.5, "tolerance": 1.5},
            "Wing Twist": {"target": 11.5, "tolerance": 1.5},
            "Clew Position": {"target": 780.0, "tolerance": 40.0},
            "Wing Rotation": {"target": 25.0, "tolerance": 1.5},
            "Heel": {"target": 3.8, "tolerance": 0.8},
            "Pitch": {"target": 0.9, "tolerance": 0.2}
        }
    }
}

def load_presets():
    if not os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, "w") as f:
                json.dump(DEFAULT_PRESETS, f, indent=4)
            return DEFAULT_PRESETS
        except:
            return DEFAULT_PRESETS
    try:
        with open(PRESETS_FILE, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_PRESETS

def save_presets(presets):
    try:
        with open(PRESETS_FILE, "w") as f:
            json.dump(presets, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Error saving presets: {e}")
        return False

# Target definition mapping in Polars periods dataframe
TARGETS_METADATA = {
    "BSP": {"col": "bsp_mean", "unit": "kts", "format": "{:.1f}"},
    "TWA": {"col": "twa_n_mean", "unit": "°", "format": "{:.1f}"},
    "VMG": {"col": "vmg_mean", "unit": "kts", "format": "{:.1f}"},
    "CANT": {"col": "leeward_cant_mean", "unit": "°", "format": "{:.1f}"},
    "CANT Drop Target": {"col": "target_db_cant_drop_mean", "unit": "°", "format": "{:.1f}"}, # Dynamic mapping
    "Ride Height": {"col": "foil_leeward_sink_mean", "unit": "mm", "format": "{:.0f}"},
    "Rudder Average": {"col": "rudder_angle_n_mean", "unit": "°", "format": "{:.1f}"},
    "Rudder Differential": {"col": "rudder_diff_tack_mean", "unit": "°", "format": "{:.1f}"},
    "Camber (CA1)": {"col": "cam1_angle_n_mean", "unit": "°", "format": "{:.1f}"},
    "Wing Twist": {"col": "wing_twist_n_mean", "unit": "°", "format": "{:.1f}"},
    "Clew Position": {"col": "wing_clew_mean", "unit": "mm", "format": "{:.0f}"},
    "Wing Rotation": {"col": "wing_rotation_n_mean", "unit": "°", "format": "{:.1f}"},
    "Heel": {"col": "heel_n_mean", "unit": "°", "format": "{:.1f}"},
    "Pitch": {"col": "trim_mean", "unit": "°", "format": "{:.1f}"}
}

def get_column_for_target(target_name, upwind):
    if target_name == "CANT Drop Target":
        return "target_db_cant_drop_upw_mean" if upwind else "target_db_cant_drop_dw_mean"
    return TARGETS_METADATA[target_name]["col"]

def get_status_color(value, target, tolerance):
    if value is None or pd.isna(value):
        return "grey", "N/A"
    diff = abs(value - target)
    if tolerance <= 0:
        return "green" if diff <= 0.05 else "red", "ON TGT" if diff <= 0.05 else "OUT"
    if diff <= tolerance:
        return "green", "ON TGT"
    elif diff <= 1.5 * tolerance:
        return "orange", "EDGE"
    else:
        return "red", "OUT"

def render_target_card(name, value, target, tolerance, unit_str, format_str, source=None):
    color, status_text = get_status_color(value, target, tolerance)

    if value is not None and not pd.isna(value):
        val_display = format_str.format(value) + " " + unit_str
    else:
        val_display = "N/A"

    upper_bound = target + tolerance
    lower_bound = target - tolerance

    tgt_display = format_str.format(target) + " " + unit_str
    upper_display = format_str.format(upper_bound) + " " + unit_str
    lower_display = format_str.format(lower_bound) + " " + unit_str

    source_badge = (
        f'<span style="font-size:0.6rem;color:#38bdf8;font-weight:500;'
        f'letter-spacing:0.3px;margin-left:6px;">&#9654; {source}</span>'
        if source else ""
    )

    html = f"""
    <div class="target-card">
        <div class="target-info">
            <div class="target-name">{name}{source_badge}</div>
            <div class="target-bounds">
                <div class="bound-row">
                    <span class="bound-label">Target:</span>
                    <span class="bound-val">{tgt_display}</span>
                </div>
                <div class="bound-row">
                    <span class="bound-label">Upper:</span>
                    <span class="bound-val">{upper_display}</span>
                </div>
                <div class="bound-row">
                    <span class="bound-label">Lower:</span>
                    <span class="bound-val">{lower_display}</span>
                </div>
            </div>
        </div>
        <div class="value-box {color}">
            <div style="font-size: 1.15rem; font-weight: 700;">{val_display}</div>
            <div class="status-badge">{status_text}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# Login System
def check_password():
    """Returns `True` if the user has entered the correct password."""
    def password_entered():
        correct_username = os.getenv("APP_USERNAME")
        correct_password = os.getenv("APP_PASSWORD")
        
        if not correct_username or not correct_password:
            st.session_state["password_correct"] = False
            st.session_state["credentials_missing"] = True
            return
        
        st.session_state["credentials_missing"] = False
        entered_password_hash = hashlib.sha256(st.session_state["password"].encode()).hexdigest()
        correct_password_hash = hashlib.sha256(correct_password.encode()).hexdigest()
        
        if (st.session_state["username"] == correct_username and 
            entered_password_hash == correct_password_hash):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False
            st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1

    if "password_correct" not in st.session_state:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image("assets/black_foils_logo.png", use_container_width=True)
            st.markdown("<h2 style='text-align: center; margin: 2rem 0 1.5rem 0; color:#fff;'>Login</h2>", unsafe_allow_html=True)
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("Login", on_click=password_entered, use_container_width=True, type="primary")
        return False
    
    elif not st.session_state["password_correct"]:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image("assets/black_foils_logo.png", use_container_width=True)
            st.markdown("<h2 style='text-align: center; margin: 2rem 0 1.5rem 0; color:#fff;'>Login</h2>", unsafe_allow_html=True)
            if st.session_state.get("credentials_missing"):
                st.error("⚠️ Server configuration error: Login credentials not set. Please contact administrator.")
            else:
                attempts = st.session_state.get("login_attempts", 0)
                if attempts >= 3:
                    st.error(f"❌ Invalid username or password. Too many failed attempts ({attempts}).")
                else:
                    st.error("❌ Invalid username or password. Please try again.")
            
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("Login", on_click=password_entered, use_container_width=True, type="primary")
        return False
    
    return True

# Main Dashboard Function
def main():
    # Setup session times
    if 'session_start_time' not in st.session_state:
        st.session_state['session_start_time'] = time_lib.time()

    # Load presets
    presets = load_presets()

    # Sidebar Controls
    with st.sidebar:
        st.image("assets/black_foils_logo.png", use_container_width=True)
        st.title("Settings")
        
        # 1. Preset Parameters Selector
        st.subheader("Target Presets")
        preset_names = list(presets.keys())
        active_preset_name = st.selectbox("Active Preset", options=preset_names, index=0)
        
        # Keep track of active preset
        if 'active_preset_name' not in st.session_state or st.session_state['active_preset_name'] != active_preset_name:
            st.session_state['active_preset_name'] = active_preset_name
            # Sync parameters to temporary session state for editing
            st.session_state['current_parameters'] = presets[active_preset_name]

        # 2. Data Mode selector
        st.subheader("Data Extraction Mode")
        data_mode = st.radio("Extraction Mode", ["Live / Rolling Window", "Historical Range"], horizontal=True)
        
        # Mode options
        is_live = (data_mode == "Live / Rolling Window")
        
        if is_live:
            rolling_window = st.slider("Rolling Window (minutes)", min_value=1, max_value=60, value=5)
            refresh_rate = st.slider("Refresh Rate (seconds)", min_value=5, max_value=60, value=5)
            auto_refresh = st.checkbox("Enable Auto-Refresh", value=True)
            
            # Replay Demo mode toggle
            demo_mode = st.checkbox("Demo Mode (Replay Auckland)", value=True, help="Replays active Auckland sailing data. Recommended if no live event is active.")
        else:
            demo_mode = False
            auto_refresh = False
            
            # Date/Time selector
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", value=datetime(2026, 1, 17))
            with col2:
                end_date = st.date_input("End Date", value=datetime(2026, 1, 17))
                
            col3, col4 = st.columns(2)
            with col3:
                start_time_str = st.text_input("Start (UTC)", value="04:15:00")
            with col4:
                end_time_str = st.text_input("End (UTC)", value="05:10:00")
                
            def parse_time(t_str, default_t):
                try:
                    return datetime.strptime(t_str.strip(), "%H:%M:%S").time()
                except ValueError:
                    try:
                        return datetime.strptime(t_str.strip(), "%H:%M").time()
                    except ValueError:
                        return default_t
            
            start_time = parse_time(start_time_str, datetime_time(4, 15, 0))
            end_time = parse_time(end_time_str, datetime_time(5, 10, 0))
            
            start_datetime = datetime.combine(start_date, start_time)
            end_datetime = datetime.combine(end_date, end_time)

        # 3. Sailing Filters
        st.subheader("Sailing Parameters")
        boat_choice = st.selectbox("Selected Boat", ["NZL", "SWE", "BRA", "SUI", "CAN", "DEN", "GBR", "ITA", "FRA", "USA", "AUS", "ESP", "GER"], index=0)
        
        # Upwind vs Downwind Toggle
        sailing_direction = st.radio("Sailing Direction", ["Upwind", "Downwind"], horizontal=True)
        upwind_mode = (sailing_direction == "Upwind")
        
        period_duration = st.slider("Period Duration (seconds)", min_value=2, max_value=20, value=6)
        
        min_bsp_val = st.slider("Min BSP Threshold (kts)", min_value=0, max_value=50, value=30)
        min_vmg_pct = st.slider("Min % VMG Target", min_value=0, max_value=100, value=40)
        
        # Preset Management Options (Create / Delete)
        st.subheader("Manage Presets")
        new_preset_name = st.text_input("New Preset Name", placeholder="e.g. TWS 15-20 kts")
        if st.button("Save Current Parameters as New Preset", use_container_width=True):
            if new_preset_name.strip():
                # Get parameters from st.session_state['current_parameters']
                presets[new_preset_name] = st.session_state['current_parameters']
                if save_presets(presets):
                    st.success(f"Preset '{new_preset_name}' created!")
                    st.session_state['active_preset_name'] = new_preset_name
                    st.rerun()
            else:
                st.error("Please enter a valid preset name.")
                
        if st.button("Delete Selected Preset", use_container_width=True):
            if active_preset_name in presets:
                if len(presets) <= 1:
                    st.error("Cannot delete the last remaining preset.")
                else:
                    del presets[active_preset_name]
                    if save_presets(presets):
                        st.success(f"Preset '{active_preset_name}' deleted.")
                        # Fallback to first preset
                        st.session_state['active_preset_name'] = list(presets.keys())[0]
                        st.rerun()

        # Logout option
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
            st.session_state["password_correct"] = False
            st.rerun()

    # Title area
    st.markdown("<h1>F50 Performance Comparison Dashboard</h1>", unsafe_allow_html=True)
    st.caption(f"Analyzing boat performance against targets in real time. Active Preset: **{active_preset_name}** | Mode: **{sailing_direction}**")
    
    # ------------------
    # Data Fetch Pipeline
    # ------------------
    periods_df = pl.DataFrame()
    raw_df_rows = 0
    data_source_label = ""
    
    if demo_mode:
        data_source_label = "Demo Data (Auckland Day 1 Replay)"
        
        # Check if full Auckland Day 1 is loaded, if not fetch it
        # Auckland Replay range: 04:10 to 05:15
        if 'demo_raw_df' not in st.session_state:
            with st.spinner("Loading Auckland Day 1 replay data from InfluxDB (approx. 30s)..."):
                try:
                    fetcher = SGPDataProvider(boat=boat_choice)
                    st.session_state['demo_raw_df'] = fetcher.get_data("2026-01-17T04:10:00Z", "2026-01-17T05:15:00Z")
                except Exception as e:
                    st.error(f"Error loading demo data: {e}")
                    return
        
        # Re-process caching based on period parameters
        filter_hash = hash((period_duration, min_bsp_val))
        if st.session_state.get('demo_filter_hash') != filter_hash or 'demo_periods_df' not in st.session_state:
            st.session_state['demo_filter_hash'] = filter_hash
            if 'demo_raw_df' in st.session_state and st.session_state['demo_raw_df'].height > 0:
                with st.spinner("Processing demo sailing data straight lines..."):
                    fetcher = SGPDataProvider(boat=boat_choice)
                    processed_df = fetcher.process_data(
                        st.session_state['demo_raw_df'],
                        race_num=None,
                        period_duration=period_duration,
                        min_speed_upwind=min_bsp_val,
                        min_speed_downwind=min_bsp_val
                    )
                    st.session_state['demo_periods_df'] = fetcher.periods
            else:
                st.session_state['demo_periods_df'] = pl.DataFrame()
                
        # Calculate sliding virtual clock
        AUCKLAND_START = datetime(2026, 1, 17, 4, 15, 19)
        AUCKLAND_END = datetime(2026, 1, 17, 5, 8, 48)
        auckland_duration_sec = (AUCKLAND_END - AUCKLAND_START).total_seconds()
        
        elapsed = time_lib.time() - st.session_state['session_start_time']
        virtual_end_time = AUCKLAND_START + timedelta(seconds=(elapsed % auckland_duration_sec))
        virtual_start_time = virtual_end_time - timedelta(minutes=rolling_window)
        
        # Extract periods within the virtual rolling window
        all_periods = st.session_state.get('demo_periods_df', pl.DataFrame())
        if not all_periods.is_empty():
            periods_df = all_periods.filter(
                (pl.col("timestamp") >= virtual_start_time) & 
                (pl.col("timestamp") <= virtual_end_time)
            )
            raw_df_rows = st.session_state['demo_raw_df'].height
            st.success(f"🔴 Live Simulating: Virtual Time is **{virtual_end_time.strftime('%H:%M:%S')}** (Window: last {rolling_window} min)")
        else:
            st.warning("No periods computed in demo data.")
            
    else:
        # Real query mode
        if is_live:
            # Query from now - rolling window to now
            end_dt = datetime.utcnow()
            start_dt = end_dt - timedelta(minutes=rolling_window)
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            data_source_label = f"Live InfluxDB (Last {rolling_window} mins)"
        else:
            start_str = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
            data_source_label = f"Historical Range ({start_time_str} - {end_time_str} UTC)"

        # Fetch and process
        with st.spinner("Fetching and processing sailing data..."):
            try:
                fetcher = SGPDataProvider(boat=boat_choice)
                raw_df = fetcher.get_data(start_str, end_str)
                raw_df_rows = raw_df.height
                if raw_df_rows > 0:
                    fetcher.process_data(
                        raw_df,
                        race_num=None,
                        period_duration=period_duration,
                        min_speed_upwind=min_bsp_val,
                        min_speed_downwind=min_bsp_val
                    )
                    periods_df = fetcher.periods
                else:
                    periods_df = pl.DataFrame()
            except Exception as e:
                st.error(f"Error querying live database: {e}")
                periods_df = pl.DataFrame()

        if is_live and periods_df.is_empty() and raw_df_rows == 0:
            st.info("ℹ️ No active live data was returned from the database. Recommending 'Demo Mode' checkbox in the sidebar to replay simulation data.")
            
    # Apply direction & speed/VMG filters to periods
    filtered_periods = pl.DataFrame()
    if not periods_df.is_empty():
        if upwind_mode:
            if 'upwind' in periods_df.columns:
                filtered_periods = periods_df.filter(
                    pl.col("upwind") & 
                    (pl.col("bsp_mean") >= min_bsp_val) & 
                    (pl.col("tgt_vmg_percent_mean") >= min_vmg_pct)
                )
        else:
            if 'downwind' in periods_df.columns:
                filtered_periods = periods_df.filter(
                    pl.col("downwind") & 
                    (pl.col("bsp_mean") >= min_bsp_val) & 
                    (pl.col("tgt_vmg_percent_mean") >= min_vmg_pct)
                )

    # ------------------
    # Parameters Editor Table
    # ------------------
    st.subheader("Active Targets Configurator")
    st.caption("Change targets and tolerances below to update status colors on the fly. Save changes to persist them.")
    
    # Load current target dict
    curr_targets = st.session_state.get('current_parameters', presets[active_preset_name])
    mode_key = "upwind" if upwind_mode else "downwind"
    mode_targets = curr_targets.get(mode_key, {})
    
    # Render table in st.data_editor
    param_rows = []
    for metric_name in TARGETS_METADATA.keys():
        m_vals = mode_targets.get(metric_name, {"target": 0.0, "tolerance": 0.0})
        param_rows.append({
            "Metric": metric_name,
            "Target Value": float(m_vals["target"]),
            "Tolerance (+/-)": float(m_vals["tolerance"])
        })
    df_params = pd.DataFrame(param_rows)
    
    edited_df = st.data_editor(
        df_params,
        column_config={
            "Metric": st.column_config.TextColumn("Metric", disabled=True),
            "Target Value": st.column_config.NumberColumn("Target Value", format="%.2f"),
            "Tolerance (+/-)": st.column_config.NumberColumn("Tolerance (+/-)", format="%.2f", min_value=0.0)
        },
        disabled=["Metric"],
        use_container_width=True,
        num_rows="fixed",
        key="targets_editor"
    )
    
    # Build target map from edited table
    active_targets = {}
    for idx, row in edited_df.iterrows():
        active_targets[row["Metric"]] = {
            "target": row["Target Value"],
            "tolerance": row["Tolerance (+/-)"]
        }
        
    # Save edits back to presets in memory
    st.session_state['current_parameters'][mode_key] = active_targets
    
    # Persistence Action buttons
    col_save1, col_save2 = st.columns(2)
    with col_save1:
        if st.button("Save Changes to Selected Preset"):
            presets[active_preset_name] = st.session_state['current_parameters']
            if save_presets(presets):
                st.success(f"Changes saved to preset '{active_preset_name}'!")
    
    # Calculate performance metrics
    target_averages = {}
    for target_name in TARGETS_METADATA.keys():
        col_name = get_column_for_target(target_name, upwind_mode)
        if not filtered_periods.is_empty() and col_name in filtered_periods.columns:
            target_averages[target_name] = filtered_periods[col_name].mean()
        else:
            target_averages[target_name] = None

    # ------------------
    # SPEED v2 Sheet Target Overrides
    # ------------------
    sheet_targets = {}
    if not filtered_periods.is_empty():
        mean_bsp = filtered_periods['bsp_mean'].mean() if 'bsp_mean' in filtered_periods.columns else None
        mean_tws = filtered_periods['tws_mean'].mean() if 'tws_mean' in filtered_periods.columns else None
        sheet_targets = sheets_client.get_sheet_targets(mean_bsp, mean_tws, upwind_mode)
        for metric, sheet_val in sheet_targets.items():
            if metric in active_targets:
                active_targets[metric]['target'] = sheet_val

    if sheet_targets:
        metrics_str = ' · '.join(sheet_targets.keys())
        st.info(f"📊 **SPEED v2:** Targets for **{metrics_str}** interpolated from the sheet based on session BSP & TWS.")

    # ------------------
    # TARGET DASHBOARD GRID
    # ------------------
    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)

    # Category 1: Global
    st.markdown("<div class='category-header'>Global Performance</div>", unsafe_allow_html=True)
    cols_global = st.columns(3)
    global_list = ["BSP", "TWA", "VMG"]
    for idx, name in enumerate(global_list):
        with cols_global[idx]:
            avg_val = target_averages.get(name)
            tgt_val = active_targets[name]["target"]
            tol_val = active_targets[name]["tolerance"]
            render_target_card(
                name=name,
                value=avg_val,
                target=tgt_val,
                tolerance=tol_val,
                unit_str=TARGETS_METADATA[name]["unit"],
                format_str=TARGETS_METADATA[name]["format"]
            )
            
    # Category 2: Foils
    st.markdown("<div class='category-header'>Foil Commands & Settings</div>", unsafe_allow_html=True)
    cols_foils1 = st.columns(3)
    foils_list1 = ["CANT", "CANT Drop Target", "Ride Height"]
    for idx, name in enumerate(foils_list1):
        with cols_foils1[idx]:
            avg_val = target_averages.get(name)
            tgt_val = active_targets[name]["target"]
            tol_val = active_targets[name]["tolerance"]
            render_target_card(
                name=name,
                value=avg_val,
                target=tgt_val,
                tolerance=tol_val,
                unit_str=TARGETS_METADATA[name]["unit"],
                format_str=TARGETS_METADATA[name]["format"],
                source="SPEED v2" if name in sheet_targets else None
            )

    cols_foils2 = st.columns(2)
    foils_list2 = ["Rudder Average", "Rudder Differential"]
    for idx, name in enumerate(foils_list2):
        with cols_foils2[idx]:
            avg_val = target_averages.get(name)
            tgt_val = active_targets[name]["target"]
            tol_val = active_targets[name]["tolerance"]
            render_target_card(
                name=name,
                value=avg_val,
                target=tgt_val,
                tolerance=tol_val,
                unit_str=TARGETS_METADATA[name]["unit"],
                format_str=TARGETS_METADATA[name]["format"],
                source="SPEED v2" if name in sheet_targets else None
            )

    # Category 3: Wing
    st.markdown("<div class='category-header'>Wing Rigging & Trim</div>", unsafe_allow_html=True)
    cols_wing = st.columns(4)
    wing_list = ["Camber (CA1)", "Wing Twist", "Clew Position", "Wing Rotation"]
    for idx, name in enumerate(wing_list):
        with cols_wing[idx]:
            avg_val = target_averages.get(name)
            tgt_val = active_targets[name]["target"]
            tol_val = active_targets[name]["tolerance"]
            render_target_card(
                name=name,
                value=avg_val,
                target=tgt_val,
                tolerance=tol_val,
                unit_str=TARGETS_METADATA[name]["unit"],
                format_str=TARGETS_METADATA[name]["format"]
            )
            
    # Category 4: Boat
    st.markdown("<div class='category-header'>Boat Attitude</div>", unsafe_allow_html=True)
    cols_boat = st.columns(2)
    boat_list = ["Heel", "Pitch"]
    for idx, name in enumerate(boat_list):
        with cols_boat[idx]:
            avg_val = target_averages.get(name)
            tgt_val = active_targets[name]["target"]
            tol_val = active_targets[name]["tolerance"]
            render_target_card(
                name=name,
                value=avg_val,
                target=tgt_val,
                tolerance=tol_val,
                unit_str=TARGETS_METADATA[name]["unit"],
                format_str=TARGETS_METADATA[name]["format"]
            )

    # ------------------
    # Detailed Data Section
    # ------------------
    st.markdown("<hr style='border-color: #334155;'>", unsafe_allow_html=True)
    with st.expander("Show Details & Filtered Sailing Periods", expanded=False):
        st.markdown(f"**Data Source:** {data_source_label} | **Rows Queried:** {raw_df_rows} | **Periods Detected:** {len(periods_df)} | **Matching Filters:** {len(filtered_periods)}")
        if not filtered_periods.is_empty():
            # Convert to Pandas for display
            pd_disp = filtered_periods.to_pandas()
            st.dataframe(pd_disp, use_container_width=True)
        else:
            st.warning("No sailing periods found matching current speed/VMG/direction filters in this time window.")

    # Auto-refresh loop trigger
    if is_live and auto_refresh:
        time_lib.sleep(refresh_rate)
        st.rerun()

if __name__ == "__main__":
    if check_password():
        main()

"""
Streamlit App for Sailing Performance Analysis
Converts the HTML report generation to an interactive Streamlit dashboard
"""

import streamlit as st
import polars as pl
import pandas as pd
from datetime import datetime, time
import plots
from data_fetcher import SGPDataProvider
from bokeh.models import ColumnDataSource
from bokeh.palettes import Category10
import html_utils
from streamlit_bokeh import streamlit_bokeh as st_bokeh
import hashlib
import os
from typing import List

# python -m streamlit run app.py
# Fixed color mapping for boats/countries
BOAT_COLORS = {
    'NZL': "#07a0f9",
    'SWE': "#ae10da",
    'BRA': "#09f062",
    'SUI': '#FF0000',
    'CAN': "#19D1C2",
    'DEN': "#5F0ED0",
    'GBR': "#162446",
    'ITA': "#168915",
    'FRA': "#0A3DBE",
    'USA': "#CDCA18",
    'AUS': "#1C4D1C",
    'ESP': "#E7170C",
    'GER': "#DDEEEF",
}

def construct_color_map(color_bys: List[str], df: pl.DataFrame, y_cols: set[str] = None) -> dict:
    color_bys_map = {}
    
    # Fixed color mapping for boats/countries
    BOAT_COLORS = {
        'NZL': "#07a0f9",     # Blue (New Zealand)
        'SWE': "#ae10da",     # Purple (Sweden)
        'BRA': "#09f062",     # Green (Brazil)
        'SUI': '#FF0000',     # Red (Switzerland)
        'CAN': "#19D1C2",     # Cyan (Canada)
        'DEN': "#5F0ED0",     # Purple (Denmark)
        'GBR': "#162446",     # Navy Blue (Great Britain)
        'ITA': "#168915",     # Green (Italy)
        'FRA': "#0A3DBE",     # Blue (France)
        'USA': "#CDCA18",     # Yellow (United States)
        'AUS': "#1C4D1C",     # Dark Green (Australia)
        'ESP': "#E7170C",     # Red (Spain)
        'GER': "#DDEEEF",     # Light Gray (Germany)
    }
    
    for color_by in color_bys:
        color_map = {}
        if color_by == 'boat':
            unique_boats = df.select(pl.col('boat')).unique().to_series().to_list()
            # Use fixed colors for known boats, fallback to Category10 for unknown
            palette = Category10[10]
            color_map = {}
            unknown_boat_idx = 0
            for boat in unique_boats:
                if boat in BOAT_COLORS:
                    color_map[boat] = BOAT_COLORS[boat]
                else:
                    # For unknown boats, use palette colors
                    color_map[boat] = palette[unknown_boat_idx % len(palette)]
                    unknown_boat_idx += 1
        elif color_by == 'sails':
            unique_sails = df.select(pl.col('sails')).unique().to_series().to_list()
            palette = Category10[10]
            color_map = {sail: palette[i % len(palette)] for i, sail in enumerate(unique_sails)}
        elif color_by in ['tack', 'entry_tack', 'exit_tack']:
            df = df.with_columns(pl.lit(color_by).str.to_lowercase().alias(color_by))
            color_map = {'port': "#ef0808", 'starboard': "#18d618"}
        elif color_by == 'mean_tws':
            color_map = {'color_bar': {"#b826e0": 0.286, "#3b18d9": 0.428, "#1ed918": 0.5714, "#edb50c": 0.714, '#ed2e0c': 1.0}, 
                         'cols': {}}
            min = 0
            max = 21
            # Print the cutoffs
            color_range = color_map['color_bar']
            color_legend = {}
            for color, cutoff in color_range.items():
                value = min + cutoff * (max - min)
                color_legend[f"{round(value)} kts"] = color
            color_map['color_legend'] = color_legend
            color_map['cols']['mean_tws'] = {'min': min, 'max': max}
        else:
            if color_by in df.columns:
                col_type = df.select(pl.col(color_by)).dtypes[0]
                if col_type in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
                    color_map = 'color_bar'
            else:
                raise ValueError(f"Unknown color_by '{color_by}' or column does not exist in DataFrame.")
        color_bys_map[color_by] = color_map
    return color_bys_map

st.set_page_config(
    page_title="Sailing Performance Analysis",
    page_icon="assets/black_foils_logo.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
    <style>
    /* Main content area */
    .main {
        padding: 0rem 1rem;
    }
    
    /* Headers */
    h1 {
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 1.5rem;
        font-size: 2rem;
        letter-spacing: -0.5px;
    }
    
    h2 {
        font-weight: 500;
        color: #e0e0e0;
        margin-top: 2.5rem;
        margin-bottom: 1rem;
        font-size: 1.5rem;
        letter-spacing: -0.3px;
    }
    
    h3 {
        font-weight: 500;
        color: #c0c0c0;
        margin-bottom: 0.75rem;
        font-size: 1.2rem;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0e1117;
        padding-top: 1rem;
    }
    
    [data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 300px;
        max-width: 300px;
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
        color: #ffffff;
    }
    
    [data-testid="stSidebar"] h1 {
        font-size: 1.3rem;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        letter-spacing: -0.3px;
        color: #ffffff;
    }
    
    [data-testid="stSidebar"] h2 {
        font-size: 1rem;
        font-weight: 600;
        color: #ffffff;
        margin-top: 2rem;
        margin-bottom: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
    }

    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stText,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stTextInput label,
    [data-testid="stSidebar"] .stCheckbox label,
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stDateInput label,
    [data-testid="stSidebar"] .stTimeInput label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stRadio > label,
    [data-testid="stSidebar"] .stCheckbox > label {
        color: #ffffff !important;
    }

    [data-testid="stSidebar"] .stSelectbox select,
    [data-testid="stSidebar"] .stMultiSelect select {
        color: #ffffff !important;
    }

    [data-testid="stSidebar"] .stDateInput input,
    [data-testid="stSidebar"] .stTimeInput input,
    [data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] .stTextInput input {
        color: #000000 !important;
    }
    
    /* Info boxes */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid #4CAF50;
        background-color: rgba(76, 175, 80, 0.1);
    }
    
    /* Warning boxes */
    .stWarning {
        border-radius: 8px;
        border-left: 4px solid #ff9800;
        background-color: rgba(255, 152, 0, 0.1);
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 6px;
        font-weight: 500;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        font-size: 0.9rem;
    }
    
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg, #1976d2 0%, #2196f3 100%);
        border: none;
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 600;
        color: #000000 !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.95rem;
        font-weight: 500;
        color: #333333 !important;
    }

    /* White-background tables and cards */
    .stDataFrame, .stDataFrame td, .stDataFrame th,
    .stTable, .stTable td, .stTable th {
        color: #000000 !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        border-bottom: 2px solid #333;
    }
    
    .stTabs [data-baseweb="tab"] {
        font-weight: 500;
        font-size: 1rem;
        padding: 0.75rem 1.5rem;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(255, 255, 255, 0.05);
    }
    
    /* Input fields */
    .stDateInput, .stTimeInput, .stSelectbox, .stMultiSelect {
        margin-bottom: 1rem;
    }
    
    /* Dataframes */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Spacing */
    .stHeader {
        margin-bottom: 20px;
    }
    
    .block-container {
        padding-top: 2rem;
        max-width: 100%;
    }
    
    /* Radio buttons */
    .stRadio > label {
        font-weight: 500;
        color: #e0e0e0;
    }
    
    /* Captions */
    .caption {
        color: #000000 !important;
        font-size: 0.9rem;
    }
    
    /* Login page styling */
    div[data-testid="column"]:has(input[type="password"]) {
        background-color: rgba(30, 30, 30, 0.6);
        padding: 2rem 2rem 2.5rem 2rem;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
    }

    /* Ensure form inputs have white background for readability */
    input[type="text"],
    input[type="password"],
    input[type="number"],
    textarea,
    select,
    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    .stTimeInput input,
    .stTextArea textarea,
    .stSelectbox select,
    .stMultiSelect select {
        background-color: #ffffff !important;
        color: #000000 !important;
    }

    /* Placeholder text color for better contrast */
    ::placeholder {
        color: #666666 !important;
        opacity: 1 !important;
    }
    </style>
""", unsafe_allow_html=True)

def check_password():
    """Returns `True` if the user has entered the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Get credentials from environment variables
        correct_username = os.getenv("APP_USERNAME")
        correct_password = os.getenv("APP_PASSWORD")
        
        # Check if credentials are configured
        if not correct_username or not correct_password:
            st.session_state["password_correct"] = False
            st.session_state["credentials_missing"] = True
            return
        
        st.session_state["credentials_missing"] = False
        
        # Hash the entered password for comparison
        entered_password_hash = hashlib.sha256(st.session_state["password"].encode()).hexdigest()
        correct_password_hash = hashlib.sha256(correct_password.encode()).hexdigest()
        
        if (st.session_state["username"] == correct_username and 
            entered_password_hash == correct_password_hash):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
            del st.session_state["username"]  # Don't store username
        else:
            st.session_state["password_correct"] = False
            st.session_state["login_attempts"] = st.session_state.get("login_attempts", 0) + 1

    # First run, show login form
    if "password_correct" not in st.session_state:
        # Add spacing from top
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        
        # Center the login form
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            st.image("assets/black_foils_logo.png", use_container_width=True)
            st.markdown("<h2 style='text-align: center; margin: 2rem 0 1.5rem 0;'>Login</h2>", unsafe_allow_html=True)
            
            st.text_input("Username", key="username", placeholder="Enter username")
            st.text_input("Password", type="password", key="password", placeholder="Enter password")
            st.button("Login", on_click=password_entered, use_container_width=True, type="primary")
        
        return False
    
    # Password not correct, show input + error
    elif not st.session_state["password_correct"]:
        # Add spacing from top
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        
        # Center the login form
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            st.image("assets/black_foils_logo.png", use_container_width=True)
            st.markdown("<h2 style='text-align: center; margin: 2rem 0 1.5rem 0;'>Login</h2>", unsafe_allow_html=True)
            
            # Show appropriate error message
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
    
    # Password correct
    return True

def main():
    # Sidebar configuration
    with st.sidebar:
        st.image("assets/black_foils_logo.png", use_container_width=True)
        st.title("Configuration")
        
        # Report parameters
        st.subheader("Report Parameters")
        
        # Date inputs
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date",
                value=datetime(2026, 1, 17),
                help="Select the start date for the report"
            )
        with col2:
            end_date = st.date_input(
                "End Date",
                value=datetime(2026, 1, 17),
                help="Select the end date for the report"
            )
        
        # Time inputs
        col3, col4 = st.columns(2)
        with col3:
            start_time_str = st.text_input(
                "Start Time (UTC)",
                value="03:00",
                help="Start time in UTC (HH:MM or HH:MM:SS)"
            )
        with col4:
            end_time_str = st.text_input(
                "End Time (UTC)",
                value="23:59",
                help="End time in UTC (HH:MM or HH:MM:SS)"
            )
        
        # Parse time strings
        def parse_time(time_str, default_time):
            try:
                return datetime.strptime(time_str.strip(), "%H:%M").time()
            except ValueError:
                try:
                    return datetime.strptime(time_str.strip(), "%H:%M:%S").time()
                except ValueError:
                    return default_time
        
        start_time = parse_time(start_time_str, time(3, 0))
        end_time = parse_time(end_time_str, time(23, 59))
        
        # Boat selection
        boats = st.multiselect(
            "Select Boats",
            options=BOAT_COLORS.keys(),
            default=["NZL"],
            help="Select one or more boats to analyze"
        )
        
        # Race number (optional)
        race_num = st.number_input(
            "Race Number (Optional)",
            min_value=1,
            value=None,
            help="Leave empty for full day analysis"
        )

        period_duration = st.slider(
            "Period Duration (seconds)",
            min_value=2,
            max_value=20,
            value=6,
            step=1,
            help="Set the window size used to convert 'good' straight-line periods into report data points. Smaller values produce more points."
        )
        
        # Filters
        st.subheader("Filters")
        st.caption("Adjust these filters to update plots")
        
        filter_score_maneuvers = st.slider(
            "Maneuver Filter Score",
            min_value=0,
            max_value=100,
            value=0,
            help="Minimum quality score for maneuvers (0-100)"
        )
        
        min_pct_vmg_upw = st.slider(
            "Min % VMG Upwind",
            min_value=0,
            max_value=100,
            value=40,
            help="Minimum percentage VMG for upwind periods"
        )
        
        min_pct_vmg_dw = st.slider(
            "Min % VMG Downwind",
            min_value=0,
            max_value=100,
            value=40,
            help="Minimum percentage VMG for downwind periods"
        )
        
        min_bsp_upwind = st.slider(
            "Min BSP Upwind Periods",
            min_value=0,
            max_value=50,
            value=30,
            help="Minimum boat speed (knots) required to detect upwind straight-line periods"
        )
        
        min_bsp_downwind = st.slider(
            "Min BSP Downwind Periods",
            min_value=0,
            max_value=50,
            value=30,
            help="Minimum boat speed (knots) required to detect downwind straight-line periods"
        )
        
        min_bsp_reaching = st.slider(
            "Min BSP Reaching",
            min_value=0,
            max_value=50,
            value=20,
            help="Minimum boat speed for reaching periods (knots)"
        )
        
        # Generate button
        generate_report = st.button("Generate Report", type="primary", use_container_width=True)
        
        # Logout button at the bottom
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
            st.session_state["password_correct"] = False
            st.rerun()
    
    # Main content area
    if not boats:
        st.warning("Please select at least one boat from the sidebar to generate the report.")
        return
    
    # Combine date and time
    start_datetime = datetime.combine(start_date, start_time)
    end_datetime = datetime.combine(end_date, end_time)
    
    # Format for API
    start_time_str = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_str = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    st.info(f"Analysis Period: {start_datetime.strftime('%B %d, %Y %H:%M')} - {end_datetime.strftime('%B %d, %Y %H:%M')} UTC")
    
    # Only fetch data when Generate Report is clicked
    if generate_report:
        with st.spinner("Fetching and processing data..."):
            try:
                # Fetch data
                periods_list = []
                maneuvers_list = []
                maneuver_timeseries_list = []
                
                for boat in boats:
                    fetcher = SGPDataProvider(boat=boat)
                    df = fetcher.get_data(start_time_str, end_time_str)
                    st.success(f"Fetched data for {boat}: {df.height} rows")
                    
                    fetcher.process_data(
                        df,
                        race_num=race_num,
                        period_duration=period_duration,
                        min_speed_upwind=min_bsp_upwind,
                        min_speed_downwind=min_bsp_downwind,
                    )
                    periods_list.append(fetcher.periods)
                    maneuvers_list.append(fetcher.maneuvers)
                    maneuver_timeseries_list.append(fetcher.maneuver_timeseries)
                
                # Concatenate all data
                periods = pl.concat(periods_list, how='diagonal_relaxed') if periods_list else pl.DataFrame()
                maneuvers = pl.concat(maneuvers_list, how='diagonal_relaxed') if maneuvers_list else pl.DataFrame()
                maneuver_timeseries = pl.concat(maneuver_timeseries_list, how='diagonal_relaxed') if maneuver_timeseries_list else pl.DataFrame()
                
                # Store in session state - raw unfiltered data
                st.session_state['data_loaded'] = True
                st.session_state['raw_periods'] = periods
                st.session_state['raw_maneuvers'] = maneuvers
                st.session_state['raw_maneuver_timeseries'] = maneuver_timeseries
                st.session_state['boats'] = boats
                
            except Exception as e:
                st.error(f"Error fetching data: {str(e)}")
                return

    # Display data if loaded (filters are applied here, not during data fetch)
    if 'data_loaded' in st.session_state:
        # Get raw data from session state
        periods = st.session_state['raw_periods']
        maneuvers = st.session_state['raw_maneuvers']
        maneuver_timeseries = st.session_state['raw_maneuver_timeseries']
        
        # Summary Section
        st.header("Report Summary")
        
        if not periods.is_empty():
            # Create summary metrics
            cols = st.columns(4)
            
            for idx, boat in enumerate(boats):
                with cols[idx % 4]:
                    boat_periods = periods.filter(pl.col('boat') == boat)
                    upw_periods = boat_periods.filter(pl.col('upwind'))
                    dw_periods = boat_periods.filter(pl.col('downwind'))
                    
                    # Check if reaching column exists
                    if 'reaching' in periods.columns:
                        reach_periods = boat_periods.filter(pl.col('reaching'))
                        caption = f"Upwind: {len(upw_periods)} | Downwind: {len(dw_periods)} | Reaching: {len(reach_periods)}"
                    else:
                        caption = f"Upwind: {len(upw_periods)} | Downwind: {len(dw_periods)}"
                    
                    st.metric(
                        label=f"{boat}",
                        value=f"{len(boat_periods)} periods"
                    )
                    st.caption(caption)
        
        if not maneuvers.is_empty():
            st.subheader("Maneuvers Summary")
            cols = st.columns(4)
            
            for idx, boat in enumerate(boats):
                with cols[idx % 4]:
                    boat_maneuvers = maneuvers.filter(pl.col('boat') == boat)
                    tacks = boat_maneuvers.filter(pl.col('maneuver_type') == 'Tack')
                    gybes = boat_maneuvers.filter(pl.col('maneuver_type') == 'Gybe')
                    
                    st.metric(
                        label=f"{boat} Maneuvers",
                        value=f"{len(boat_maneuvers)}"
                    )
                    st.caption(f"Tacks: {len(tacks)} | Gybes: {len(gybes)}")
        
        # Tabs for different analysis sections
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["Upwind Analysis", "Downwind Analysis", "Reaching Analysis", "Maneuvers", "Raw Data"])
        
        with tab1:
            display_period_analysis(periods, "upwind", min_pct_vmg_upw, boats)
        
        with tab2:
            display_period_analysis(periods, "downwind", min_pct_vmg_dw, boats)
        
        with tab3:
            display_period_analysis(periods, "reaching", min_bsp_reaching, boats)
        
        with tab4:
            display_maneuver_analysis(maneuvers, maneuver_timeseries, filter_score_maneuvers, boats)
        
        with tab5:
            display_raw_data(periods, maneuvers)
    
    else:
        # Welcome message
        st.markdown("""
        **To get started:**
        1. Configure your parameters in the sidebar
        2. Click the "Generate Report" button
        3. Explore the interactive charts and data
        
        ---
        """)


def display_period_analysis(periods, segment, min_pct_vmg, boats):
    """Display period analysis for upwind/downwind/reaching - shows all plots with default metrics"""
    st.header(f"{segment.capitalize()} Performance Analysis")
    
    if periods.is_empty():
        st.warning(f"No {segment} period data available.")
        return

    filtering_col = 'tgt_vmg_percent_mean' if segment != 'reaching' else 'bsp_mean'
    segment_col = segment

    if segment_col not in periods.columns:
        st.warning(f"The '{segment}' column is not available in the data. This may be due to the data format or period detection settings.")
        return
    
    segment_periods = periods.filter(
        pl.col(segment_col) & (pl.col(filtering_col) >= min_pct_vmg)
    )
    
    if segment_periods.is_empty():
        st.warning(f"No {segment} periods meet the filter criteria.")
        return
    
    # Setup color mapping (done once for all plots)
    period_color_bys = {'boat'}
    period_color_map = construct_color_map(period_color_bys, segment_periods)
    period_symbol_map = {'port': 's', 'starboard': 'o'}
    segment_periods = html_utils.add_colors_symbols_to_df_multi(
        segment_periods, 
        color_map=period_color_map, 
        color_bys=period_color_bys, 
        symbol_map=period_symbol_map, 
        symbol_by='tack'
    )
    
    # Convert to pandas once for reuse  
    segment_periods_pd = segment_periods.to_pandas()
    
    # Default metrics from build_daily_report.py
    boat_state_cols = ['bsp_mean', 'twa_n_mean', 'vmg_mean', 'heel_n_mean', 'trim_mean', 'heel_mean',
                       'foil_leeward_sink_mean', 'bow_sink_mean', 'leeward_rudder_immersion_mean',
                       'leeway_n_mean', 'rudder_angle_n_mean', 'leeward_effective_cant_mean', 
                       'leeward_cant_mean', 'leeward_flap_mean', 'leeward_rake_mean', 
                       'leeward_rake_aoa_mean', 'leeward_rudder_rake_mean', 'windward_rudder_rake_mean']
    
    wing_trim_cols = ['wing_twist_n_mean', 'wing_rotation_n_mean', 'clew_angle_n_mean', 
                      'cam1_angle_n_mean', 'cam2_angle_n_mean', 'cam3_angle_n_mean', 
                      'cam4_angle_n_mean', 'cam5_angle_n_mean', 'cam6_angle_n_mean']
    
    jib_trim_cols = ['jib_lead_percent_mean', 'jib_sheet_percent_mean', 'jib_sheet_angle_mean', 
                     'jib_cunningham_load_mean', 'jib_sheet_load_mean']
    
    variability_cols = ['wing_twist_std', 'wing_twist_total_var', 'wing_rotation_std', 
                        'wing_rotation_total_var', 'bsp_std', 'bsp_total_var', 'twa_std', 
                        'twa_total_var', 'heel_std', 'heel_total_var', 'trim_std', 'trim_total_var', 
                        'leeward_rudder_immersion_std', 'leeward_rudder_immersion_total_var', 
                        'rudder_angle_n_std', 'rudder_angle_n_total_var', 'leeward_cant_std', 
                        'leeward_cant_total_var', 'leeward_flap_std', 'leeward_flap_total_var', 
                        'leeward_rudder_rake_std', 'leeward_rudder_rake_total_var', 
                        'windward_rudder_rake_std', 'windward_rudder_rake_total_var', 
                        'jib_sheet_percent_std', 'jib_sheet_percent_total_var', 
                        'jib_sheet_angle_std', 'jib_sheet_angle_total_var']
    
    # Filter to only available columns
    boat_state_cols = [col for col in boat_state_cols if col in segment_periods.columns]
    wing_trim_cols = [col for col in wing_trim_cols if col in segment_periods.columns]
    jib_trim_cols = [col for col in jib_trim_cols if col in segment_periods.columns]
    variability_cols = [col for col in variability_cols if col in segment_periods.columns]
    
    # Combine all scatter plot columns
    all_scatter_cols = boat_state_cols + wing_trim_cols + jib_trim_cols + variability_cols

    # Create a shared ColumnDataSource for all plots to enable linked selection
    shared_source = ColumnDataSource(segment_periods_pd)
    
    # Combined plots with shared selection
    st.subheader("Performance Analysis")
    st.info("Lasso Select is active by default. Select data points to synchronize the selection across all plots below.")
    
    # Use bsp_mean for reaching, tgt_vmg_percent_mean for upwind/downwind
    box_plot_y_col = 'bsp_mean' if segment == 'reaching' else 'tgt_vmg_percent_mean'
    
    if box_plot_y_col in segment_periods.columns and 'tws_mean' in segment_periods.columns and all_scatter_cols:
        st_bokeh(
            plots.combined_period_plots(
                source=shared_source,
                y_column_box=box_plot_y_col,
                y_column_time='tws_mean',
                scatter_cols=all_scatter_cols,
                df=segment_periods,
                tws_col='tws_mean',
                color_map=period_color_map.get('boat'),
                color_by='boat_color',
                show_trendline=True,
                upwind=(segment == 'upwind'),
                trendline_by='boat_color'
            ),
            key=f"{segment}_combined_plots"
        )
    else:
        st.warning("Some required columns are missing for the combined view.")


def display_maneuver_analysis(maneuvers, maneuver_timeseries, filter_score, boats):
    """Display maneuver analysis (tacks and gybes) - shows all plots with default metrics"""
    st.header("Maneuver Analysis")
    
    if maneuvers.is_empty():
        st.warning("No maneuver data available.")
        return
    
    # Use tabs instead of radio button
    tack_tab, gybe_tab = st.tabs(["Tacks", "Gybes"])
    
    with tack_tab:
        _display_maneuver_type(maneuvers, maneuver_timeseries, filter_score, "Tack")
    
    with gybe_tab:
        _display_maneuver_type(maneuvers, maneuver_timeseries, filter_score, "Gybe")


def _display_maneuver_type(maneuvers, maneuver_timeseries, filter_score, maneuver_type):
    """Helper function to display analysis for a specific maneuver type"""
    
    # Filter maneuvers (filtering happens here based on current slider value)
    type_maneuvers = maneuvers.filter(pl.col('maneuver_type') == maneuver_type)
    filtered_maneuvers = type_maneuvers.filter(pl.col('filter_score') >= filter_score)
    
    if filtered_maneuvers.is_empty():
        st.warning(f"No {maneuver_type} maneuvers meet the filter criteria (score >= {filter_score}).")
        return
    
    # Setup color mapping (done once for all plots)
    maneuver_color_bys = {'boat'}
    maneuver_color_map = construct_color_map(maneuver_color_bys, filtered_maneuvers)
    
    # Convert entry_tack
    maneuver_entry_tack_map = {'Port': 'port', 'Stbd': 'starboard'}
    filtered_maneuvers = filtered_maneuvers.with_columns(
        pl.col("entry_tack").replace(maneuver_entry_tack_map).alias("entry_tack")
    )
    
    maneuver_symbol_map = {'port': 's', 'starboard': 'o'}
    filtered_maneuvers = html_utils.add_colors_symbols_to_df_multi(
        filtered_maneuvers, 
        color_map=maneuver_color_map, 
        color_bys=maneuver_color_bys, 
        symbol_map=maneuver_symbol_map, 
        symbol_by='entry_tack'
    )
    
    # Convert to pandas once for reuse
    filtered_maneuvers_pd = filtered_maneuvers.to_pandas()
    
    # Create a shared ColumnDataSource for all plots to enable linked selection
    shared_maneuver_source = ColumnDataSource(filtered_maneuvers_pd)
    
    # Default metrics from build_daily_report.py
    scatter_metrics = ['entry_bsp', 'min_bsp', 'delta_bsp', 'max_yaw_rate', 'max_leeway', 
                      'max_rudder_angle', 'overshoot_angle', 'maneuver_angle', 
                      'old_foil_sink_min', 'new_foil_sink_min']
    
    # Filter to only available columns
    scatter_metrics = [col for col in scatter_metrics if col in filtered_maneuvers.columns]
    
    # Prepare timeseries data if available
    ts_source = None
    available_y_cols = []
    
    if not maneuver_timeseries.is_empty():
        # Filter timeseries to match filtered maneuvers
        filtered_ids = filtered_maneuvers['id'].to_list()
        filtered_ts = maneuver_timeseries.filter(pl.col('id').is_in(filtered_ids))
        
        if not filtered_ts.is_empty():
            # Convert to pandas and prepare data for Bokeh
            filtered_ts_pd = filtered_ts.to_pandas()
            
            # Group by maneuver id for multi_line plots
            # The data needs to be in list-of-lists format for multi_line
            grouped_data = {
                'time_from_htw_ms': [],
                'bsp': [],
                'twa_n': [],
                'vmg': [],
                'acceleration': [],
                'heel': [],
                'trim': [],
                'yaw_rate': [],
                'rudder_angle': [],
                'leeway': [],
                'hull_altitude': [],
                'foil_port_sink_mean': [],
                'foil_stbd_sink_mean': [],
                'bow_sink_mean': [],
                'rudder_rake': [],
                'leeward_flap_speed': [],
                'id': [],
                'maneuver_id': [],
                'color': [],
                'line_style': []
            }
            
            for maneuver_id in filtered_ts_pd['id'].unique():
                maneuver_data = filtered_ts_pd[filtered_ts_pd['id'] == maneuver_id]
                
                # Get color from the maneuver dataframe
                maneuver_info = filtered_maneuvers_pd[filtered_maneuvers_pd['id'] == maneuver_id]
                if not maneuver_info.empty:
                    color = maneuver_info.iloc[0]['boat_color']
                else:
                    color = '#1f77b4'  # Default color
                
                # Append data for this maneuver
                grouped_data['time_from_htw_ms'].append(maneuver_data['time_from_htw_ms'].tolist())
                grouped_data['id'].append(maneuver_id)
                grouped_data['maneuver_id'].append(str(maneuver_id))
                grouped_data['color'].append(color)
                grouped_data['line_style'].append('solid')
                
                # Append y-column data
                for col in ['bsp', 'twa_n', 'vmg', 'acceleration', 'heel', 'trim', 'yaw_rate', 
                           'rudder_angle', 'leeway', 'hull_altitude', 'foil_port_sink_mean', 
                           'foil_stbd_sink_mean', 'bow_sink_mean', 'rudder_rake', 'leeward_flap_speed']:
                    if col in maneuver_data.columns:
                        grouped_data[col].append(maneuver_data[col].tolist())
                    else:
                        # If column doesn't exist, append empty list
                        grouped_data[col].append([])
            
            # Create ColumnDataSource for timeseries
            ts_source = ColumnDataSource(grouped_data)
            
            # Define y_columns to plot
            y_cols = ['bsp', 'twa_n', 'vmg', 'acceleration', 'heel', 'trim', 'yaw_rate', 
                     'rudder_angle', 'leeway', 'hull_altitude', 'foil_port_sink_mean', 
                     'foil_stbd_sink_mean', 'bow_sink_mean', 'rudder_rake', 'leeward_flap_speed']
            
            # Filter to only available columns (non-empty)
            available_y_cols = [col for col in y_cols if col in ts_source.data and any(len(lst) > 0 for lst in ts_source.data[col])]
    
    # Combined plots with shared selection including timeseries
    st.subheader("Maneuver Analysis")
    st.info("Lasso Select is active by default. Select data points to synchronize across all plots below, including timeseries.")
    
    if ('total_loss_m' in filtered_maneuvers.columns and 'mean_tws' in filtered_maneuvers.columns 
        and scatter_metrics and ts_source is not None and available_y_cols):
        # Create combined layout with linked timeseries
        st_bokeh(
            plots.combined_maneuver_plots_with_ts(
                agg_source=shared_maneuver_source,
                ts_source=ts_source,
                y_column_box='total_loss_m',
                y_column_time='mean_tws',
                scatter_cols=scatter_metrics,
                ts_y_cols=available_y_cols,
                df=filtered_maneuvers,
                tws_col='mean_tws',
                color_map=maneuver_color_map.get('boat'),
                color_by='boat_color',
                show_trendline=True
            ),
            key=f"{maneuver_type}_combined_plots_with_ts"
        )
    elif 'total_loss_m' in filtered_maneuvers.columns and 'mean_tws' in filtered_maneuvers.columns and scatter_metrics:
        # Fallback to combined plots without timeseries
        st_bokeh(
            plots.combined_maneuver_plots(
                source=shared_maneuver_source,
                y_column_box='total_loss_m',
                y_column_time='mean_tws',
                scatter_cols=scatter_metrics,
                df=filtered_maneuvers,
                tws_col='mean_tws',
                color_map=maneuver_color_map.get('boat'),
                color_by='boat_color',
                show_trendline=True
            ),
            key=f"{maneuver_type}_combined_plots"
        )
        if not maneuver_timeseries.is_empty():
            st.warning("Timeseries data is available but could not be linked. Check data format.")
    else:
        st.warning("Some required columns are missing for the combined view.")


def display_raw_data(periods, maneuvers):
    """Display raw data tables"""
    st.header("Raw Data Tables")
    
    data_type = st.radio(
        "Select Data Type",
        ["Periods", "Maneuvers"],
        horizontal=True
    )
    
    if data_type == "Periods":
        if not periods.is_empty():
            st.subheader("Periods Data")
            st.dataframe(periods.to_pandas(), use_container_width=True, height=700)
            
            # Download button
            csv = periods.to_pandas().to_csv(index=False)
            st.download_button(
                label="Download Periods CSV",
                data=csv,
                file_name="periods_data.csv",
                mime="text/csv"
            )
        else:
            st.warning("No periods data available.")
    
    else:  # Maneuvers
        if not maneuvers.is_empty():
            st.subheader("Maneuvers Data")
            st.dataframe(maneuvers.to_pandas(), use_container_width=True, height=700)
            
            # Download button
            csv = maneuvers.to_pandas().to_csv(index=False)
            st.download_button(
                label="Download Maneuvers CSV",
                data=csv,
                file_name="maneuvers_data.csv",
                mime="text/csv"
            )
        else:
            st.warning("No maneuvers data available.")


if __name__ == "__main__":
    if check_password():
        main()

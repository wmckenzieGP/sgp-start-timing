import numpy as np
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

# BSP in the sheet is kph; app bsp_mean is in kts
KTS_TO_KPH = 1.852
# TWS in the sheet drop table is kts; app tws_mean is in kph
KPH_TO_KTS = 1 / 1.852


@st.cache_resource
def _get_gc():
    """Authenticated gspread client. Uses Streamlit secrets in production, JSON file locally."""
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    except Exception:
        creds = Credentials.from_service_account_file(
            'blackfoilsdata-0475bd5996f2.json', scopes=SCOPES
        )
    return gspread.authorize(creds)


def _parse_table(rows, start_col=0):
    """Extract (xs, ys) numeric arrays from a two-column section of sheet rows."""
    xs, ys = [], []
    for row in rows:
        try:
            x = float(str(row[start_col]).strip())
            y = float(str(row[start_col + 1]).strip())
            xs.append(x)
            ys.append(y)
        except (ValueError, IndexError):
            continue
    return np.array(xs), np.array(ys)


def _interp(x_val, xs, ys):
    """Clamped linear interpolation. Returns None if table is empty or input is None."""
    if x_val is None or len(xs) == 0:
        return None
    return float(np.interp(x_val, xs, ys))


@st.cache_data(ttl=300)
def load_speed_targets():
    """
    Load and parse lookup tables from SPEED v2.
    Returns a nested dict of (xs, ys) arrays per metric/direction, or None on failure.
    Results cached for 5 minutes.

    Sheet structure (0-indexed rows):
      Cant & Drop Targets:
        rows 3-16   → upwind cant vs BSP (kph)
        rows 20-29  → downwind cant vs BSP (kph)
        rows 33-43  → drop targets vs TWS (kts); cols 0-1 UW, cols 4-5 DW
      Rudder & LARW Targets:
        rows 3-13   → upwind LARW2 vs BSP (kph); cols 0-1
        rows 3-18   → downwind LARW2 vs BSP (kph); cols 4-5
    """
    try:
        gc = _get_gc()
        sh = gc.open('SPEED v2')

        cant_rows = sh.worksheet('Cant & Drop Targets').get_all_values()
        rudder_rows = sh.worksheet('Rudder & LARW Targets').get_all_values()

        return {
            'cant': {
                'upwind':   _parse_table(cant_rows[3:17],  start_col=0),
                'downwind': _parse_table(cant_rows[20:30], start_col=0),
            },
            'drop': {
                'upwind':   _parse_table(cant_rows[33:44], start_col=0),
                'downwind': _parse_table(cant_rows[33:44], start_col=4),
            },
            'rudder': {
                'upwind':   _parse_table(rudder_rows[3:14], start_col=0),
                'downwind': _parse_table(rudder_rows[3:19], start_col=4),
            },
        }
    except Exception:
        return None


def get_sheet_targets(mean_bsp_kts, mean_tws_kph, upwind: bool):
    """
    Interpolate performance targets from SPEED v2 for the current session conditions.

    Args:
        mean_bsp_kts: session mean boat speed in knots (from bsp_mean column)
        mean_tws_kph: session mean true wind speed in kph (from tws_mean column)
        upwind: True for upwind, False for downwind

    Returns:
        Dict of {metric_name: target_value} for sheet-covered metrics.
        Empty dict if sheet is unavailable or inputs are None.
    """
    tables = load_speed_targets()
    if tables is None:
        return {}

    direction = 'upwind' if upwind else 'downwind'
    result = {}

    # Cant and Rudder look up by BSP (sheet uses kph, convert from kts)
    if mean_bsp_kts is not None:
        bsp_kph = mean_bsp_kts * KTS_TO_KPH

        val = _interp(bsp_kph, *tables['cant'][direction])
        if val is not None:
            result['CANT'] = val

        val = _interp(bsp_kph, *tables['rudder'][direction])
        if val is not None:
            result['Rudder Average'] = val

    # Drop target looks up by TWS (sheet uses kts, convert from kph)
    if mean_tws_kph is not None:
        tws_kts = mean_tws_kph * KPH_TO_KTS

        val = _interp(tws_kts, *tables['drop'][direction])
        if val is not None:
            result['CANT Drop Target'] = val

    return result

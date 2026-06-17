import streamlit as st

# gspread and google-auth are imported lazily inside functions so a missing
# package only breaks sheet fetching, not the entire app startup.

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

# Valid wing sizes per foil type
WING_OPTIONS = {
    'HSB2': ['18m', '24m'],
    'LAB2': ['24m', '27m'],
}

# Section lookup: (foils, wing_size, upwind) -> (first_data_row, exclusive_end_row)
# Row indices are 0-based into the raw sheet data. Reach sections are excluded.
_SECTIONS = {
    ('HSB2', '24m', True):  (4,  16),   # rows 4-15:  TWS 17.5-45
    ('HSB2', '24m', False): (18, 32),   # rows 18-31: TWS 17.5-50
    ('HSB2', '18m', True):  (51, 62),   # rows 51-61: TWS 25-50
    ('HSB2', '18m', False): (63, 74),   # rows 63-73: TWS 25-50
    ('LAB2', '27m', True):  (4,  15),   # rows 4-14:  TWS 5-30
    ('LAB2', '27m', False): (21, 32),   # rows 21-31: TWS 5-30
    ('LAB2', '24m', True):  (36, 45),   # rows 36-44: TWS 10-30
    ('LAB2', '24m', False): (47, 55),   # rows 47-54: TWS 10-27.5
}


@st.cache_resource
def _get_gc():
    """Authenticated gspread client. Uses Streamlit secrets in production, JSON file locally."""
    import gspread
    from google.oauth2.service_account import Credentials
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
    except Exception:
        creds = Credentials.from_service_account_file(
            'blackfoilsdata-0475bd5996f2.json', scopes=SCOPES
        )
    return gspread.authorize(creds)


@st.cache_data(ttl=300)
def _load_cheatsheet_rows():
    """
    Load raw row data from both cheatsheet tabs.
    Returns {'HSB2': [[...], ...], 'LAB2': [[...], ...]} or None on failure.
    Cached for 5 minutes — sheet content rarely changes mid-session.

    Column layout (0-indexed):
      0: CONFIG/MODE  1: TWS  2: TWA  3: SGP BSP  4: BSP  5: DRP  6: CANT
      7: RH TARGET  8: LARW RUD AVG  9: HSRW RUD AVG  10: CAMBER  11: WING TWIST
      12: CLEW POSITION  13: WING ROTATION
      14-16: BIG JIB (TRACK, SHEET LOAD, CUNNO LOAD)
      17-19: SMALL JIB (TRACK, SHEET LOAD, CUNNO LOAD)
    """
    try:
        gc = _get_gc()
        sh = gc.open('SPEED v2')
        result = {}
        for ws in sh.worksheets():
            name = ws.title
            if 'HSB2' in name and 'heatsheet' in name.lower():
                result['HSB2'] = ws.get_all_values()
            elif 'LAB2' in name and 'heatsheet' in name.lower():
                result['LAB2'] = ws.get_all_values()
        return result if len(result) == 2 else None
    except Exception:
        return None


def _parse(row, col):
    """Return float from row[col], or None if empty/missing/non-numeric."""
    try:
        s = str(row[col]).strip()
        return float(s) if s else None
    except (IndexError, ValueError):
        return None


def get_cheatsheet_targets(foils, wing_size, rudders, jib, upwind, tws_mean):
    """
    Look up all performance targets from the SPEED v2 cheatsheet for the
    current boat configuration and wind conditions.

    Args:
        foils:     'HSB2' or 'LAB2'
        wing_size: '18m', '24m', or '27m' (must match foil choice)
        rudders:   'LARW' or 'HSRW'
        jib:       'Big' or 'Small'
        upwind:    True for upwind section, False for downwind
        tws_mean:  session mean TWS in km/h. The sheet TWS column is also in km/h
                   (confirmed). No unit conversion is applied — values are compared
                   directly.

    Returns:
        dict with keys for all metrics plus '_matched_tws' (the sheet row TWS
        that was selected). Values are float or None (None = empty cell = no target).
        Returns {} if sheet is unavailable or config has no matching section.
    """
    tables = _load_cheatsheet_rows()
    if tables is None or foils not in tables:
        return {}

    key = (foils, wing_size, upwind)
    if key not in _SECTIONS:
        return {}

    start, end = _SECTIONS[key]
    rows = tables[foils][start:end]

    # Find closest TWS row — no interpolation, round to nearest available
    best_row = None
    best_diff = float('inf')
    for row in rows:
        tws_str = str(row[1]).strip() if len(row) > 1 else ''
        if not tws_str:
            continue
        try:
            diff = abs(float(tws_str) - (tws_mean or 0))
            if diff < best_diff:
                best_diff = diff
                best_row = row
        except ValueError:
            continue

    if best_row is None:
        return {}

    rud_col = 8 if rudders == 'LARW' else 9
    jib_base = 14 if jib == 'Big' else 17

    return {
        'TWA':            _parse(best_row, 2),
        'BSP':            _parse(best_row, 4),
        'DRP':            _parse(best_row, 5),
        'CANT':           _parse(best_row, 6),
        'Ride Height':    _parse(best_row, 7),
        'Rudder Avg':     _parse(best_row, rud_col),
        'Camber':         _parse(best_row, 10),
        'Wing Twist':     _parse(best_row, 11),
        'Clew Position':  _parse(best_row, 12),
        'Wing Rotation':  _parse(best_row, 13),
        'Jib Track':      _parse(best_row, jib_base),
        'Jib Sheet Load': _parse(best_row, jib_base + 1),
        'Jib Cunno Load': _parse(best_row, jib_base + 2),
        'VMG':            None,
        '_matched_tws':   float(str(best_row[1]).strip()),
    }

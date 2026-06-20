from concurrent.futures import ThreadPoolExecutor, as_completed
from influxdb_client import InfluxDBClient
import pandas as pd
import arrow
from config import ORG_ID, TOKEN, URL

BOAT_MEASUREMENTS = [
    "LATITUDE_GPS_unk",
    "LONGITUDE_GPS_unk",
    "GPS_COG_deg",
    "GPS_SOG_km_h_1",
    "TWA_SGP_deg",
]

ALL_BOATS = ["NZL", "AUS", "GBR", "FRA", "DEN", "ESP", "SUI", "CAN", "USA", "ITA", "GER", "BRA", "SWE"]


def _client():
    return InfluxDBClient(url=URL, token=TOKEN, org=ORG_ID, timeout=120_000)


def _fmt(dt) -> str:
    return arrow.get(dt).format("YYYY-MM-DDTHH:mm:ss.SSS") + "Z"


def _measurement_filter(measurements: list[str]) -> str:
    return " or ".join(f'r["_measurement"] == "{m}"' for m in measurements)


# ---------------------------------------------------------------------------
# Mark positions — single query for both marks and both coordinates
# ---------------------------------------------------------------------------

def fetch_mark_positions(start_time, end_time) -> dict[str, tuple[float, float]]:
    """Return {mark: (lat, lon)} for SL1 and SL2. Single InfluxDB round trip."""
    query = f"""
from(bucket: "sailgp")
  |> range(start: {_fmt(start_time)}, stop: {_fmt(end_time)})
  |> filter(fn: (r) => r["_measurement"] == "LATITUDE_MDSS_deg" or r["_measurement"] == "LONGITUDE_MDSS_deg")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["level"] == "mdss")
  |> filter(fn: (r) => r["boat"] == "SL1" or r["boat"] == "SL2")
  |> group(columns: ["boat", "_measurement"])
  |> mean()
  |> group()
"""
    with _client() as c:
        result = c.query_api().query_data_frame(org=ORG_ID, query=query)

    df = _coerce_result(result)
    if df.empty or "_value" not in df.columns:
        return {}

    marks = {}
    for mark in ("SL1", "SL2"):
        sub = df[df["boat"] == mark] if "boat" in df.columns else pd.DataFrame()
        if sub.empty:
            continue
        lat_row = sub[sub["_measurement"] == "LATITUDE_MDSS_deg"]
        lon_row = sub[sub["_measurement"] == "LONGITUDE_MDSS_deg"]
        if lat_row.empty or lon_row.empty:
            continue
        lat = float(lat_row["_value"].iloc[0]) / 10_000_000
        lon = float(lon_row["_value"].iloc[0]) / 10_000_000
        marks[mark] = (lat, lon)

    return marks


# ---------------------------------------------------------------------------
# Boat GPS — single boat fetch
# ---------------------------------------------------------------------------

def fetch_boat_gps(boat: str, start_time, end_time) -> pd.DataFrame:
    """Return time-series GPS + wind data for a single boat."""
    mfilter = _measurement_filter(BOAT_MEASUREMENTS)
    query = f"""
from(bucket: "sailgp")
  |> range(start: {_fmt(start_time)}, stop: {_fmt(end_time)})
  |> filter(fn: (r) => {mfilter})
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["level"] == "strm")
  |> filter(fn: (r) => r["boat"] == "{boat}")
  |> drop(columns: ["_start", "_stop", "_field", "level", "boat"])
  |> pivot(rowKey: ["_time"], columnKey: ["_measurement"], valueColumn: "_value")
"""
    with _client() as c:
        result = c.query_api().query_data_frame(org=ORG_ID, query=query)

    df = _coerce_result(result)
    if df.empty:
        return df

    df = df.rename(columns={
        "_time": "timestamp",
        "LATITUDE_GPS_unk": "latitude",
        "LONGITUDE_GPS_unk": "longitude",
        "GPS_COG_deg": "cog",
        "GPS_SOG_km_h_1": "sog",
        "TWA_SGP_deg": "twa",
    })
    df["latitude"] = df["latitude"] / 10_000_000
    df["longitude"] = df["longitude"] / 10_000_000
    df["boat"] = boat
    # Strip timezone so timestamp comparisons work throughout the app
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)

    df = df.sort_values("timestamp").reset_index(drop=True)
    for col in ["latitude", "longitude", "cog", "sog", "twa"]:
        if col in df.columns:
            df[col] = df[col].interpolate(method="linear")
    return df


# ---------------------------------------------------------------------------
# Parallel fetch for all selected boats
# ---------------------------------------------------------------------------

def fetch_all_boats_gps(
    boats: list[str],
    start_time,
    end_time,
    max_workers: int = 6,
) -> dict[str, pd.DataFrame]:
    """Fetch GPS data for multiple boats concurrently. Returns {boat: df}."""
    results = {}

    def _fetch(boat):
        return boat, fetch_boat_gps(boat, start_time, end_time)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(boats))) as ex:
        futures = {ex.submit(_fetch, b): b for b in boats}
        for future in as_completed(futures):
            boat, df = future.result()
            results[boat] = df

    return results


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def fetch_mark_measurements(start_time, end_time) -> pd.DataFrame:
    """Return every distinct measurement for SL1/SL2 at mdss level."""
    query = f"""
from(bucket: "sailgp")
  |> range(start: {_fmt(start_time)}, stop: {_fmt(end_time)})
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["level"] == "mdss")
  |> filter(fn: (r) => r["boat"] == "SL1" or r["boat"] == "SL2")
  |> keep(columns: ["boat", "_measurement"])
  |> distinct(column: "_measurement")
"""
    with _client() as c:
        result = c.query_api().query_data_frame(org=ORG_ID, query=query)
    return _coerce_result(result)


def _coerce_result(result) -> pd.DataFrame:
    if isinstance(result, list):
        parts = [r for r in result if r is not None and not r.empty]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if result is None or result.empty:
        return pd.DataFrame()
    return result.reset_index(drop=True)

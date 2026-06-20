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


def fetch_mark_positions(start_time, end_time) -> dict[str, tuple[float, float]]:
    """
    Return {mark_name: (lat, lon)} for SL1 and SL2, averaged over the time window.
    Queries each measurement separately (mirrors the Grafana mdss pattern).
    Returns an empty dict if no data found.
    """
    marks = {}
    for mark in ("SL1", "SL2"):
        lat = _fetch_single_mdss_mean("LATITUDE_GPS_unk", mark, start_time, end_time)
        lon = _fetch_single_mdss_mean("LONGITUDE_GPS_unk", mark, start_time, end_time)
        if lat is not None and lon is not None:
            marks[mark] = (lat / 10_000_000, lon / 10_000_000)
    return marks


def _fetch_single_mdss_mean(measurement: str, mark: str, start_time, end_time):
    """Fetch the mean value of a single measurement for a mark over the time window."""
    query = f"""
from(bucket: "sailgp")
  |> range(start: {_fmt(start_time)}, stop: {_fmt(end_time)})
  |> filter(fn: (r) => r["_measurement"] == "{measurement}")
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["level"] == "mdss")
  |> filter(fn: (r) => r["boat"] == "{mark}")
  |> mean()
"""
    with _client() as c:
        result = c.query_api().query_data_frame(org=ORG_ID, query=query)

    df = _coerce_result(result)
    if df.empty or "_value" not in df.columns:
        return None
    val = df["_value"].dropna()
    return float(val.iloc[0]) if not val.empty else None


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
    df = df.sort_values("timestamp").reset_index(drop=True)
    df[["latitude", "longitude", "cog", "sog", "twa"]] = (
        df[["latitude", "longitude", "cog", "sog", "twa"]].interpolate(method="linear")
    )
    return df



def fetch_mark_measurements(start_time, end_time) -> pd.DataFrame:
    """
    Diagnostic: return every distinct _measurement available for SL1 and SL2
    at mdss level in the given window. Use this to find the correct GPS field names.
    """
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

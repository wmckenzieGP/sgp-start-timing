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

MARK_MEASUREMENTS = [
    "LATITUDE_GPS_unk",
    "LONGITUDE_GPS_unk",
]

MARK_NAMES = ["SL1", "SL2"]

ALL_BOATS = ["NZL", "AUS", "GBR", "FRA", "DEN", "ESP", "SUI", "CAN", "USA", "ITA", "GER", "BRA", "SWE"]


def _client():
    return InfluxDBClient(url=URL, token=TOKEN, org=ORG_ID, timeout=120_000)


def _fmt(dt) -> str:
    return arrow.get(dt).format("YYYY-MM-DDTHH:mm:ss.SSS") + "Z"


def _measurement_filter(measurements: list[str]) -> str:
    return " or ".join(f'r["_measurement"] == "{m}"' for m in measurements)


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


def fetch_mark_positions(start_time, end_time) -> dict[str, tuple[float, float]]:
    """Return {mark_name: (lat, lon)} averaged over the time window."""
    mfilter = _measurement_filter(MARK_MEASUREMENTS)
    mark_filter = " or ".join(f'r["boat"] == "{m}"' for m in MARK_NAMES)

    query = f"""
from(bucket: "sailgp")
  |> range(start: {_fmt(start_time)}, stop: {_fmt(end_time)})
  |> filter(fn: (r) => {mfilter})
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["level"] == "mdss")
  |> filter(fn: (r) => {mark_filter})
  |> drop(columns: ["_start", "_stop", "_field", "level"])
  |> pivot(rowKey: ["_time", "boat"], columnKey: ["_measurement"], valueColumn: "_value")
"""
    with _client() as c:
        result = c.query_api().query_data_frame(org=ORG_ID, query=query)

    df = _coerce_result(result)
    if df.empty:
        return {}

    df["LATITUDE_GPS_unk"] = df["LATITUDE_GPS_unk"] / 10_000_000
    df["LONGITUDE_GPS_unk"] = df["LONGITUDE_GPS_unk"] / 10_000_000

    marks = {}
    for mark in MARK_NAMES:
        sub = df[df["boat"] == mark]
        if not sub.empty:
            marks[mark] = (sub["LATITUDE_GPS_unk"].mean(), sub["LONGITUDE_GPS_unk"].mean())

    return marks


def _coerce_result(result) -> pd.DataFrame:
    if isinstance(result, list):
        parts = [r for r in result if r is not None and not r.empty]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if result is None or result.empty:
        return pd.DataFrame()
    return result.reset_index(drop=True)

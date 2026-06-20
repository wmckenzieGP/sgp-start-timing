"""
Start line crossing detection and practice start grouping.

Sequence per practice start (working backwards from the start):
  T1  → boat crosses the *extended* start line on port tack (TWA < 0)
  T2  → boat tacks/gybes port→starboard (TWA sign flips negative→positive)
  Start → boat crosses the *actual* line segment on starboard tack (TWA > 0)

Timings reported as seconds before the start crossing.
"""

import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PracticeStart:
    boat: str
    number: int
    start_time: pd.Timestamp
    t2_time: Optional[pd.Timestamp] = None
    t1_time: Optional[pd.Timestamp] = None

    @property
    def t2_delta(self) -> Optional[float]:
        if self.t2_time is None:
            return None
        return (self.start_time - self.t2_time).total_seconds()

    @property
    def t1_delta(self) -> Optional[float]:
        if self.t1_time is None:
            return None
        return (self.start_time - self.t1_time).total_seconds()

    def track_window(self, df: pd.DataFrame, pre_t1_s: float = 20.0, post_start_s: float = 10.0) -> pd.DataFrame:
        """Slice of the boat's GPS track for display."""
        anchor = self.t1_time if self.t1_time is not None else self.start_time
        t_start = anchor - pd.Timedelta(seconds=pre_t1_s)
        t_end = self.start_time + pd.Timedelta(seconds=post_start_s)
        mask = (df["timestamp"] >= t_start) & (df["timestamp"] <= t_end)
        return df[mask].copy()


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _lat_lon_to_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Flat-earth projection in metres relative to a reference point."""
    R = 6_371_000.0
    x = math.radians(lon - ref_lon) * R * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * R
    return x, y


def _signed_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """
    Signed distance of point P from the infinite line through A→B.
    Positive = left side, negative = right side (using right-hand rule).
    """
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    return ((px - ax) * dy - (py - ay) * dx) / length


def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float, tol: float = 20.0) -> bool:
    """True if the nearest point on segment AB to P is within tol metres of P."""
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay) < tol
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    near_x = ax + t * dx
    near_y = ay + t * dy
    return math.hypot(px - near_x, py - near_y) < tol


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def _compute_crossings(df: pd.DataFrame, sl1_xy: tuple, sl2_xy: tuple) -> pd.DataFrame:
    """
    Add columns to df:
      dist_to_line  : signed distance (metres) to the extended start line
      on_segment    : bool, nearest point is within the segment bounds + buffer
    """
    ax, ay = sl1_xy
    bx, by = sl2_xy

    # Extend segment by 200 m each end so boats near the marks still trigger
    seg_len = math.hypot(bx - ax, by - ay)
    if seg_len == 0:
        df["dist_to_line"] = np.nan
        df["on_segment"] = False
        return df

    ux, uy = (bx - ax) / seg_len, (by - ay) / seg_len
    ext = 200.0
    ax_e, ay_e = ax - ux * ext, ay - uy * ext
    bx_e, by_e = bx + ux * ext, by + uy * ext

    df = df.copy()
    df["dist_to_line"] = df.apply(
        lambda r: _signed_distance(r["x"], r["y"], ax, ay, bx, by), axis=1
    )
    df["on_segment"] = df.apply(
        lambda r: _point_on_segment(r["x"], r["y"], ax_e, ay_e, bx_e, by_e, tol=50.0), axis=1
    )
    return df


MIN_CROSSING_GAP_S = 15  # ignore crossings within 15 s of each other


def detect_practice_starts(
    df: pd.DataFrame,
    sl1: tuple[float, float],
    sl2: tuple[float, float],
    boat: str,
) -> list[PracticeStart]:
    """
    Detect all practice starts for a single boat.

    Parameters
    ----------
    df   : time-series for one boat, must have columns:
           timestamp, latitude, longitude, twa
    sl1  : (lat, lon) of SL1 mark
    sl2  : (lat, lon) of SL2 mark
    boat : boat identifier string
    """
    if df.empty or len(df) < 5:
        return []

    # Project everything to flat-earth XY
    ref_lat = (sl1[0] + sl2[0]) / 2
    ref_lon = (sl1[1] + sl2[1]) / 2
    sl1_xy = _lat_lon_to_xy(sl1[0], sl1[1], ref_lat, ref_lon)
    sl2_xy = _lat_lon_to_xy(sl2[0], sl2[1], ref_lat, ref_lon)

    df = df.copy()
    df["x"], df["y"] = zip(*df.apply(
        lambda r: _lat_lon_to_xy(r["latitude"], r["longitude"], ref_lat, ref_lon), axis=1
    ))
    df = _compute_crossings(df, sl1_xy, sl2_xy)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Sign of distance to line  (+1 left / -1 right)
    df["side"] = np.sign(df["dist_to_line"])

    # -----------------------------------------------------------------------
    # Detect start crossings  (on segment, starboard tack → TWA > 0)
    # -----------------------------------------------------------------------
    start_events: list[pd.Timestamp] = []
    for i in range(1, len(df)):
        prev, cur = df.iloc[i - 1], df.iloc[i]
        if prev["side"] == cur["side"] or prev["side"] == 0 or cur["side"] == 0:
            continue
        mid_twa = (prev["twa"] + cur["twa"]) / 2
        mid_on_seg = cur["on_segment"] or prev["on_segment"]
        if mid_twa > 0 and mid_on_seg:
            t_cross = prev["timestamp"] + (cur["timestamp"] - prev["timestamp"]) / 2
            if not start_events or (t_cross - start_events[-1]).total_seconds() > MIN_CROSSING_GAP_S:
                start_events.append(t_cross)

    if not start_events:
        return []

    # -----------------------------------------------------------------------
    # Detect T1 crossings  (extended line, port tack → TWA < 0)
    # -----------------------------------------------------------------------
    t1_events: list[pd.Timestamp] = []
    for i in range(1, len(df)):
        prev, cur = df.iloc[i - 1], df.iloc[i]
        if prev["side"] == cur["side"] or prev["side"] == 0 or cur["side"] == 0:
            continue
        mid_twa = (prev["twa"] + cur["twa"]) / 2
        if mid_twa < 0:
            t_cross = prev["timestamp"] + (cur["timestamp"] - prev["timestamp"]) / 2
            if not t1_events or (t_cross - t1_events[-1]).total_seconds() > MIN_CROSSING_GAP_S:
                t1_events.append(t_cross)

    # -----------------------------------------------------------------------
    # Detect T2 tacks  (TWA sign: negative → positive)
    # -----------------------------------------------------------------------
    t2_events: list[pd.Timestamp] = []
    for i in range(1, len(df)):
        prev, cur = df.iloc[i - 1], df.iloc[i]
        if prev["twa"] < 0 and cur["twa"] > 0:
            dt = (cur["timestamp"] - prev["timestamp"]).total_seconds()
            if dt < 10:  # filter out data gaps
                t_tack = prev["timestamp"] + (cur["timestamp"] - prev["timestamp"]) / 2
                if not t2_events or (t_tack - t2_events[-1]).total_seconds() > MIN_CROSSING_GAP_S:
                    t2_events.append(t_tack)

    # -----------------------------------------------------------------------
    # Group into practice starts
    # -----------------------------------------------------------------------
    results: list[PracticeStart] = []
    for idx, start_t in enumerate(start_events, start=1):
        # Most recent T2 before this start
        t2_candidates = [t for t in t2_events if t < start_t]
        t2 = t2_candidates[-1] if t2_candidates else None

        # Most recent T1 before T2 (or before start if no T2)
        cutoff = t2 if t2 is not None else start_t
        t1_candidates = [t for t in t1_events if t < cutoff]
        t1 = t1_candidates[-1] if t1_candidates else None

        results.append(PracticeStart(
            boat=boat,
            number=idx,
            start_time=start_t,
            t2_time=t2,
            t1_time=t1,
        ))

    return results


def summarise_starts(starts: list[PracticeStart]) -> pd.DataFrame:
    """Convert a list of PracticeStart objects to a display DataFrame."""
    rows = []
    for ps in starts:
        rows.append({
            "boat": ps.boat,
            "practice_start": f"PS {ps.number}",
            "start_time": ps.start_time,
            "T2 (s before)": round(ps.t2_delta, 1) if ps.t2_delta is not None else None,
            "T1 (s before)": round(ps.t1_delta, 1) if ps.t1_delta is not None else None,
        })
    return pd.DataFrame(rows)

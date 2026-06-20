"""
Start line crossing detection and practice start grouping.

All detection is vectorised with numpy — no nested Python loops.

Sequence per practice start:
  T1    → boat crosses the extended start line going outbound
  T2    → boat tacks/gybes (COG change > 60° over ≤ 30 s)
  Start → boat crosses near the line segment going inbound

Timings reported as seconds before the start crossing.
"""

import math
import numpy as np
import pandas as pd
from dataclasses import dataclass
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
        anchor = self.t1_time if self.t1_time is not None else self.start_time
        t_start = anchor - pd.Timedelta(seconds=pre_t1_s)
        t_end   = self.start_time + pd.Timedelta(seconds=post_start_s)
        return df[(df["timestamp"] >= t_start) & (df["timestamp"] <= t_end)].copy()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_GAP_S        = 20    # debounce — ignore events within this many seconds of each other
MIN_COG_CHANGE   = 60    # degrees of heading change to count as a tack
TACK_WINDOW_S    = 30    # seconds over which the COG change is measured
SEGMENT_BUFFER   = 0.5   # fraction of segment length beyond each end still counts as "on segment"
MAX_SEQUENCE_S   = 600   # T1 must be within 10 min before Start


# ---------------------------------------------------------------------------
# Geometry (vectorised)
# ---------------------------------------------------------------------------

def _to_xy(lat: np.ndarray, lon: np.ndarray, ref_lat: float, ref_lon: float):
    R = 6_371_000.0
    x = np.radians(lon - ref_lon) * R * math.cos(math.radians(ref_lat))
    y = np.radians(lat - ref_lat) * R
    return x, y


def _signed_dist_vec(px, py, ax, ay, bx, by) -> np.ndarray:
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return np.zeros(len(px))
    return ((px - ax) * dy - (py - ay) * dx) / length


def _along_frac_vec(px, py, ax, ay, bx, by) -> np.ndarray:
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return np.zeros(len(px))
    return ((px - ax) * dx + (py - ay) * dy) / seg_len_sq


# ---------------------------------------------------------------------------
# Crossing detection (vectorised)
# ---------------------------------------------------------------------------

def _detect_crossings(df: pd.DataFrame, ax, ay, bx, by) -> list[tuple]:
    """
    Return list of (timestamp, from_side, along_frac) for every line crossing.
    Crossings within MIN_GAP_S of each other are collapsed to one.
    """
    px = df["x"].values
    py = df["y"].values
    ts = df["timestamp"].values

    dist  = _signed_dist_vec(px, py, ax, ay, bx, by)
    along = _along_frac_vec(px, py, ax, ay, bx, by)
    side  = np.sign(dist)

    # Vectorised: find indices where side changes sign
    prev_s = side[:-1]
    cur_s  = side[1:]
    cross_idx = np.where(prev_s * cur_s < 0)[0]  # product < 0 ⟹ opposite non-zero signs

    crossings = []
    last_t = None

    for i in cross_idx:
        d1, d2 = abs(dist[i]), abs(dist[i + 1])
        frac   = d1 / (d1 + d2) if (d1 + d2) > 0 else 0.5

        t_cross    = pd.Timestamp(ts[i]) + (pd.Timestamp(ts[i + 1]) - pd.Timestamp(ts[i])) * frac
        along_cross = float(along[i] + (along[i + 1] - along[i]) * frac)
        from_side  = int(prev_s[i])

        # Debounce
        if last_t is not None and (t_cross - last_t).total_seconds() < MIN_GAP_S:
            continue

        crossings.append((t_cross, from_side, along_cross))
        last_t = t_cross

    return crossings


# ---------------------------------------------------------------------------
# Tack detection (vectorised)
# ---------------------------------------------------------------------------

def _detect_tacks(df: pd.DataFrame) -> list[pd.Timestamp]:
    """
    Return debounced list of tack timestamps using vectorised COG comparison.
    For each row i, compare COG to the row ~TACK_WINDOW_S seconds later.
    A tack is flagged where the change exceeds MIN_COG_CHANGE degrees.
    """
    if "cog" not in df.columns or df["cog"].notna().sum() < 10:
        return []

    cog = df["cog"].ffill().bfill().values
    ts  = df["timestamp"].values
    n   = len(cog)

    # Estimate median sample interval to convert seconds → rows
    dt_sec = pd.Series(
        (pd.to_datetime(ts[1:]) - pd.to_datetime(ts[:-1])) / pd.Timedelta(seconds=1)
    ).median()
    if pd.isna(dt_sec) or dt_sec <= 0:
        dt_sec = 1.0

    look = max(2, int(TACK_WINDOW_S / dt_sec))  # rows to look ahead

    if n <= look:
        return []

    cog_now   = cog[:n - look]
    cog_later = cog[look:]
    delta     = np.abs(((cog_later - cog_now + 180) % 360) - 180)

    # Tack index = midpoint of the look-ahead window
    tack_mask    = delta >= MIN_COG_CHANGE
    raw_indices  = np.where(tack_mask)[0]

    if len(raw_indices) == 0:
        return []

    # Use midpoint of each tack window as the tack timestamp
    mid = look // 2
    tack_ts = [pd.Timestamp(ts[min(i + mid, n - 1)]) for i in raw_indices]

    # Debounce: keep only tacks separated by MIN_GAP_S
    debounced, last_t = [], None
    for t in tack_ts:
        if last_t is None or (t - last_t).total_seconds() >= MIN_GAP_S:
            debounced.append(t)
            last_t = t

    return debounced


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_practice_starts(
    df: pd.DataFrame,
    sl1: tuple[float, float],
    sl2: tuple[float, float],
    boat: str,
) -> list[PracticeStart]:

    if df.empty or len(df) < 10:
        return []

    ref_lat = (sl1[0] + sl2[0]) / 2
    ref_lon = (sl1[1] + sl2[1]) / 2

    R = 6_371_000.0
    cos_ref = math.cos(math.radians(ref_lat))
    ax = math.radians(sl1[1] - ref_lon) * R * cos_ref
    ay = math.radians(sl1[0] - ref_lat) * R
    bx = math.radians(sl2[1] - ref_lon) * R * cos_ref
    by = math.radians(sl2[0] - ref_lat) * R

    df = df.copy().sort_values("timestamp").reset_index(drop=True)

    # Vectorised XY projection of all boat GPS
    xs, ys = _to_xy(df["latitude"].values, df["longitude"].values, ref_lat, ref_lon)
    df["x"] = xs
    df["y"] = ys

    crossings = _detect_crossings(df, ax, ay, bx, by)
    tacks     = _detect_tacks(df)

    if not crossings:
        return []

    # Separate crossings near the segment (start candidates) vs anywhere (T1 candidates)
    start_candidates = [c for c in crossings if -SEGMENT_BUFFER <= c[2] <= 1 + SEGMENT_BUFFER]

    results: list[PracticeStart] = []
    used: set = set()

    for c_time, c_from_side, _ in start_candidates:
        if c_time in used:
            continue

        # Most recent tack before this crossing
        prior_tacks = [t for t in tacks if t < c_time]
        if not prior_tacks:
            continue
        t2_time = prior_tacks[-1]

        # Most recent crossing in the opposite direction before the tack
        opposite = -c_from_side
        prior_t1 = [
            c for c in crossings
            if c[0] < t2_time
            and c[1] == opposite
            and (c_time - c[0]).total_seconds() <= MAX_SEQUENCE_S
        ]
        t1_time = prior_t1[-1][0] if prior_t1 else None

        results.append(PracticeStart(
            boat=boat,
            number=len(results) + 1,
            start_time=c_time,
            t2_time=t2_time,
            t1_time=t1_time,
        ))
        used.add(c_time)

    return results


def summarise_starts(starts: list[PracticeStart]) -> pd.DataFrame:
    return pd.DataFrame([{
        "boat": ps.boat,
        "practice_start": f"PS {ps.number}",
        "start_time": ps.start_time,
        "T2 (s before)": round(ps.t2_delta, 1) if ps.t2_delta is not None else None,
        "T1 (s before)": round(ps.t1_delta, 1) if ps.t1_delta is not None else None,
    } for ps in starts])

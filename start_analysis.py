"""
Start line crossing detection and practice start grouping.

Sequence per practice start:
  T1  → boat crosses the extended start line going outbound (away from pre-start area)
  T2  → boat tacks/gybes (large COG change, or TWA sign flip if available)
  Start → boat crosses the segment going inbound (back toward and through the line)

Detection is TWA-independent: crossings are classified by direction (which side
the boat came from), and tacks are detected by COG heading change.
TWA is used only when available to improve tack timing accuracy.

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
        t_end = self.start_time + pd.Timedelta(seconds=post_start_s)
        mask = (df["timestamp"] >= t_start) & (df["timestamp"] <= t_end)
        return df[mask].copy()


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _lat_lon_to_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    R = 6_371_000.0
    x = math.radians(lon - ref_lon) * R * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * R
    return x, y


def _signed_distance(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    return ((px - ax) * dy - (py - ay) * dx) / length


def _along_segment_fraction(px, py, ax, ay, bx, by) -> float:
    """Return t in [0,1] for the closest point on AB to P. <0 or >1 means beyond the ends."""
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return 0.0
    return ((px - ax) * dx + (py - ay) * dy) / seg_len_sq


def _cog_change(cog1: float, cog2: float) -> float:
    """Smallest signed angle change between two COG values (degrees)."""
    diff = (cog2 - cog1 + 180) % 360 - 180
    return diff


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

MIN_CROSSING_GAP_S = 20
MIN_TACK_COG_CHANGE = 60   # degrees — minimum heading change to count as a tack
MAX_TACK_DURATION_S = 30   # seconds — tack must complete within this window
MAX_START_SEQUENCE_S = 600 # seconds — T1 must be within 10 min before Start


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
    sl1_xy = _lat_lon_to_xy(sl1[0], sl1[1], ref_lat, ref_lon)
    sl2_xy = _lat_lon_to_xy(sl2[0], sl2[1], ref_lat, ref_lon)
    ax, ay = sl1_xy
    bx, by = sl2_xy
    seg_len = math.hypot(bx - ax, by - ay)

    df = df.copy().sort_values("timestamp").reset_index(drop=True)

    # Project to XY
    coords = [_lat_lon_to_xy(r.latitude, r.longitude, ref_lat, ref_lon)
              for r in df.itertuples()]
    df["x"] = [c[0] for c in coords]
    df["y"] = [c[1] for c in coords]

    # Signed distance to the infinite line through SL1→SL2
    df["dist"] = [_signed_distance(r.x, r.y, ax, ay, bx, by) for r in df.itertuples()]
    df["side"] = np.sign(df["dist"])

    # Fraction along the segment (negative = before SL1, >1 = beyond SL2)
    df["along"] = [_along_segment_fraction(r.x, r.y, ax, ay, bx, by) for r in df.itertuples()]

    # Check TWA availability
    twa_available = (
        "twa" in df.columns
        and df["twa"].notna().sum() > len(df) * 0.3  # at least 30% non-null
        and df["twa"].abs().max() > 1.0               # not all zeros
    )

    # -----------------------------------------------------------------------
    # Detect all line crossings
    # Each crossing: (time, from_side, along_fraction_at_crossing)
    # from_side = side the boat was on BEFORE crossing
    # -----------------------------------------------------------------------
    crossings = []  # (timestamp, from_side, along_frac, twa_at_crossing)

    for i in range(1, len(df)):
        prev, cur = df.iloc[i - 1], df.iloc[i]

        # Skip if same side, or if either point is exactly on the line
        if prev["side"] == cur["side"] or prev["side"] == 0 or cur["side"] == 0:
            continue

        # Interpolate crossing time and along-fraction
        d1, d2 = abs(prev["dist"]), abs(cur["dist"])
        frac = d1 / (d1 + d2) if (d1 + d2) > 0 else 0.5
        t_cross = prev["timestamp"] + (cur["timestamp"] - prev["timestamp"]) * frac
        along_cross = prev["along"] + (cur["along"] - prev["along"]) * frac

        # Debounce
        if crossings and (t_cross - crossings[-1][0]).total_seconds() < MIN_CROSSING_GAP_S:
            continue

        twa_val = (prev.get("twa", np.nan) + cur.get("twa", np.nan)) / 2 if twa_available else np.nan

        crossings.append((t_cross, int(prev["side"]), along_cross, twa_val))

    if not crossings:
        return []

    # -----------------------------------------------------------------------
    # Detect tacks / gybes
    # Primary method: large COG change over a short window
    # Secondary: TWA sign flip (negative → positive) if available
    # -----------------------------------------------------------------------
    tacks = []  # timestamps

    if "cog" in df.columns and df["cog"].notna().sum() > len(df) * 0.3:
        for i in range(1, len(df)):
            for j in range(i + 1, min(i + MAX_TACK_DURATION_S + 1, len(df))):
                dt = (df.iloc[j]["timestamp"] - df.iloc[i]["timestamp"]).total_seconds()
                if dt > MAX_TACK_DURATION_S:
                    break
                cog_delta = abs(_cog_change(df.iloc[i]["cog"], df.iloc[j]["cog"]))
                if cog_delta >= MIN_TACK_COG_CHANGE:
                    t_tack = df.iloc[i]["timestamp"] + (df.iloc[j]["timestamp"] - df.iloc[i]["timestamp"]) / 2
                    if not tacks or (t_tack - tacks[-1]).total_seconds() > MIN_CROSSING_GAP_S:
                        tacks.append(t_tack)
                    break

    # Supplement with TWA sign flips if available
    if twa_available:
        for i in range(1, len(df)):
            prev_twa = df.iloc[i - 1]["twa"]
            cur_twa = df.iloc[i]["twa"]
            if pd.isna(prev_twa) or pd.isna(cur_twa):
                continue
            if prev_twa < -5 and cur_twa > 5:
                dt = (df.iloc[i]["timestamp"] - df.iloc[i - 1]["timestamp"]).total_seconds()
                if dt < MAX_TACK_DURATION_S:
                    t_tack = df.iloc[i - 1]["timestamp"] + (df.iloc[i]["timestamp"] - df.iloc[i - 1]["timestamp"]) / 2
                    if not tacks or (t_tack - tacks[-1]).total_seconds() > MIN_CROSSING_GAP_S:
                        tacks.append(t_tack)

    tacks = sorted(set(tacks))

    # -----------------------------------------------------------------------
    # Classify crossings as start vs T1
    #
    # Strategy: a "start" crossing is one where the boat crosses near the
    # actual segment (along fraction roughly 0–1, with buffer). A practice
    # start sequence is: outbound crossing (T1) → tack (T2) → inbound
    # crossing near the segment (Start).
    #
    # "Near segment" = along fraction between -0.5 and 1.5
    # (i.e. within half a segment length of either end)
    # -----------------------------------------------------------------------
    SEGMENT_BUFFER = 0.5  # fraction of segment length beyond each end

    # Separate into near-segment crossings (start candidates) and extended crossings (T1 candidates)
    start_candidates = [c for c in crossings if -SEGMENT_BUFFER <= c[2] <= 1 + SEGMENT_BUFFER]
    t1_candidates_all = crossings  # T1 can be anywhere on extended line

    # A start candidate is valid if:
    # 1. There is a tack before it
    # 2. There is a prior crossing of the opposite direction (T1) before that tack
    results: list[PracticeStart] = []
    used_starts: set = set()

    for c_time, c_from_side, c_along, c_twa in start_candidates:
        if c_time in used_starts:
            continue

        # Find most recent tack before this crossing
        prior_tacks = [t for t in tacks if t < c_time]
        if not prior_tacks:
            continue
        t2_time = prior_tacks[-1]

        # Find most recent crossing of the OPPOSITE direction before the tack
        # (opposite direction = came from the other side)
        opposite_side = -c_from_side  # start came FROM c_from_side; T1 came FROM opposite
        prior_crossings = [
            c for c in t1_candidates_all
            if c[0] < t2_time
            and c[1] == opposite_side
            and (c_time - c[0]).total_seconds() <= MAX_START_SEQUENCE_S
        ]
        t1_crossing = prior_crossings[-1] if prior_crossings else None
        t1_time = t1_crossing[0] if t1_crossing else None

        results.append(PracticeStart(
            boat=boat,
            number=len(results) + 1,
            start_time=c_time,
            t2_time=t2_time,
            t1_time=t1_time,
        ))
        used_starts.add(c_time)

    return results


def summarise_starts(starts: list[PracticeStart]) -> pd.DataFrame:
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

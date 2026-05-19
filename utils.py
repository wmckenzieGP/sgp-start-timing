import math
import polars as pl
import scipy.stats
from typing import Optional
import numpy as np
import utm


def add_windward_leeward_metrics(
        df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Add windward and leeward metrics to the DataFrame.
    """
    port_channels = sorted([col for col in df.columns if 'port' in col])

    windward_leeward_expressions = []
    for port_channel in port_channels:
        stbd_channel = port_channel.replace('port', 'stbd')
        if stbd_channel in df.columns:
            windward_channel = port_channel.replace('port', 'windward')
            leeward_channel = port_channel.replace('port', 'leeward')

            # Create windward channel: starboard when twa > 0, port when twa <= 0
            windward_leeward_expressions.append(
                pl.when(pl.col('twa') > 0)
                .then(pl.col(stbd_channel))
                .otherwise(pl.col(port_channel))
                .alias(windward_channel)
            )

            # Create leeward channel: port when twa > 0, starboard when twa <= 0
            windward_leeward_expressions.append(
                pl.when(pl.col('twa') > 0)
                .then(pl.col(port_channel))
                .otherwise(pl.col(stbd_channel))
                .alias(leeward_channel)
            )

    # Apply all windward/leeward conversions at once
    if windward_leeward_expressions:
        df = df.with_columns(windward_leeward_expressions)
        return df

    else:
        print("No port/stbd channels found for windward/leeward conversion.")
        return df
    
    
def normalize_columns(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """
    Normalize specified columns in the DataFrame.
    """
    # Normalize the metrics by multiplying by the sign of the twa
    normalize_expressions = []
    for metric in columns:
        if metric in df.columns:
            normalize_expressions.append(
                (pl.col(metric) * pl.col('twa').sign()).alias(f"{metric}_n")
            )

    # Apply all normalizations at once
    if normalize_expressions:
        df = df.with_columns(normalize_expressions)

    # Multiply traveller with -1 to have the correct sign convention
    if 'traveller_n' in df.columns:
        df = df.with_columns([
            (pl.col('traveller_n') * -1).alias('traveller_n')
        ])

    return df


def plmean_expr(column_name: str, channel360=False):
    """
    Return a Polars expression for mean or circular mean.

    Args:
        column_name: Name of the column to calculate mean for
        channel360: If True, calculate circular mean for 360-degree data

    Returns:
        Polars expression
    """
    if channel360:
        # For circular mean, we need to use map_batches since it's not built into Polars
        return pl.col(column_name).map_batches(
            lambda s: pl.Series(
                [scipy.stats.circmean(s.drop_nulls().to_numpy(), high=360) if s.drop_nulls().len() > 0 else None])
        ).first()
    else:
        return pl.col(column_name).mean()
    
    
def calculate_target_percent(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate target percentage columns.
    """
    if 'tgt_vmg' in df.columns and 'vmg' in df.columns:
        df = df.with_columns([
            (pl.col('vmg').abs() / pl.col('tgt_vmg').abs() * 100.0).alias('tgt_vmg_percent')
        ])
    return df


def get_delta_t_df(
        df: pl.DataFrame,
        time_col: str = "timestamp",
        force_value_if_zero: float = 0.05
) -> float:
    """
    Compute the minimum time step (in seconds) from a datetime column in a Polars DF.
    Falls back to `force_value_if_zero` if it can't infer or if the result is zero.
    """
    try:
        # 1) diff() on a datetime column yields a Duration
        durations: pl.Series = df[time_col].diff().drop_nulls()
        
        print(durations)

        # 2) Convert duration to seconds based on time unit
        if durations.dtype == pl.Duration("us"):  # microseconds
            delta_us: Optional[int] = durations.cast(pl.Int64).median()
            delta_t = delta_us / 1e6 if delta_us else None  # microseconds to seconds
        elif durations.dtype == pl.Duration("ns"):  # nanoseconds
            delta_ns: Optional[int] = durations.cast(pl.Int64).median()
            delta_t = delta_ns / 1e9 if delta_ns else None  # nanoseconds to seconds
        elif durations.dtype == pl.Duration("ms"):  # milliseconds
            delta_ms: Optional[int] = durations.cast(pl.Int64).median()
            delta_t = delta_ms / 1e3 if delta_ms else None  # milliseconds to seconds
        else:
            # Fallback: convert to total seconds directly
            delta_t = durations.dt.total_seconds().median()

        if delta_t is None:
            raise ValueError(f"No valid diffs in '{time_col}'")

    except Exception as e:
        print(f"Failed to infer deltaT: {e}. Using default {force_value_if_zero}")
        delta_t = force_value_if_zero

    if delta_t == 0.0:
        print(f"deltaT cannot be zero, forcing to {force_value_if_zero}")
        delta_t = force_value_if_zero

    return delta_t


def calculate_angle_diff(angle1: float, angle2: float):
    """
    Calculate the smallest difference between two angles in degrees.
    Result is in the range [-180, 180].
    """
    diff = (angle2 - angle1 + 180) % 360 - 180
    return diff

def calculate_mean_angle(angles):
    """Circular mean of angles in degrees. Ignores None/NaN/Inf.
       Returns NaN if no valid angles remain or the mean direction is undefined.
    """
    # Coerce to float array (None -> NaN if possible)
    arr = np.asarray(angles, dtype=float)

    # Keep only finite values
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")  # or 0.0 to match your old behavior

    # Normalize to [0, 360) to be safe
    arr = np.mod(arr, 360.0)

    rad = np.deg2rad(arr)
    x = np.mean(np.cos(rad))
    y = np.mean(np.sin(rad))

    # If result vector length ~ 0 (e.g., symmetric angles), direction is undefined
    if np.hypot(x, y) < 1e-12:
        return float("nan")

    mean_deg = np.rad2deg(np.arctan2(y, x)) % 360.0
    return float(mean_deg)


def add_board_states(
        df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Add board state columns to the DataFrame.
    """
    df = df.with_columns([
        (pl.col('db_stow_state_port') == 5).alias('port_board_down'),
        (pl.col('db_stow_state_stbd') == 5).alias('stbd_board_down'),
        (pl.col('db_stow_state_stbd') == 1).alias('at_raised_position_stbd'),
        (pl.col('db_stow_state_port') == 1).alias('at_raised_position_port'),
        (pl.col('db_stow_state_port') == 1).alias('port_board_up'),
        (pl.col('db_stow_state_stbd') == 1).alias('stbd_board_up'),
        (pl.col('db_stow_state_port') == 4).alias('board_drop_port'),
        (pl.col('db_stow_state_stbd') == 4).alias('board_drop_stbd'),
    ])
    return df


def add_utm_pos(
    df: pl.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    *,
    drop_invalid: bool = True,
) -> pl.DataFrame:
    """
    Adds UTM coordinates (utm_pos_x, utm_pos_y) to a Polars DataFrame.

    A row is considered valid iff:
      - lat/lon are not null
      - -90 <= lat <= 90
      - -180 <= lon <= 180

    If drop_invalid=True, invalid rows are removed before conversion.
    If drop_invalid=False, invalid rows are retained and UTM outputs are null for them.
    """
    # Build validity mask in Polars (fast, null-safe)
    valid_expr = (
        pl.col(lat_col).is_not_null()
        & pl.col(lon_col).is_not_null()
        & pl.col(lat_col).is_between(-90.0, 90.0, closed="both")
        & pl.col(lon_col).is_between(-180.0, 180.0, closed="both")
    )

    if drop_invalid:
        df = df.filter(valid_expr)
        # If everything got filtered out, still add the columns and return
        if df.height == 0:
            return df.with_columns([
                pl.lit(None, dtype=pl.Float64).alias("utm_pos_x"),
                pl.lit(None, dtype=pl.Float64).alias("utm_pos_y"),
            ])

        # After filtering, all remaining rows are valid
        lat = df.get_column(lat_col).to_numpy()
        lon = df.get_column(lon_col).to_numpy()

        # utm.from_latlon returns: (easting, northing, zone_number, zone_letter)
        easting, northing, *_ = utm.from_latlon(lat, lon)

        return df.with_columns([
            pl.Series("utm_pos_x", easting.astype(float)),
            pl.Series("utm_pos_y", northing.astype(float)),
        ])

    # drop_invalid=False: keep rows, set invalid UTM values to null
    # Extract columns once
    lat = df.get_column(lat_col).to_numpy()
    lon = df.get_column(lon_col).to_numpy()

    # Compute validity mask in numpy as well (aligned with df order)
    # Note: we replicate bounds logic in numpy for direct indexing
    valid = (
        np.isfinite(lat) & np.isfinite(lon)
        & (lat >= -90.0) & (lat <= 90.0)
        & (lon >= -180.0) & (lon <= 180.0)
    )

    utm_x = np.full(df.height, np.nan, dtype=float)
    utm_y = np.full(df.height, np.nan, dtype=float)

    if valid.any():
        easting, northing, *_ = utm.from_latlon(lat[valid], lon[valid])
        utm_x[valid] = easting
        utm_y[valid] = northing

    # Convert NaN -> null in Polars by using Float64 and then replacing
    out = df.with_columns([
        pl.Series("utm_pos_x", utm_x).cast(pl.Float64),
        pl.Series("utm_pos_y", utm_y).cast(pl.Float64),
    ]).with_columns([
        pl.when(pl.col("utm_pos_x").is_nan()).then(None).otherwise(pl.col("utm_pos_x")).alias("utm_pos_x"),
        pl.when(pl.col("utm_pos_y").is_nan()).then(None).otherwise(pl.col("utm_pos_y")).alias("utm_pos_y"),
    ])

    return out


def ignore_imu_travel(df: pl.DataFrame, time_col: str = "timestamp") -> pl.DataFrame:
    EARTH_R = 6_371_000.0
    SPEED_LIM_MS = 35
    DIST_LIM_M   = 100_000

    df = df.sort(time_col)

    center = df.select(
        pl.col("latitude").median().alias("lat_c"),
        pl.col("longitude").median().alias("lon_c")
    ).to_dicts()[0]
    lat_c = math.radians(center["lat_c"])
    lon_c = math.radians(center["lon_c"])

    df = df.with_columns([
        pl.col("latitude").radians().alias("lat_rad"),
        pl.col("longitude").radians().alias("lon_rad"),
        pl.lit(lat_c).alias("latc_rad"),
        pl.lit(lon_c).alias("lonc_rad"),
    ])

    lat  = pl.col("lat_rad")
    lon  = pl.col("lon_rad")
    latc = pl.col("latc_rad")
    lonc = pl.col("lonc_rad")

    a_center = ((lat - latc) / 2).sin()**2 + lat.cos() * latc.cos() * ((lon - lonc) / 2).sin()**2

    a_center = a_center.clip(0.0, 1.0)
    dist_center_m = 2 * EARTH_R * a_center.sqrt().arcsin()

    dlat = lat - lat.shift(1)
    dlon = lon - lon.shift(1)
    a_seg = (dlat / 2).sin()**2 + lat.shift(1).cos() * lat.cos() * (dlon / 2).sin()**2
    a_seg = a_seg.clip(0.0, 1.0)
    seg_m = 2 * EARTH_R * a_seg.sqrt().arcsin()

    dt_s = pl.col(time_col).diff().dt.total_seconds()

    speed_m_s = pl.when(dt_s > 0).then(seg_m / dt_s).otherwise(None)

    df = df.with_columns([
        dist_center_m.alias("distance_from_center_m"),
        seg_m.alias("segment_m"),
        dt_s.alias("dt_s"),
        speed_m_s.alias("speed_m_s"),
    ])

    df = df.filter(
        (pl.col("distance_from_center_m").is_null() | (pl.col("distance_from_center_m") <= DIST_LIM_M))
        & (pl.col("speed_m_s").is_null() | (pl.col("speed_m_s") <= SPEED_LIM_MS))
    )

    return df.drop(["lat_rad", "lon_rad", "latc_rad", "lonc_rad", "segment_m", "dt_s", "speed_m_s", "distance_from_center_m"])


def rotate_xy_to_up(
    x,
    y,
    dir_deg,
    origin=(0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray]:

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x0, y0 = origin

    # translate to origin
    xt, yt = x - x0, y - y0

    # rotate by -dir to make `dir_deg` point to 0° (north/up)
    theta = np.deg2rad(dir_deg % 360.0)
    c, s = np.cos(-theta), np.sin(-theta)

    xr = c * xt - s * yt + x0
    yr = s * xt + c * yt + y0
    return xr, yr

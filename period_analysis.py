
import polars as pl
import datetime
import re
from typing import List
import utils as u

import datetime
import polars as pl


def label_straight_line(
    df: pl.DataFrame,
    min_speed_upwind: float = 30.0,
    min_speed_downwind: float = 30.0,
    max_yaw_rate: float = 15.0,
    datetime_col: str = "timestamp",
    smooth_window_s: float = 0.0,
    max_gap_s: float = 0.0,
) -> pl.DataFrame:
    if datetime_col not in df.columns:
        raise ValueError(f"'{datetime_col}' must exist to handle gaps robustly.")

    # Ensure time order
    df = df.sort(datetime_col)

    # Estimate sampling interval (seconds) robustly
    df = df.with_columns(
        pl.col(datetime_col).diff().dt.total_seconds().alias("_dt_s")
    )
    median_dt = (
        df.select(pl.col("_dt_s").drop_nulls().median())
        .item()
    )
    if median_dt is None or median_dt <= 0:
        # Fallback: assume 10 Hz if dt cannot be inferred
        median_dt = 0.1

    window_samples = max(1, int(round(smooth_window_s / median_dt)))

    # Smooth signals (median is good for spike rejection on yaw_rate)
    df = df.with_columns([
        pl.col("yaw_rate")
          .rolling_median(window_size=window_samples, center=True, min_periods=max(1, window_samples // 2))
          .alias("_yaw_rate_s"),
        pl.col("bsp")
          .rolling_mean(window_size=window_samples, center=True, min_periods=max(1, window_samples // 2))
          .alias("_bsp_s"),
        (pl.col("_dt_s") > max_gap_s).fill_null(True).alias("_is_gap"),
    ])

    # Straight-line detection (null-safe)
    df = df.with_columns([
        (pl.col("_yaw_rate_s").is_not_null() & (pl.col("_yaw_rate_s").abs() < max_yaw_rate)).alias("_stable_steering"),
        (pl.col("_bsp_s").is_not_null() & (pl.col("_bsp_s") >= min_speed_upwind) & (pl.col("twa_n").abs() < 80)).alias("_min_speed_upwind_met"),
        (pl.col("_bsp_s").is_not_null() & (pl.col("_bsp_s") >= min_speed_downwind) & (pl.col("twa_n").abs() >= 90)).alias("_min_speed_downwind_met"),
        (pl.col("_bsp_s").is_not_null() & (pl.col("_bsp_s") >= min(min_speed_upwind, min_speed_downwind)) & (pl.col("twa_n").abs() >= 80) & (pl.col("twa_n").abs() < 90)).alias("_min_speed_reaching_met"),
    ]).with_columns([
        (
            pl.col("_stable_steering")
            & (
                pl.col("_min_speed_upwind_met")
                | pl.col("_min_speed_downwind_met")
                | pl.col("_min_speed_reaching_met")
            )
            & pl.col("leeward_board_down")
            & pl.col("windward_board_up")
            & (~pl.col("_is_gap"))            # never label straight_line across a gap
        ).alias("straight_line")
    ])
    
    # Filter the dataframe where straight_line is True and twa_n > 90
    dw_df = df.filter(
        (pl.col("straight_line") == True) & (pl.col("twa_n").abs() >= 90)
    )
    upw_df = df.filter(
        (pl.col("straight_line") == True) & (pl.col("twa_n").abs() < 80)
    )
    print(f"Downwind periods count: {dw_df.height}")
    print(f"Upwind periods count: {upw_df.height}")

    cols_to_drop = [
        "_dt_s", "_yaw_rate_s", "_bsp_s", "_is_gap", "_stable_steering",
        "_min_speed_upwind_met", "_min_speed_downwind_met", "_min_speed_reaching_met",
        "_min_speed_met",
    ]
    cols_to_drop = [col for col in cols_to_drop if col in df.columns]
    return df.drop(cols_to_drop)


import polars as pl

def compute_auto_periods(
    df: pl.DataFrame,
    auto_period_duration: float = 6.0,
    max_twa_range: float = 25.0,
    datetime_col: str = "timestamp",
    max_gap_s: float = 5.0,
    min_samples_per_window: int | None = None,  # optional
) -> pl.DataFrame:

    if df.height == 0:
        return pl.DataFrame()

    required = {"straight_line", "twa", datetime_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.sort(datetime_col)

    # Split on gaps
    df = df.with_columns([
        pl.col(datetime_col).diff().dt.total_seconds().alias("_dt_s"),
        (pl.col(datetime_col).diff().dt.total_seconds() > max_gap_s).fill_null(True).alias("_is_gap"),
    ])

    # Split on straight_line change OR gap
    df = df.with_columns([
        (
            pl.col("straight_line").ne(pl.col("straight_line").shift(1)) | pl.col("_is_gap")
        ).fill_null(True).cum_sum().alias("_group_id")
    ])

    # Aggregate consecutive straight_line=True runs
    segments = (
        df.filter(pl.col("straight_line") == True)
          .group_by("_group_id")
          .agg([
              pl.col(datetime_col).min().alias("seg_start"),
              pl.col(datetime_col).max().alias("seg_end"),
              pl.col("twa").mean().alias("twa_mean"),
              pl.col("twa_n").min().alias("twa_abs_min"),
              pl.col("twa_n").max().alias("twa_abs_max"),
              pl.len().alias("n_samples"),
          ])
          .with_columns([
              (pl.col("seg_end") - pl.col("seg_start")).dt.total_seconds().alias("duration_s"),
              (pl.col("twa_abs_max") - pl.col("twa_abs_min")).alias("twa_range"),
          ])
    )

    if segments.height == 0:
        return pl.DataFrame()
    
    # Print upwind and downwind segment counts
    upwind_segments = segments.filter(pl.col("twa_mean").abs() < 75)
    downwind_segments = segments.filter(pl.col("twa_mean").abs() >= 120)
    reaching_segments = segments.filter((pl.col("twa_mean").abs() >= 75) & (pl.col("twa_mean").abs() < 120))
    print(f"Upwind segments count: {upwind_segments.height}")
    print(f"Downwind segments count: {downwind_segments.height}")
    print(f"Reaching segments count: {reaching_segments.height}")

    # Filter segments (optional: keep your twa_range filter if desired)
    valid = (
        segments
        .with_columns([
            (pl.col("duration_s") / auto_period_duration).floor().cast(pl.Int32).alias("n_windows")
        ])
        .filter(pl.col("n_windows") >= 1)
        .select(["_group_id", "seg_start", "seg_end", "twa_mean", "n_windows"])
    )

    if valid.height == 0:
        return pl.DataFrame()

    # Expand into windows
    windows = (
        valid
        .with_columns(pl.int_ranges(0, pl.col("n_windows")).alias("_i"))
        .explode("_i")
        .with_columns([
            (pl.col("seg_start") + pl.duration(seconds=(pl.col("_i") * auto_period_duration))).alias("timestamp"),
        ])
        .with_columns([
            (pl.col("timestamp") + pl.duration(seconds=auto_period_duration)).alias("end"),
        ])
        # Safety: ensure window is fully inside the segment
        .filter(pl.col("end") <= pl.col("seg_end"))
        .with_columns([
            (pl.col("twa_mean").abs() <= 75).alias("upwind"),
            (pl.col("twa_mean").abs() >= 120).alias("downwind"),
            ((pl.col("twa_mean").abs() > 75) & (pl.col("twa_mean").abs() < 120)).alias("reaching"),
            pl.when(pl.col("twa_mean") > 0).then(pl.lit("starboard")).otherwise(pl.lit("port")).alias("tack"),
        ])
        
        .select(["timestamp", "end", "upwind", "downwind", "reaching", "tack"])
        .with_row_index("period_id")
    )

    if min_samples_per_window is not None and min_samples_per_window > 0 and windows.height > 0:
        df_small = df.select([datetime_col, "straight_line"])
        windows = (
            windows
            .join(
                df_small,
                how="cross"
            )
        )
        raise NotImplementedError(
            "If you need min_samples_per_window, tell me your df sizes; "
            "I’ll give you an efficient asof/join-based approach."
        )

    return windows



def assign_period_col(df: pl.DataFrame, periods_df: pl.DataFrame, period_channel_name='PeriodID',
                           timestamp_col: str = "timestamp") -> pl.DataFrame:
    """
    More efficient version using interval joins (requires timestamp-based periods).
    """
    df_sorted = df.sort(timestamp_col)
    periods_sorted = periods_df.sort("timestamp")

    result_df = df_sorted.join_asof(
        periods_sorted,
        left_on=timestamp_col,
        right_on="timestamp",
        strategy="backward"
    ).filter(
        pl.col(timestamp_col) <= pl.col("end")
    )

    all_rows = df_sorted.join(
        result_df.select([timestamp_col, period_channel_name]),
        on=timestamp_col,
        how="left"
    )

    return all_rows

def compute_period_metrics(
    df: pl.DataFrame,
    periods_df: pl.DataFrame,
    cols_360: set,
    period_channel_name: str = "period_id",
    agg_functions: List[str] = ("mean", "std", "min", "max", "total_var"),
) -> pl.DataFrame:
    """
    Adds AAV (= mean absolute successive difference) for selected columns per period.
    """
    if periods_df is None or periods_df.is_empty():
        return pl.DataFrame()
    tmp_df = assign_period_col(df, periods_df, period_channel_name=period_channel_name)

    tmp_df = tmp_df.fill_nan(None)
    
    # Get mean period duration
    mean_period_duration = (periods_df['end'] - periods_df['timestamp']).dt.total_seconds().mean()

    if 'timestamp' in tmp_df.columns:
        tmp_df = tmp_df.sort([period_channel_name, 'timestamp'])

    agg_expressions: List[pl.Expr] = []

    skip_cols = {'tgt', 'utm', 'latitude', 'longitude'}

    # Build standard aggregations
    for col in tmp_df.columns:
        if col == period_channel_name:
            continue
        if tmp_df[col].dtype not in (
            pl.Int8, pl.Int16, pl.Int32, pl.Int64,
            pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
            pl.Float32, pl.Float64
        ):
            continue

        is_circular = col in cols_360

        if "mean" in agg_functions:
            agg_expressions.append(u.plmean_expr(col, channel360=is_circular).alias(f"{col}_mean"))

        if "std" in agg_functions:
            if any(skip in col for skip in skip_cols):
                continue
            agg_expressions.append(pl.col(col).std().alias(f"{col}_std"))

        if "min" in agg_functions:
            if any(skip in col for skip in skip_cols):
                continue
            agg_expressions.append(pl.col(col).nan_min().alias(f"{col}_min"))

        if "max" in agg_functions:
            if any(skip in col for skip in skip_cols):
                continue
            agg_expressions.append(pl.col(col).nan_max().alias(f"{col}_max"))

        if "total_var" in agg_functions:
            if any(skip in col for skip in skip_cols):
                continue
            agg_expressions.append((pl.col(col).diff().abs().sum() / mean_period_duration).alias(f"{col}_total_var"))

    if agg_expressions:
        try:
            aggregated_df = tmp_df.group_by(period_channel_name).agg(agg_expressions)
        except Exception as e:
            print(f"Error during aggregation: {str(e)}")
            return periods_df
        periods_calc_df = periods_df.join(aggregated_df, on=period_channel_name, how="left")
    else:
        periods_calc_df = periods_df

    # Remove any periods with less than 10kts vmg_mean
    if 'vmg_mean' in periods_calc_df.columns:
        periods_calc_df = periods_calc_df.filter(pl.col('vmg_mean') >= 10.0)

    # Apply filtering score
    periods_calc_df = apply_filtering_score(periods_calc_df)

    return periods_calc_df


def apply_filtering_score(periods_df: pl.DataFrame) -> pl.DataFrame:
    """
    Create a per-row filter_score computed within each period type's distribution.

    - For each period type (boolean column), compute min/max as the 5th/95th quantiles
      of the chosen metric *within that subset*.
    - Score is scaled to [0, 100] within that range.
    - Rows not belonging to any known period type get null score.
    """
    if periods_df is None or periods_df.is_empty():
        return pl.DataFrame()

    # Which metric column to score for each period type
    period_metric = {
        "upwind": "tgt_vmg_percent_mean",
        "downwind": "tgt_vmg_percent_mean",
        "reaching": "bsp_mean",          # <-- this is what your code *seemed* to intend
        # add more here if needed
    }

    # Start with null score; we’ll fill it conditionally per period type
    score_expr = pl.lit(None, dtype=pl.Float64)

    for period_type, metric_col in period_metric.items():
        if period_type not in periods_df.columns:
            continue
        if metric_col not in periods_df.columns:
            continue

        subset = periods_df.filter(pl.col(period_type) == True).select(metric_col)

        if subset.height == 0:
            continue

        minv = subset.select(pl.col(metric_col).quantile(0.05)).item()
        maxv = subset.select(pl.col(metric_col).quantile(0.95)).item()

        # If quantiles are null (all nulls) skip
        if minv is None or maxv is None:
            continue

        den = maxv - minv

        if abs(den) <= 1e-12:
            raw = pl.lit(100.0)
        else:
            raw = ((pl.col(metric_col) - pl.lit(minv)) / pl.lit(den)) * 100.0

        # Optional: clamp to [0, 100]
        raw = raw.clip(0.0, 100.0)

        # Only apply score to rows of this period type; otherwise keep prior score
        score_expr = (
            pl.when(pl.col(period_type) == True)
              .then(raw.cast(pl.Float64))
              .otherwise(score_expr)
        )

    return periods_df.with_columns(score_expr.alias("filter_score"))

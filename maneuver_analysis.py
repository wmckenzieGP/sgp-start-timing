import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

import datetime
import polars as pl
import numpy as np
from typing import Optional, List, Union, Tuple
import utils as u
import pandas as pd
import re

def get_clean_htw_times(
        df: pl.DataFrame,
        time_col: str = "timestamp",
        debug: bool = False,
) -> Union[List[str], pl.DataFrame]:

    min_speed = 20
    min_delta = 10
    interval = 1

    # infer how many rows correspond to interval seconds
    delta_t = u.get_delta_t_df(df, time_col=time_col)
    fake_steps = int(interval / delta_t)

    # Add row index to preserve original position
    df = df.with_row_index("_original_idx")

    # define each filter as an expression
    zero_cross = (pl.col("twa").sign().diff().abs() > 0)
    speed_ok = (pl.col("bsp") > min_speed)
    not_fake = (
            pl.col("twa").shift(-fake_steps).sign()
            != pl.col("twa").shift(fake_steps).sign()
    )

    # Apply base filters
    base_filters = zero_cross & speed_ok & not_fake

    # Get potential maneuvers with their original indices
    potential_maneuvers = df.filter(base_filters).select([
        pl.col("_original_idx"),
        pl.col(time_col).alias("timestamp"),
        pl.col("twa"),
        pl.col("bsp"),
    ])

    if debug:
        print("zero_cross:", df.filter(zero_cross).height)
        print("speed_ok:", df.filter(zero_cross & speed_ok).height)
        print("not_fake:", df.filter(base_filters).height)

    # Handle empty result after board check
    if len(potential_maneuvers) == 0:
        if debug:
            print("No maneuvers found after filters!")
        empty_df = pl.DataFrame({
            "timestamp": [],
            "entry_tack": [],
            "maneuver_type": [],
            "maneuver_id": []
        }, schema={
            "timestamp": pl.Datetime,
            "entry_tack": pl.Utf8,
            "maneuver_type": pl.Utf8,
            "maneuver_id": pl.Int64
        })
        return empty_df

    # Calculate time differences between consecutive maneuvers
    delta_secs_expr = (
        pl.col("timestamp")
        .diff()
        .dt.total_seconds()
        .fill_null(min_delta + 1)
        .alias("delta_times")
    )

    maneuvers_with_delta = potential_maneuvers.with_columns([delta_secs_expr])

    if debug:
        print(f"time_ok: {maneuvers_with_delta.filter(pl.col('delta_times') > min_delta).height}")
        debug_df = maneuvers_with_delta.select(["timestamp", "delta_times"])
        print(debug_df)

    # Apply time filter
    df2 = maneuvers_with_delta.filter(pl.col("delta_times") > min_delta)

    if len(df2) == 0:
        if debug:
            print("No maneuvers found after time filter!")
        empty_df = pl.DataFrame({
            "timestamp": [],
            "entry_tack": [],
            "maneuver_type": [],
            "maneuver_id": []
        }, schema={
            "timestamp": pl.Datetime,
            "entry_tack": pl.Utf8,
            "maneuver_type": pl.Utf8,
            "maneuver_id": pl.Int64
        })
        return empty_df

    classification_indices = df2["_original_idx"].to_numpy().astype(np.int64)
    twa_before_indices = np.maximum(classification_indices - fake_steps, 0)

    twa_before = df["twa"].gather(twa_before_indices).to_numpy()

    # Classify tack/gybe based on TWA before maneuver
    entry_tack = ["Stbd" if twa > 0 else "Port" for twa in twa_before]
    maneuver_type = ["Tack" if abs(twa) < 90 else "Gybe" for twa in twa_before]

    # Add classifications
    df2 = df2.with_columns([
        pl.Series("entry_tack", entry_tack),
        pl.Series("maneuver_type", maneuver_type),
    ])

    # Assign IDs per maneuver type
    df2 = df2.with_columns([
        pl.arange(0, pl.count())
        .alias("maneuver_id")
    ])

    if debug:
        print(f"\nFinal maneuvers: {df2.height}")
        if len(df2) > 0:
            summary = df2.group_by("maneuver_type").agg([
                pl.count().alias("count")
            ])
            print(f"Maneuver summary: {summary}")

    # Final selection
    return df2.select(["timestamp", "entry_tack", "maneuver_type", "maneuver_id"])


def compute_maenuver_metrics_v2(
        df: pl.DataFrame,
        htw_df: Optional[pl.DataFrame] = None
) -> Optional[pl.DataFrame]:
    """
    Computes tack and gybe metrics using Polars.

    Args:
        df: Main DataFrame with sailing data and timestamp column
        htw_df: DataFrame from get_clean_htw_times containing HTW times

    Returns:
        DataFrame with performance metrics and metadata for each maneuver
    """
    tack_interval_times = [-10, -5, 5, 15]
    gybe_interval_times = [-10, -5, 5, 15]
    wind_mean_interval = [-10, 10]

    if htw_df is None or htw_df.is_empty():
        return None

    print(f"Computing metrics for {len(htw_df)} maneuvers...")

    result_dicts = []

    # Process each HTW time
    for row_idx in range(len(htw_df)):
        try:
            row = htw_df.row(row_idx, named=True)
            time_index = row['timestamp']
            entry_tack = row['entry_tack']
            maneuver_type = row['maneuver_type']

            interval = tack_interval_times if maneuver_type == 'Tack' else gybe_interval_times

            # Create time window for analysis
            start_time = time_index + datetime.timedelta(seconds=interval[0])
            investment_end_time = time_index + datetime.timedelta(seconds=interval[1])
            maneuver_end_time = time_index + datetime.timedelta(seconds=interval[2])
            end_time = time_index + datetime.timedelta(seconds=interval[3])

            # Create sub dataframes for different phases
            total_df = df.filter(
                (pl.col("timestamp") >= start_time) &
                (pl.col("timestamp") <= end_time)
            )

            investment_df = df.filter(
                (pl.col("timestamp") >= start_time) &
                (pl.col("timestamp") <= investment_end_time)
            )

            maneuver_df = df.filter(
                (pl.col("timestamp") >= investment_end_time) &
                (pl.col("timestamp") <= maneuver_end_time)
            )

            acceleration_df = df.filter(
                (pl.col("timestamp") >= maneuver_end_time) &
                (pl.col("timestamp") <= end_time)
            )

            wind_avg_df = df.filter(
                (pl.col("timestamp") >= time_index + datetime.timedelta(seconds=wind_mean_interval[0])) &
                (pl.col("timestamp") <= time_index + datetime.timedelta(seconds=wind_mean_interval[1]))
            )

            before_htw_df = df.filter(
                (pl.col('timestamp') >= start_time) &
                (pl.col('timestamp') <= time_index)
            )

            after_htw_df = df.filter(
                (pl.col('timestamp') >= time_index) &
                (pl.col('timestamp') <= end_time)
            )

            two_boards_df = total_df.filter(
                (pl.col('timestamp') >= investment_end_time) &
                (pl.col('db_stow_state_port') == 4) &
                (pl.col('db_stow_state_stbd') == 4) &
                (pl.col('timestamp') <= end_time)
            )

            if total_df.is_empty() or investment_df.is_empty() or maneuver_df.is_empty() or acceleration_df.is_empty():
                print(f"No data found for maneuver at {time_index}")
                continue
        
        except Exception as e:
            print(f"Error processing maneuver at index {row_idx}: {e}")
            continue

        # Initialize result dictionary
        result = {'timestamp': time_index, 'maneuver_type': maneuver_type, 'entry_tack': entry_tack}

        # Calculate total maneuver angle
        initial_cog = investment_df.select(pl.col('cog').mean()).item(0, 0)
        final_cog = acceleration_df.select(pl.col('cog').mean()).item(0, 0)
        result['maneuver_angle'] = abs(u.calculate_angle_diff(initial_cog, final_cog))

        if 'twd' and 'tws' in df.columns and not wind_avg_df.is_empty():
            result['mean_tws'] = wind_avg_df.select(pl.col('tws').mean()).item(0, 0)
            # For circular mean of angles, you might want to use a proper circular mean function
            result['mean_twd'] = u.calculate_mean_angle(wind_avg_df.select(pl.col('twd')).to_series().to_list())
        else:
            result['mean_tws'] = 0.0
            result['mean_twd'] = 0.0

        if entry_tack == 'Stbd':
            new_foil_channel = 'stbd'
            old_foil_channel = 'port'
        elif entry_tack == 'Port':
            new_foil_channel = 'port'
            old_foil_channel = 'stbd'
        else:
            print(f"Unknown entry_tack '{entry_tack}' at index {row_idx}")
            continue

        new_board_drop_push_button_time = None
        if f'board_drop_{new_foil_channel}' in df.columns:
            # Get first True value in board_drop_{new_foil_channel}
            drop_data = before_htw_df.filter(pl.col(f'board_drop_{new_foil_channel}') == 1)
            if len(drop_data) > 0:
                drop_time = drop_data.select('timestamp').item(0, 0)
                new_board_drop_push_button_time = drop_time
            else:
                print(f"No board drop event found for {new_foil_channel} before HTW at {time_index}")
                new_board_drop_push_button_time = None

        if 'at_raised_position_stbd' in df.columns and 'at_raised_position_port' in df.columns:
            old_foil_raised_data = total_df.filter(
                (pl.col('timestamp') >= time_index) &
                (pl.col(f'at_raised_position_{old_foil_channel}') == 1) &
                (pl.col('timestamp') <= end_time)
            )
            new_foil_raise_data = total_df.filter(
                (pl.col('timestamp') >= start_time) &
                (pl.col(f'at_raised_position_{new_foil_channel}') == 1) &
                (pl.col('timestamp') <= time_index)
            )

            if len(old_foil_raised_data) > 0:
                old_foil_raised_time = old_foil_raised_data.select('timestamp').item(0, 0)
            else:
                old_foil_raised_time = None
            if len(new_foil_raise_data) > 0:
                new_foil_raised_time = new_foil_raise_data.select('timestamp').item(-1, 0)
            else:
                new_foil_raised_time = None
        else:
            old_foil_raised_time = None
            new_foil_raised_time = None

        result['min_bsp'] = total_df.select(pl.col('bsp').min()).item(0, 0)
        result['exit_twa_range'] = acceleration_df['twa_n'].abs().max() - acceleration_df['twa_n'].abs().min()
        result['entry_twa_range'] = investment_df['twa_n'].abs().max() - investment_df['twa_n'].abs().min()

        if old_foil_raised_time is not None and new_foil_raised_time is not None:
            drop_data = df.filter(pl.col('timestamp') == new_foil_raised_time)
            raise_data = df.filter(pl.col('timestamp') == old_foil_raised_time)
            result['entry_bsp'] = drop_data.select('bsp').item(0, 0)
            result['exit_bsp'] = raise_data.select('bsp').item(0, 0)
            result['delta_bsp'] = result['min_bsp'] - result['entry_bsp']
            result['entry_twa'] = abs(drop_data.select('twa').item(0, 0))
            result['exit_twa'] = abs(raise_data.select('twa').item(0, 0))
        else:
            result['entry_bsp'] = None
            result['exit_bsp'] = None
            result['delta_bsp'] = None
            result['entry_twa'] = None
            result['exit_twa'] = None

        if len(two_boards_df) > 0:
            start_two_boards_time = two_boards_df.select('timestamp').item(0, 0)
            end_two_boards_time = two_boards_df.select('timestamp').item(-1, 0)
        else:
            # If no two boards period found, use default times
            start_two_boards_time = time_index + datetime.timedelta(seconds=-5)
            end_two_boards_time = time_index + datetime.timedelta(seconds=5)


        result['start_two_boards'] = start_two_boards_time
        result['end_two_boards'] = end_two_boards_time
        result['time_two_boards'] = (end_two_boards_time - start_two_boards_time).total_seconds()

        if 'foil_leeward_sink' and 'foil_windward_sink' in df.columns:
            result['old_foil_sink_min'] = before_htw_df.select(pl.col(f'foil_leeward_sink').min()).item(0, 0)
            result['old_foil_sink_max'] = before_htw_df.select(pl.col(f'foil_leeward_sink').max()).item(0, 0)
            result['new_foil_sink_min'] = after_htw_df.select(pl.col(f'foil_leeward_sink').min()).item(0, 0)
            result['new_foil_sink_max'] = after_htw_df.select(pl.col(f'foil_leeward_sink').max()).item(0, 0)
        else:
            result['min_leeward_sink_entry'] = None
            result['min_leeward_sink_exit'] = None
            result['min_foil_sink_maneuver'] = None

        max_rudder_angle = maneuver_df.select(pl.col('rudder_angle').abs().max()).item(0, 0)
        result['max_rudder_angle'] = max_rudder_angle

        drop_data = df.filter(pl.col('timestamp') == new_board_drop_push_button_time)
        
        # Use existing target columns from the DataFrame
        result['period_bsp_tgt'] = total_df.select(pl.col('tgt_bsp').mean()).item(0, 0)
        result['period_vmg_tgt'] = total_df.select(pl.col('tgt_vmg').abs().mean()).item(0, 0)
        result['period_twa_tgt'] = total_df.select(pl.col('tgt_twa_n').mean()).item(0, 0)

        result['delta_bsp_tgt'] = result['min_bsp'] - result['period_bsp_tgt']

        # Calculate overshoot angle
        maximum_acceleration_twa = acceleration_df.select(pl.col('twa_n').max()).item(0, 0)
        result['overshoot_angle'] = maximum_acceleration_twa - abs(result['period_twa_tgt'])

        # Calculate loss metrics
        start_pos = df.with_columns(
            (pl.col('timestamp') - start_time).abs().alias("diff")
        ).sort("diff").head(1).drop("diff")

        end_pos = df.with_columns(
            (pl.col('timestamp') - end_time).abs().alias("diff")
        ).sort("diff").head(1).drop("diff")

        start_man_pos = df.with_columns(
            (pl.col('timestamp') - investment_end_time).abs().alias("diff")
        ).sort("diff").head(1).drop("diff")

        end_man_pos = df.with_columns(
            (pl.col('timestamp') - maneuver_end_time).abs().alias("diff")
        ).sort("diff").head(1).drop("diff")

        if (not start_pos.is_empty() and not end_pos.is_empty() and
                not start_man_pos.is_empty() and 'utm_pos_x' in df.columns):

            # Get positions
            start_x = start_pos.select('utm_pos_x').item(0, 0)
            start_y = start_pos.select('utm_pos_y').item(0, 0)
            start_man_x = start_man_pos.select('utm_pos_x').item(0, 0)
            start_man_y = start_man_pos.select('utm_pos_y').item(0, 0)
            end_man_x = end_man_pos.select('utm_pos_x').item(0, 0)
            end_man_y = end_man_pos.select('utm_pos_y').item(0, 0)
            end_x = end_pos.select('utm_pos_x').item(0, 0)
            end_y = end_pos.select('utm_pos_y').item(0, 0)

            # Calculate actual distances
            total_distance = np.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)

            # Calculate distance in wind direction (upwind component)
            wind_rad = np.deg2rad(result['mean_twd'])

            if maneuver_type == 'Gybe':
                wind_rad = (wind_rad + np.pi) % (2 * np.pi)  # Adjust for gybe
            total_distance_y = (np.sin(wind_rad) * (end_x - start_x) +
                                np.cos(wind_rad) * (end_y - start_y))
            investment_distance_y = (np.sin(wind_rad) * (start_man_x - start_x) +
                                     np.cos(wind_rad) * (start_man_y - start_y))
            maneuver_distance_y = (np.sin(wind_rad) * (end_man_x - start_man_x) +
                                   np.cos(wind_rad) * (end_man_y - start_man_y))
            acceleration_distance_y = (np.sin(wind_rad) * (end_x - end_man_x) +
                                       np.cos(wind_rad) * (end_y - end_man_y))

            # Calculate ghost boat distances using target VMG
            total_time_s = (end_time - start_time).total_seconds()
            investment_time_s = (investment_end_time - start_time).total_seconds()
            maneuver_time_s = (maneuver_end_time - investment_end_time).total_seconds()
            acceleration_time_s = (end_time - maneuver_end_time).total_seconds()

            # Convert VMG from knots to m/s
            vmg_ms = result['period_vmg_tgt'] * 1852 / 3600

            total_ghost_distance_y = total_time_s * vmg_ms
            investment_ghost_distance_y = investment_time_s * vmg_ms
            maneuver_ghost_distance_y = maneuver_time_s * vmg_ms
            acceleration_ghost_distance_y = acceleration_time_s * vmg_ms

            result['total_loss_m'] = total_distance_y - total_ghost_distance_y
            result['investment_loss_m'] = investment_distance_y - investment_ghost_distance_y
            result['maneuver_loss_m'] = maneuver_distance_y - maneuver_ghost_distance_y
            result['acceleration_loss_m'] = acceleration_distance_y - acceleration_ghost_distance_y

            # Store distances for reference
            result['total_distance'] = total_distance
            result['total_distance_y'] = total_distance_y
            result['investment_distance_y'] = investment_distance_y
            result['maneuver_distance_y'] = maneuver_distance_y
            result['acceleration_distance_y'] = acceleration_distance_y

        else:
            result['total_loss_m'] = 0.0
            result['investment_loss_m'] = 0.0
            result['maneuver_loss_m'] = 0.0
            result['total_distance'] = 0.0
            result['total_distance_y'] = 0.0
            result['investment_distance_y'] = 0.0
            result['maneuver_distance_y'] = 0.0
            result['acceleration_loss_m'] = 0.0
            result['acceleration_distance_y'] = 0.0

        # Convert losses to time (optional - requires target speed)
        vmg_ms = result['period_vmg_tgt'] * 1852 / 3600
        result['total_loss_s'] = result['total_loss_m'] / vmg_ms if vmg_ms > 0 else 0.0
        result['investment_loss_s'] = result['investment_loss_m'] / vmg_ms if vmg_ms > 0 else 0.0
        result['maneuver_loss_s'] = result['maneuver_loss_m'] / vmg_ms if vmg_ms > 0 else 0.0
        result['acceleration_loss_s'] = result['acceleration_loss_m'] / vmg_ms if vmg_ms > 0 else 0.0

        if 'yaw_rate' in df.columns:
            result['max_yaw_rate'] = maneuver_df.select(pl.col('yaw_rate').abs().max()).item(0, 0)
        else:
            result['max_yaw_rate'] = 0.0

        if 'hull_altitude' in df.columns:
            sink_data = maneuver_df.filter(pl.col('hull_altitude') < 0)
            total_points = len(maneuver_df)
            touch_points = len(sink_data)
            result['flying_percent'] = (1 - (touch_points / total_points)) * 100 if total_points > 0 else 0.0
            result['mean_hull_altitude'] = maneuver_df.select(pl.col('hull_altitude').mean()).item(0, 0)
        else:
            result['flying_percent'] = 0.0
            result['mean_hull_altitude'] = None

        # Add max leeway during turn
        if 'leeway' in df.columns:
            result['max_leeway'] = maneuver_df.select(pl.col('leeway').abs().max()).item(0, 0)
        else:
            result['max_leeway'] = None

        # Add mean turn trim
        if 'trim' in df.columns:
            result['mean_turn_trim'] = maneuver_df.select(pl.col('trim').mean()).item(0, 0)
        else:
            result['mean_turn_trim'] = None

        result_dicts.append(result)

    maneuvers_df = pl.DataFrame(result_dicts)
    
    if maneuvers_df.is_empty():
        return None

    # Redo maneuver ids by cumulating over maneuver_type
    maneuvers_df = maneuvers_df.sort('timestamp')
    maneuvers_df = maneuvers_df.with_columns([
        pl.int_range(pl.len()).over('maneuver_type').add(1).alias('maneuver_id')
    ])

    # Apply filtering score
    maneuvers_df = apply_filtering_score_v2(maneuvers_df)

    return maneuvers_df


def get_single_timeseries(
        df: pl.DataFrame,
        maneuver_id: int,
        maneuver_type: str,
        timing_data: dict,
        entry_tack: str,
        window_s_pre: float,
        window_s_post: float,
        reference_twd: float,
        center_time_col: str,
        boat: str = "No Data",
        crew: str = "No Data",
        sails: str = "No Data",
        timestamp_col: str = 'timestamp',
        utm_x_col: str = 'utm_pos_x',
        utm_y_col: str = 'utm_pos_y',
        id_col: str = 'maneuver_id',
        type_col: str = 'maneuver_type',
) -> pl.DataFrame:
    """
    Extract a single maneuver timeseries around given parameters
    """
    # Define renaming mappings based on entry tack
    port_renaming = {
        'stbd_flap': 'old_foil_flap',
        'port_flap': 'new_foil_flap',
        'stbd_rake': 'old_rake',
        'port_rake': 'new_rake',
        'stbd_cant': 'old_foil_cant',
        'port_cant': 'new_foil_cant',
        'foil_stbd_sink': 'old_foil_sink',
        'foil_port_sink': 'new_foil_sink',
        'port_effective_cant': 'new_foil_effective_cant',
        'stbd_effective_cant': 'old_foil_effective_cant',
        'm_cant_stbd': 'old_foil_m_cant',
        'm_cant_port': 'new_foil_m_cant',
    }

    starboard_renaming = {
        'stbd_flap': 'new_foil_flap',
        'port_flap': 'old_foil_flap',
        'stbd_rake': 'new_foil_rake',
        'port_rake': 'old_foil_rake',
        'stbd_cant': 'new_foil_cant',
        'port_cant': 'old_foil_cant',
        'foil_stbd_sink': 'new_foil_sink',
        'foil_port_sink': 'old_foil_sink',
        'port_effective_cant': 'old_foil_effective_cant',
        'stbd_effective_cant': 'new_foil_effective_cant',
        'm_cant_stbd': 'new_foil_m_cant',
        'm_cant_port': 'old_foil_m_cant',
    }

    # Metrics that need sign inversion for port tacks
    invert_metrics = ['heel', 'rudder_angle', 'traveller', 'yaw_rate', 'leeway', 'twa', 'jib_car_angle', 'foot_camber', 'foot_angle', 'mast_rotation', 'mast_aoa']

    # define window bounds
    start = timing_data['timestamp'] - pd.Timedelta(seconds=window_s_pre)
    end = timing_data['timestamp'] + pd.Timedelta(seconds=window_s_post)

    # filter df for window
    window_df = df.filter(
        (pl.col(timestamp_col) >= start) &
        (pl.col(timestamp_col) <= end)
    )

    # Get reference point coordinates and wind direction
    maneuver_point = df.filter(
        pl.col(timestamp_col) <= timing_data['timestamp']
    ).sort(timestamp_col).tail(1)

    if len(maneuver_point) > 0:
        center_utm_x = maneuver_point[utm_x_col].item()
        center_utm_y = maneuver_point[utm_y_col].item()

    else:
        # Fallback
        center_utm_x = window_df[utm_x_col][0]
        center_utm_y = window_df[utm_y_col][0]

    # Choose the appropriate renaming mapping
    renaming_map = port_renaming if entry_tack == 'Port' else starboard_renaming

    if 'twd_at_t0' in timing_data.keys():
        window_df = window_df.with_columns([
            (pl.col('twd') - pl.lit(timing_data['twd_at_t0'])).alias('twd_rel_t0')
        ])
        invert_metrics.append('twd_rel_t0')

    if 'tws_at_t0' in timing_data.keys():
        window_df = window_df.with_columns([
            (pl.col('tws') - pl.lit(timing_data['tws_at_t0'])).alias('tws_rel_t0')
        ])
        invert_metrics.append('tws_rel_t0')

    # Create expressions for renaming and inverting
    column_expressions = []
    for col in window_df.columns:
        # Handle UTM coordinates - center them around zero
        if col == utm_x_col:
            column_expressions.append((pl.col(col) - center_utm_x).alias('utm_x_centered'))
            column_expressions.append(pl.col(col))  # Keep original
        elif col == utm_y_col:
            column_expressions.append((pl.col(col) - center_utm_y).alias('utm_y_centered'))
            column_expressions.append(pl.col(col))  # Keep original
        # Handle other columns as before
        elif col in renaming_map:
            new_name = renaming_map[col]
            if entry_tack == 'Port' and col in invert_metrics:
                column_expressions.append((pl.col(col) * -1).alias(new_name))
            else:
                column_expressions.append(pl.col(col).alias(new_name))
        elif entry_tack == 'Port' and col in invert_metrics:
            column_expressions.append((pl.col(col) * -1).alias(col))
        else:
            column_expressions.append(pl.col(col))

    # Apply the renaming and inversions
    window_df = window_df.select(column_expressions)

    # Create wind-relative normalized coordinates
    x_centered = window_df['utm_x_centered'].to_numpy()
    y_centered = window_df['utm_y_centered'].to_numpy()

    # Rotate coordinates so twa = 0 points directly upwind (positive y direction)
    x_wind_relative, y_wind_relative = u.rotate_xy_to_up(x_centered, y_centered, -reference_twd)

    # Add the wind-relative coordinates back to the dataframe
    window_df = window_df.with_columns([
        pl.Series('track_x_wind_relative', x_wind_relative),
        pl.Series('track_y_wind_relative', y_wind_relative),
    ])

    # Flip x coordinates for port entry tacks
    if entry_tack == 'Port':
        window_df = window_df.with_columns([
            (pl.col('track_x_wind_relative') * -1).alias('track_x_wind_relative')
        ])

    window_df = window_df.with_columns([
        pl.lit(maneuver_id).alias(id_col),
        pl.lit(maneuver_type).alias(type_col),
        pl.lit(boat).alias('boat'),
        pl.lit(timing_data['id']).alias('id'),
        pl.lit(entry_tack).alias('entry_tack'),
        pl.lit(center_utm_x).alias('maneuver_center_utm_x'),
        pl.lit(center_utm_y).alias('maneuver_center_utm_y'),
        pl.lit(reference_twd).alias('reference_twd'),
        # compute milliseconds offset
        (((pl.col(timestamp_col).cast(pl.Int64) - pl.lit(timing_data[center_time_col]).cast(pl.Int64)) / 1e6)
         .alias('time_from_htw_ms'))
    ])
    
    # Sort the columns alphabetically for easier comparison later
    window_df = window_df.select(sorted(window_df.columns))

    return window_df


def extract_maneuver_timeseries_all(
        df: pl.DataFrame,
        tack_gybe_df: pl.DataFrame,
        window_s_pre: float = 15.0,
        window_s_post: float = 15.0,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        boat: str = "No Data",
        center_time_col: str = 'timestamp',
) -> pl.DataFrame:
    """
    Extract maneuver timeseries with wind-relative normalized track positioning.
    Creates a standardized coordinate system where upwind is always 'up' (north).
    """
    # ensure timestamps are datetime
    df = df.with_columns(pl.col('timestamp').cast(pl.Datetime))
    tack_gybe_df = tack_gybe_df.with_columns(pl.col('timestamp').cast(pl.Datetime))

    # Check if start_time and end_time is given and if so, filter the DataFrame
    if start_time is not None:
        df = df.filter(pl.col('timestamp') >= start_time)
        tack_gybe_df = tack_gybe_df.filter(pl.col('timestamp') >= start_time)
    if end_time is not None:
        df = df.filter(pl.col('timestamp') <= end_time)
        tack_gybe_df = tack_gybe_df.filter(pl.col('timestamp') <= end_time)

    result = []

    # iterate maneuvers
    for rec in tack_gybe_df.rows(named=True):
        # Extract the maneuver timeseries
        window_df = get_single_timeseries(
            df,
            maneuver_id=rec['maneuver_id'],
            maneuver_type=rec['maneuver_type'],
            timing_data=rec,
            entry_tack=rec['entry_tack'],
            window_s_pre=window_s_pre,
            window_s_post=window_s_post,
            reference_twd=rec['mean_twd'],
            boat=rec.get('boat'),
            crew=rec.get('crew'),
            sails=rec.get('sails'),
            center_time_col=center_time_col,
        )
        if window_df is None or window_df.is_empty():
            print(f"No data found for maneuver_id={rec['maneuver_id']} of type={rec['maneuver_type']} at time={rec['timestamp']}")
            continue
        result.append(window_df)
        
    if len(result) == 0:
        return pl.DataFrame()
    
    result = pl.concat(result, how='diagonal_relaxed')

    return result


def apply_filtering_score_v2(maneuver_metrics: pl.DataFrame) -> pl.DataFrame:
    if maneuver_metrics is None or maneuver_metrics.is_empty():
        return pl.DataFrame()

    required = {"maneuver_type", "total_distance_y"}
    if not required.issubset(set(maneuver_metrics.columns)):
        return maneuver_metrics.with_columns(pl.lit(None, dtype=pl.Float64).alias("filter_score"))

    minv = pl.col("total_distance_y").quantile(0.05).over("maneuver_type")
    maxv = pl.col("total_distance_y").quantile(0.95).over("maneuver_type")
    den  = (maxv - minv)

    score = pl.when(den.abs() <= 1e-12) \
              .then(100.0) \
              .otherwise(((pl.col("total_distance_y") - minv) / den) * 100.0)

    return maneuver_metrics.with_columns(score.alias("filter_score").cast(pl.Float64))
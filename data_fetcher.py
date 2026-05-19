from influxdb_client import InfluxDBClient
import pandas as pd
import arrow
from config import ORG_ID, TOKEN, URL
import maneuver_analysis as ma
import period_analysis as pa
from col_mapping import RENAMING_DICT, COLS_360
import utils as u
import numpy as np
import polars as pl

class SGPDataProvider:
    def __init__(self, boat: str):
        print("Initializing InfluxDB client... with url:", URL, "org:", ORG_ID, "boat:", boat)
        self.api_client = InfluxDBClient(url=URL, token=TOKEN, org=ORG_ID, timeout=1080_000)
        self.boat = boat
        
        self.df = None
        self.maneuvers = None
        self.maneuver_timeseries = None
        self.periods = None
        
    def get_data(self, start_time, end_time) -> pl.DataFrame:
        with open("data.flux", "r") as file:
            query = file.read()
        start = arrow.get(start_time).format("YYYY-MM-DDTHH:mm:ss.SSS") + "Z"
        end   = arrow.get(end_time).format("YYYY-MM-DDTHH:mm:ss.SSS") + "Z"
        
        measurement_filter = _flux_or_equals("_measurement", RENAMING_DICT.keys())

        query = (
            query.replace("{startTime}", start)
                 .replace("{stopTime}", end)
                 .replace("{boat}", self.boat)
                 .replace("{measurementFilter}", measurement_filter)
        )

        result = self.api_client.query_api().query_data_frame(org=ORG_ID, query=query)

        if isinstance(result, list):
            dfs = [df for df in result if df is not None and not df.empty]
            if not dfs:
                return pl.DataFrame()

            pdf = pd.concat(dfs, ignore_index=True)
        else:
            if result is None or result.empty:
                return pl.DataFrame()
            pdf = result

        for col in ("result", "table"):
            if col in pdf.columns:
                pdf = pdf.drop(columns=[col])
                
        pdf = pdf.pivot_table(
                values='_value', 
                index=['_time'], 
                columns='_measurement')
        
        pdf = pdf.reset_index()
        
        race_col = "TRK_RACE_NUM_unk"
        
        num_cols = pdf.select_dtypes(include=[np.number]).columns
        linear_cols = [c for c in num_cols if c != race_col]

        pdf[linear_cols] = pdf[linear_cols].interpolate(
            method="linear", limit_direction="forward", axis=0
        )

        pdf[race_col] = (
            pdf[race_col]
            .ffill()
            .astype("Int64")
        )
        
        pdf['LATITUDE_GPS_unk'] = pdf['LATITUDE_GPS_unk'] / 10000000
        pdf['LONGITUDE_GPS_unk'] = pdf['LONGITUDE_GPS_unk'] / 10000000

        # Convert to Polars
        df = pl.from_pandas(pdf)

        if "_time" in df.columns and df["_time"].dtype == pl.Utf8:
            df = df.with_columns(pl.col("_time").str.to_datetime())

        return df
    
    def detect_periods(
        self,
        df: pl.DataFrame,
        auto_period_duration: float = 6.0,
        min_speed_upwind: float = 30.0,
        min_speed_downwind: float = 30.0,
    ) -> pl.DataFrame:
        df = pa.label_straight_line(
            df,
            min_speed_upwind=min_speed_upwind,
            min_speed_downwind=min_speed_downwind,
        )
        period_times = pa.compute_auto_periods(df, auto_period_duration=auto_period_duration)
        periods = pa.compute_period_metrics(df, period_times, cols_360=COLS_360)
        periods = periods.with_columns([
            pl.lit(self.boat).alias("boat")
        ])
        return periods
    
    def detect_maneuvers(self, df: pl.DataFrame) -> pl.DataFrame:
        maneuver_times = ma.get_clean_htw_times(df, time_col='timestamp')
        maneuvers = ma.compute_maenuver_metrics_v2(df, maneuver_times)
        if maneuvers is None or maneuvers.is_empty():
            self.maneuver_timeseries = pl.DataFrame()
            return pl.DataFrame()
        maneuvers = maneuvers.with_columns([
            pl.lit(self.boat).alias("boat")
        ])
        maneuvers = maneuvers.with_columns([
            (pl.col("timestamp").dt.strftime("%Y%m%d_%H%M%S") + "_" + pl.lit(self.boat)).alias("id")
        ])
        maneuver_timeseries = ma.extract_maneuver_timeseries_all(df=df, tack_gybe_df=maneuvers, boat=self.boat)
        # Add 'boat' to dictionary
        self.maneuver_timeseries = maneuver_timeseries
        return maneuvers
    
    def process_data(
        self,
        df: pl.DataFrame,
        race_num: int = None,
        period_duration: float = 6.0,
        min_speed_upwind: float = 30.0,
        min_speed_downwind: float = 30.0,
    ) -> pl.DataFrame:
        df = df.rename(RENAMING_DICT, strict=False)
        print(df['twa'].describe())
        df = df.with_columns(
            pl.col("timestamp")
            .dt.cast_time_unit("us")
            .dt.replace_time_zone(None)
        )
        if race_num is not None:
            df = df.filter(pl.col('race_number').cast(pl.Int64) == race_num)
            df = df.sort('timestamp')
            print(f"Filtered data for race number: {race_num}, resulting rows: {df.height}")
            print(f"Min timestamp: {df['timestamp'].min()}, Max timestamp: {df['timestamp'].max()}")
        # Convert vmg to absolute value
        df = df.with_columns(
            pl.col("vmg").abs().alias("vmg")
        )
        df = u.ignore_imu_travel(df)
        df = u.add_board_states(df)
        df = u.add_windward_leeward_metrics(df)
        df = u.normalize_columns(df, columns=['twa', 'tgt_twa', 'leeway', 'rudder_angle', 'wing_twist', 'wing_rotation', 'clew_angle', 'cam1_angle', 'cam2_angle', 'cam3_angle', 'cam4_angle', 'cam5_angle', 'cam6_angle'])
        df = u.add_utm_pos(df)
        df = u.calculate_target_percent(df)
        
        periods = self.detect_periods(
            df,
            auto_period_duration=period_duration,
            min_speed_upwind=min_speed_upwind,
            min_speed_downwind=min_speed_downwind,
        )
        
        maneuvers = self.detect_maneuvers(df)
        
        self.df = df
        self.periods = periods
        self.maneuvers = maneuvers
        
        print(f"TWA Column Stats:\n{df['twa'].describe()}")
        
        return df
    
def _flux_or_equals(col: str, values: list[str]) -> str:
    # Ensure only allow-listed measurements are used (prevents Flux injection)
    bad = [v for v in values if v not in RENAMING_DICT.keys()]
    if bad:
        raise ValueError(f"Unsupported measurements: {bad}")

    return " or ".join([f'r["{col}"] == "{v}"' for v in values])
from collections import defaultdict
import polars as pl
from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource, HoverTool, Whisker, CustomJSTickFormatter, Jitter, FactorRange, CDSView, GroupFilter, Range1d, LinearAxis
from bokeh.layouts import gridplot, column as bokeh_column
from bokeh.models import BoxSelectTool, LassoSelectTool, TapTool
from bokeh.core.properties import field
import numpy as np
from numpy.polynomial.polynomial import Polynomial
from bokeh.themes import built_in_themes
from bokeh.io import curdoc

curdoc().theme = built_in_themes["dark_minimal"]

def calculate_mean_timeseries_source(ts, y_column, x_column='time_from_htw_ms', color_by='color', continuous_color_scale=False):   
    if continuous_color_scale:
        color_by = f"{color_by}_bin"
        print(f"Using continuous color scale with color_by: {color_by}")
        
    groups = defaultdict(lambda: {'time': [], 'x': [], 'y': [], 'color': []})
    for time, xs, ys, color in zip(ts['time_from_htw_ms'], ts[x_column], ts[y_column], ts[color_by]):
        if len(time) > 0 and len(xs) > 0 and len(ys) > 0:
            groups[color]['time'].append(time)
            groups[color]['x'].append(xs)
            groups[color]['y'].append(ys)

    mean_lines = {'x': [], 'y': [], 'color': []}
    for color, data in groups.items():
        all_times = np.concatenate(data['time'])
        # Convert to float and drop any None/NaN values
        all_times = np.asarray(all_times, dtype=float)
        all_times = all_times[~np.isnan(all_times)]
        
        if len(all_times) == 0:
            continue
            
        time_min, time_max = np.min(all_times), np.max(all_times)
        common_times = np.linspace(time_min, time_max, 300)

        interp_ys = []
        interp_xs = []
        for time, x, y in zip(data['time'], data['x'], data['y']):
            # Convert to float arrays and filter out NaN values
            time = np.asarray(time, dtype=float)
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            
            # Create mask for valid (non-NaN) values across all arrays
            valid_mask = ~(np.isnan(time) | np.isnan(x) | np.isnan(y))
            time = time[valid_mask]
            x = x[valid_mask]
            y = y[valid_mask]
            
            if len(x) > 1 and len(y) > 1 and len(time) > 1:
                interp_y = np.interp(common_times, time, y)
                interp_x = np.interp(common_times, time, x)
                interp_ys.append(interp_y)
                interp_xs.append(interp_x)
                
        if len(interp_ys) == 0 or len(interp_xs) == 0:
            continue
            
        interp_y = np.array(interp_ys)
        interp_x = np.array(interp_xs)

        mean_y = np.nanmean(interp_y, axis=0)
        mean_x = np.nanmean(interp_x, axis=0)

        mean_lines['x'].append(mean_x)
        mean_lines['y'].append(mean_y)
        mean_lines['color'].append(color)

    mean_source = ColumnDataSource(mean_lines)

    return mean_source

def maneuver_time_series_subplots_bokeh(source, y_columns, color_by='color', trendline=False, continuous_color_scale=False):

    col_n = 1
    plots = []
    for y_column in y_columns:
        if y_column not in source.data:
            continue
        
        ts = source.data
        
        def is_2d(v): 
            return isinstance(v, (list, tuple)) and (len(v) == 0 or isinstance(v[0], (list, tuple)))

        assert 'time_from_htw_ms' in ts, "missing xs"
        assert y_column in ts, f"missing ys for {y_column}"
        if not is_2d(ts['time_from_htw_ms']):
            raise ValueError("time_from_htw_ms must be list-of-lists")
        if not is_2d(ts[y_column]):
            raise ValueError(f"{y_column} must be list-of-lists; got first elem type {type(ts[y_column][0])}")
        assert len(ts['time_from_htw_ms']) == len(ts[y_column]), f"outer lengths differ for {y_column}"

        p = figure(title=y_column, x_axis_label='Time from HTW (s)', y_axis_label=y_column,
                    tools="xwheel_zoom,box_zoom,reset,save", toolbar_location="right", sizing_mode="stretch_width", aspect_ratio=3)
        p.multi_line(xs='time_from_htw_ms', ys=y_column, source=source, line_color=color_by, hover_line_color=color_by, line_dash='line_style',
                     line_alpha=0.4, line_width=1, hover_line_alpha=1.0, nonselection_line_alpha=0.1, selection_line_alpha=1.0, hover_line_width=3)
        
        if trendline:
            try:
                mean_source = calculate_mean_timeseries_source(ts, y_column, color_by=color_by, continuous_color_scale=continuous_color_scale)
                p.multi_line(xs='x', ys='y', source=mean_source, line_color='color', line_width=3, line_alpha=1)

            except Exception as e:
                print(f"Error calculating trendline for {y_column}: {e}")

        hover = HoverTool(tooltips=[
            ('ID', f'@id'),
            ('Maneuver ID', f'@maneuver_id'),
        ], line_policy='next')
        p.add_tools(hover)
        p.add_tools(TapTool())
        p.add_tools(BoxSelectTool())
        lasso = LassoSelectTool()
        p.add_tools(lasso)
        p.toolbar.active_drag = lasso
        plots.append(p)
        
    grid = gridplot(plots, ncols=col_n, sizing_mode='stretch_width')
    return grid


def scatter_timeseries_plot(source, y_column, color_by='color'):
    p = figure(title=y_column, x_axis_type='datetime', tools="xpan,xwheel_zoom,box_zoom,reset,save", toolbar_location="right", sizing_mode="stretch_width", aspect_ratio=24)
    p.scatter(x='timestamp', y=y_column, source=source, color=color_by,
              marker='symbol', size=8, alpha=0.6)

    hover = HoverTool(tooltips=[
        ('ID', f'@id'),
        ('TWS', f'@mean_tws'),
    ], formatters={'@timestamp': 'datetime'}, mode='vline')
    p.add_tools(hover)
    p.add_tools(BoxSelectTool())
    lasso = LassoSelectTool()
    p.add_tools(lasso)
    p.toolbar.active_drag = lasso
    return p


def scatter_sub_plots_tws_bokeh(df, y_columns, tws_col, source=None, color_by='color', show_trendline=False, targets=None, upwind=None, cols=2, trendline_by=None):
    # Use Bokeh for scatter subplots, with grouped selections
    col_n = cols
    
    plots = []

    source_columns = source.column_names

    for y_column in y_columns:
        if isinstance(y_column, list):
            title = y_column[0]
        else:
            title = y_column
            if y_column not in source_columns:
                continue

        p = figure(title=title, x_axis_label='TWS', y_axis_label=title, tools="pan,wheel_zoom,box_zoom,reset,save", toolbar_location="right", sizing_mode="stretch_width", aspect_ratio=1)
        
        if color_by == 'delta_dyn_tgt_color':
            color_col = f'delta_dyn_tgt_{y_column}_color'
        elif color_by == 'delta_automation_tgt_color':
            automation_tgt_mapping = {
            'clew_adjuster_stroke_windward_mean': 'delta_automation_tgt_stroke_clew_mean',
            'jib_sheet_stroke_mean': 'delta_automation_tgt_stroke_jib_sheet_mean',
            'jib_cunno_stroke_mean': 'delta_automation_tgt_stroke_jib_cunningham_mean',
            'jib_car_angle_n_mean': 'delta_automation_tgt_stroke_jib_track_mean',
            'main_cunno_stroke_mean': 'delta_automation_tgt_stroke_main_cunningham_mean',
            'main_sheet_stroke_mean': 'delta_automation_tgt_stroke_main_sheet_mean',
            'mast_rotation_n_mean': 'delta_automation_tgt_stroke_mast_rotation_mean'
            }
            color_col = f'{automation_tgt_mapping.get(y_column)}_color'
        else:
            color_col = color_by
            
        if color_col not in source_columns:
            color_col = 'red'
            
        p.scatter(tws_col, y_column, source=source, color=color_col,
                marker='symbol', size=8, alpha=0.6)

        if show_trendline:
            # Plot a poliynomial fit trendline for each color
            if trendline_by is None:
                trendline_by = color_by
            for color in df[trendline_by].unique().to_list():
                df_subset = df.filter(pl.col(trendline_by) == color)
                if isinstance(y_column, list):
                    y_col = y_column[0]
                else:
                    y_col = y_column
                x = df_subset[tws_col].to_numpy().flatten()
                y = df_subset[y_col].to_numpy().flatten()
                # Remove NaN values
                mask = ~np.isnan(x) & ~np.isnan(y)
                x = x[mask]
                y = y[mask]
                if len(x) < 4:
                    continue
                # Fit a 3rd degree polynomial
                coefs = Polynomial.fit(x, y, 2).convert().coef
                p_x = np.linspace(np.min(x), np.max(x), 100)
                p_y = sum(c * p_x**i for i, c in enumerate(coefs))
                if color_col in df_subset.columns:
                    p.line(p_x, p_y, color=df_subset[trendline_by].head(1).item(), line_width=2)

        if targets is not None and upwind is not None:
            targets_color_map = {target.version: color for target, color in zip(targets, ['black', 'gray', 'lightblue'])} if targets is not None else {}
            for target in targets:
                color = targets_color_map.get(target.version, 'black')
                target_data, base_channel = target.get_target_for_col(y_column, upwind=upwind)
                if target_data is not None:
                    tws_min = df.select(pl.col(tws_col)).min().item() - 2
                    tws_max = df.select(pl.col(tws_col)).max().item() + 2
                    target_data = target_data.filter((pl.col('tws') >= tws_min) & (pl.col('tws') <= tws_max))
                    # Rename target cols to match - for the hovertool
                    target_data = target_data.rename({base_channel: y_column, 'tws': tws_col})
                    # Make the hovertool work for target line
                    target_source = ColumnDataSource(target_data.to_pandas())
                    p.line(tws_col, y_column, source=target_source, color=color, line_width=2)


        # Add hover for target and scatter
        hover = HoverTool(tooltips=[
            ("ID", f"@id"),
            ("TWS", f"@{tws_col}"),
        ])
        p.add_tools(hover)
        p.add_tools(BoxSelectTool())
        lasso = LassoSelectTool()
        p.add_tools(lasso)
        p.toolbar.active_drag = lasso
        plots.append(p)

    grid = gridplot(plots, ncols=col_n, toolbar_location='above', sizing_mode='stretch_width')

    return grid


def combined_period_plots(source, y_column_box, y_column_time, scatter_cols, df, tws_col, color_map=None, color_by='color', show_trendline=True, upwind=False, trendline_by=None):
    """Combine box plot, time series, and scatter plots with shared selection"""
    
    # Create box plot
    box_p = box_plot_bokeh(source, y_column_box, color_map, color_by)
    
    # Create time series plot
    time_p = scatter_timeseries_plot(source, y_column_time, color_by)
    
    # Create scatter subplots
    scatter_grid = scatter_sub_plots_tws_bokeh(df, scatter_cols, tws_col, source, color_by, show_trendline, upwind=upwind, trendline_by=trendline_by)
    
    # Combine into single layout
    layout = bokeh_column(box_p, time_p, scatter_grid, sizing_mode='stretch_width')
    
    return layout

def combined_maneuver_plots(source, y_column_box, y_column_time, scatter_cols, df, tws_col, color_map=None, color_by='color', show_trendline=True):
    """Combine box plot, time series, and scatter plots for maneuvers with shared selection"""
    
    # Create box plot
    box_p = box_plot_bokeh(source, y_column_box, color_map, color_by)
    
    # Create time series plot
    time_p = scatter_timeseries_plot(source, y_column_time, color_by)
    
    # Create scatter subplots
    scatter_grid = scatter_sub_plots_tws_bokeh(df, scatter_cols, tws_col, source, color_by, show_trendline)
    
    # Combine into single layout
    layout = bokeh_column(box_p, time_p, scatter_grid, sizing_mode='stretch_width')
    
    return layout

def combined_maneuver_plots_with_ts(agg_source, ts_source, y_column_box, y_column_time, scatter_cols, ts_y_cols, df, tws_col, color_map=None, color_by='color', show_trendline=True):
    """Combine box plot, time series, scatter plots, and maneuver timeseries with linked selection"""
    import html_utils
    from bokeh.models import CustomJS
    
    # Create box plot
    box_p = box_plot_bokeh(agg_source, y_column_box, color_map, color_by)
    
    # Create time series plot
    time_p = scatter_timeseries_plot(agg_source, y_column_time, color_by)
    
    # Create scatter subplots
    scatter_grid = scatter_sub_plots_tws_bokeh(df, scatter_cols, tws_col, agg_source, color_by, show_trendline)
    
    # Create maneuver timeseries subplots
    ts_grid = maneuver_time_series_subplots_bokeh(
        source=ts_source,
        y_columns=ts_y_cols,
        color_by='color',
        trendline=False,
        continuous_color_scale=False
    )
    
    agg_to_ts_js = html_utils.link_agg_to_ts_js(ts_source, agg_source)
    agg_source.selected.js_on_change('indices', agg_to_ts_js)
    
    # Link timeseries to aggregate
    ts_to_agg_js = html_utils.link_ts_to_agg_js(ts_source, agg_source)
    ts_source.selected.js_on_change('indices', ts_to_agg_js)
    
    # Combine into single layout
    layout = bokeh_column(box_p, time_p, scatter_grid, ts_grid, sizing_mode='stretch_width')
    
    return layout

def box_plot_bokeh(source, y_column, color_map=None, color_by='color'):

    # Calculate quartiles and IQR
    data = source.data
    all_y = data[y_column]
    all_colors = data[color_by]
    # Group by color
    groups = defaultdict(list)
    for y, color in zip(all_y, all_colors):
        groups[color].append(y)
    
    box_data = {'color': [], 'q1': [], 'q2': [], 'q3': [], 'iqr': [], 'upper': [], 'lower': []}
    for color, ys in groups.items():
        ys = np.array(ys)
        q1 = np.percentile(ys, 25)
        q2 = np.percentile(ys, 50)
        q3 = np.percentile(ys, 75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        lower = q1 - 1.5 * iqr
        upper = np.min([upper, np.max(ys)])
        lower = np.max([lower, np.min(ys)])
        
        box_data['color'].append(color)
        box_data['q1'].append(q1)
        box_data['q2'].append(q2)
        box_data['q3'].append(q3)
        box_data['iqr'].append(iqr)
        box_data['upper'].append(upper)
        box_data['lower'].append(lower)

    box_source = ColumnDataSource(box_data)

    p = figure(x_range=box_data['color'], tools="reset,save", toolbar_location="right", y_axis_label=y_column, sizing_mode="stretch_width", aspect_ratio=3)

    whisker = Whisker(source=box_source, base="color", upper="upper", lower="lower", line_width=2,
                      line_color="color", line_alpha=0.5)

    whisker.upper_head.size=100
    whisker.upper_head.line_color="color"
    whisker.upper_head.line_width=2
    whisker.upper_head.line_alpha=0.5
    whisker.lower_head.size=100
    whisker.lower_head.line_color="color"
    whisker.lower_head.line_width=2
    whisker.lower_head.line_alpha=0.5
    p.add_layout(whisker)

    p.vbar("color", 0.5, "q2", "q3", source=box_source, color="color", alpha=0.3, line_width=2, width=0.4, line_alpha=0.5)
    p.vbar("color", 0.5, "q1", "q2", source=box_source, color="color", alpha=0.3, line_width=2, width=0.4, line_alpha=0.5)

    # Scatter all points
    # Jitter the x values for better visibility
    range = FactorRange(*box_data['color'])
    jitter = Jitter(width=0.05, distribution="uniform", range=range)
    scatters = p.scatter(x=field(color_by, jitter), y=y_column, source=source, color=color_by, size=8, alpha=0.3, marker='symbol', selection_alpha=0.8, nonselection_alpha=0.1)

    if color_map:
        # Reverse the color map
        reversed_color_map = {v: k for k, v in color_map.items()}
        p.xaxis.formatter = CustomJSTickFormatter(code="""
                                              var color_map = %s;
                                                return color_map[tick];
                                                """ % str(reversed_color_map))
        
    hover = HoverTool(tooltips=[
            ("ID", f"@id"),
            (f"{y_column}", f"@{y_column}"),
        ], renderers=[scatters])
    p.add_tools(hover)
    p.add_tools(BoxSelectTool())
    lasso = LassoSelectTool()
    p.add_tools(lasso)
    p.toolbar.active_drag = lasso

    return p

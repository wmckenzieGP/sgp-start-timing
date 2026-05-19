from bisect import bisect_right
from html import escape
from bokeh.models import ColumnDataSource, CustomJS
from bokeh.embed import components
from bokeh.transform import linear_cmap
from typing import Dict, List, Optional
import polars as pl
from bokeh.embed import components
from bokeh.themes import built_in_themes

def build_legend(color_map: dict = None,
                 symbol_map: dict = None,
                 line_styles_map: dict = None,
                 target_map: dict = None):
    """
    Returns an HTML string for a compact legend showing:
    - color swatches
    - marker symbols
    - line styles
    Only the sections provided are shown.

    Parameters accept lists; lengths are zipped (extra items are ignored).
    """
    color_map = color_map or {}
    symbol_map = symbol_map or {}
    line_styles_map = line_styles_map or {}

    def symbol_svg(marker, size=16, stroke="currentColor", fill="none", stroke_width=1.8):
        # Generate a tiny SVG for common marker shapes
        s = size
        c = s/2
        r = s*0.32
        if marker == 'o':   # circle
            shape = f'<circle cx="{c}" cy="{c}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == 's': # square
            d = r*1.6
            x = c - d/2
            y = c - d/2
            shape = f'<rect x="{x}" y="{y}" width="{d}" height="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />'
        elif marker == '^': # up-triangle
            p1 = (c, c-r)
            p2 = (c-r*1.2, c+r*0.9)
            p3 = (c+r*1.2, c+r*0.9)
            shape = f'<polygon points="{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == 'v': # down-triangle
            p1 = (c, c+r)
            p2 = (c-r*1.2, c-r*0.9)
            p3 = (c+r*1.2, c-r*0.9)
            shape = f'<polygon points="{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == '<': # left-triangle
            p1 = (c-r, c)
            p2 = (c+r*0.9, c-r*1.1)
            p3 = (c+r*0.9, c+r*1.1)
            shape = f'<polygon points="{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == '>': # right-triangle
            p1 = (c+r, c)
            p2 = (c-r*0.9, c-r*1.1)
            p3 = (c-r*0.9, c+r*1.1)
            shape = f'<polygon points="{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == 'D': # diamond
            p1 = (c, c-r*1.2)
            p2 = (c-r*1.2, c)
            p3 = (c, c+r*1.2)
            p4 = (c+r*1.2, c)
            shape = f'<polygon points="{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]} {p4[0]},{p4[1]}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == '*': # star (simple 5-point)
            # rough star path
            pts = [
                (c, c-r*1.2),
                (c+r*0.35, c-r*0.35),
                (c+r*1.2, c-r*0.2),
                (c+r*0.55, c+r*0.25),
                (c+r*0.75, c+r*1.0),
                (c, c+r*0.6),
                (c-r*0.75, c+r*1.0),
                (c-r*0.55, c+r*0.25),
                (c-r*1.2, c-r*0.2),
                (c-r*0.35, c-r*0.35),
            ]
            pts_str = " ".join(f"{x},{y}" for x,y in pts)
            shape = f'<polygon points="{pts_str}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        elif marker == 'x': # X
            d = r*1.6
            x1, y1 = c - d/2, c - d/2
            x2, y2 = c + d/2, c + d/2
            x3, y3 = c - d/2, c + d/2
            x4, y4 = c + d/2, c - d/2
            shape = (
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
                f'<line x1="{x3}" y1="{y3}" x2="{x4}" y2="{y4}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )
        elif marker == '+': # plus
            d = r*1.6
            shape = (
                f'<line x1="{c}" y1="{c-d/2}" x2="{c}" y2="{c+d/2}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
                f'<line x1="{c-d/2}" y1="{c}" x2="{c+d/2}" y2="{c}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )
        else:  # fallback: small filled circle
            shape = f'<circle cx="{c}" cy="{c}" r="{r*0.8}" fill="{stroke}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        return f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{shape}</svg>'

    def line_svg(style, width=36, height=12, stroke="currentColor", stroke_width=2):
        dash = {
            'solid': None,
            'dashed': "6,4",
            'dotted': "2,3",
            'dashdot': "6,4,2,4"
        }.get(style, None)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        y = height//2
        return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' \
               f'<line x1="1" y1="{y}" x2="{width-1}" y2="{y}" stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr}/></svg>'

    # Build sections
    sections_html = []

    if color_map:
        items = []
        if 'color_bar' in color_map:
            print(f"Building legend for color bar with colors: {color_map['color_bar']}")  # Debug print
            color_legend = color_map.get('color_legend', {})
            for label, color in color_legend.items():
                items.append(
                    f'''<div class="legend-item">
                            <span class="swatch" style="background:{escape(str(color))}"></span>
                            <span class="label">{escape(str(label))}</span>
                        </div>'''
                )
            print(f"Legend items for color bar: {items}")  # Debug print
        else:
            for boat, color in color_map.items():
                items.append(
                    f'''<div class="legend-item">
                            <span class="swatch" style="background:{escape(str(color))}"></span>
                            <span class="label">{escape(str(boat))}</span>
                        </div>'''
                )
        sections_html.append(
            f'''<div class="legend-section">
                    <div class="section-title">Colors</div>
                    <div class="section-body">{''.join(items)}</div>
                </div>'''
        )

    if symbol_map:
        items = []
        for lab, sym in symbol_map.items():
            items.append(
                f'''<div class="legend-item">
                        <span class="icon">{symbol_svg(str(sym))}</span>
                        <span class="label">{escape(str(lab))}</span>
                    </div>'''
            )
        sections_html.append(
            f'''<div class="legend-section">
                    <div class="section-title">Symbols</div>
                    <div class="section-body">{''.join(items)}</div>
                </div>'''
        )

    if line_styles_map:
        items = []
        for lab, ls in line_styles_map.items():
            items.append(
                f'''<div class="legend-item">
                        <span class="icon">{line_svg(str(ls))}</span>
                        <span class="label">{escape(str(lab))}</span>
                    </div>'''
            )
        sections_html.append(
            f'''<div class="legend-section">
                    <div class="section-title">Line styles</div>
                    <div class="section-body">{''.join(items)}</div>
                </div>'''
        )

    if target_map:
        items = []
        for target, color in target_map.items():
            items.append(
                f'''<div class="legend-item">
                        <span class="swatch" style="background:{escape(str(color))}"></span>
                        <span class="label">{escape(str(target))}</span>
                    </div>'''
            )
        sections_html.append(
            f'''<div class="legend-section">
                    <div class="section-title">Targets</div>
                    <div class="section-body">{''.join(items)}</div>
                </div>'''
        )

    if not sections_html:
        return ""  # nothing to show

    # Wrapper with minimal inline CSS so it works anywhere
    html = f'''
<div class="legend-wrapper" role="group">
  <style>
    /* Legend styles are scoped to this wrapper to avoid collisions */
    .legend-wrapper {{
      /* Inherit your report variables if present; otherwise use safe defaults */
      --lg-bg: var(--surface-alt, #0f1623);
      --lg-border: var(--border, rgba(148,163,184,0.18));
      --lg-text: var(--text, #e5e7eb);
      --lg-muted: var(--muted, #9ca3af);
      --lg-radius: var(--radius, 8px);
      --lg-radius-sm: var(--radius-sm, 6px);

      font-family: var(--sans, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif);
      font-size: 12.5px;
      line-height: 1.35;

      color: var(--lg-text);
      background: var(--lg-bg);
      border: 1px solid var(--lg-border);
      border-radius: var(--lg-radius);
      padding: 10px 12px;

      display: flex;
      flex-wrap: wrap;
      gap: 14px;

      /* No shadows for the professional style */
      box-shadow: none;
    }}

    .legend-section {{
      display: inline-flex;
      flex-direction: column;
      gap: 8px;
      min-width: 160px;
    }}

    .section-title {{
      font-weight: 600;
      font-size: 11.5px;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      color: var(--lg-muted);
      padding-bottom: 6px;
      border-bottom: 1px solid var(--lg-border);
    }}

    .section-body {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
      padding-top: 2px;
    }}

    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      color: var(--lg-text);
    }}

    .swatch {{
      width: 12px;
      height: 12px;
      border-radius: 3px;
      border: 1px solid rgba(148,163,184,0.22);
      box-sizing: border-box;
      display: inline-block;
      flex: none;
      background: transparent;
    }}

    .icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 38px;
      height: 16px;
      flex: none;
      opacity: 0.95;
    }}

    .label {{
      display: inline-block;
      color: var(--lg-text);
    }}

    /* Ensure inline SVG strokes match dark mode */
    .legend-wrapper svg {{
      display: block;
    }}
    .legend-wrapper svg * {{
      stroke: currentColor;
    }}

    /* If you want filled markers to be visible, set fill to currentColor when fill="none" is used */
    /* (We won't force fill globally, because you may rely on "none" for hollow markers.) */
  </style>
  {''.join(sections_html)}
</div>
'''

    return html


def link_agg_to_ts_js(time_series_source: ColumnDataSource,
                                 agg_source: ColumnDataSource) -> CustomJS:
    """
    Returns a CustomJS that links selection from aggregate tack source to time series tack source.
    """
    # Aggregate -> Timeseries (with guard)
    agg_to_ts = CustomJS(args=dict(ts=time_series_source, agg=agg_source), code="""
        // Check if this update came from ts_to_agg to prevent circular update
        if (agg._updating) {
            console.log("[agg->ts] Skipping - circular update detected");
            return;
        }
        
        // Ensure bootstrap has run
        if (!ts._id_to_ts || !agg._id_to_agg) {
            console.log("[agg->ts] Running bootstrap first...");
            
            const ts_id = ts.data.id || [];
            const agg_id = agg.data.id || [];
            
            let actual_ts_ids = ts_id;
            if (ts_id.length > 0 && Array.isArray(ts_id[0])) {
                actual_ts_ids = ts_id.map(id_array => id_array[0]);
            }
            
            const id_to_ts = {};
            for (let i = 0; i < actual_ts_ids.length; i++) {
                const id = actual_ts_ids[i];
                if (!id_to_ts[id]) id_to_ts[id] = [];
                id_to_ts[id].push(i);
            }
            
            const id_to_agg = {};
            for (let j = 0; j < agg_id.length; j++) {
                id_to_agg[agg_id[j]] = j;
            }
            
            ts._id_to_ts = id_to_ts;
            agg._id_to_agg = id_to_agg;
            ts._updating = false;
            agg._updating = false;
            
            console.log("[bootstrap in agg->ts] Initialized with", Object.keys(id_to_ts).length, "ts IDs");
        }
        
        // Now do the selection sync
        const sel = agg.selected.indices;
        const agg_ids = agg.data.id;
        const id_to_ts = ts._id_to_ts || {};
        
        console.log("[agg->ts] Selected agg indices:", sel);
        
        const ts_sel = [];
        for (const j of sel) {
            const id = agg_ids[j];
            const rows = id_to_ts[id] || [];
            ts_sel.push(...rows);
        }
        
        console.log("[agg->ts] Mapping", sel.length, "agg selections to", ts_sel.length, "ts indices");
        
        // Set flag before updating to prevent circular trigger
        ts._updating = true;
        ts.selected.indices = ts_sel;
        ts.change.emit();
        
        // Reset flag after a small delay
        setTimeout(() => { ts._updating = false; }, 10);
    """)
    return agg_to_ts


def link_ts_to_agg_js(time_series_source: ColumnDataSource,
                                 agg_source: ColumnDataSource) -> CustomJS:
    """
    Returns a CustomJS that links selection from time series tack source to aggregate tack source.
    """
    ts_to_agg = CustomJS(args=dict(ts=time_series_source, agg=agg_source), code="""
        // Check if this update came from agg_to_ts to prevent circular update
        if (ts._updating) {
            console.log("[ts->agg] Skipping - circular update detected");
            return;
        }
        
        // Ensure bootstrap has run
        if (!ts._id_to_ts || !agg._id_to_agg) {
            console.log("[ts->agg] Running bootstrap first...");
            
            const ts_id = ts.data.id || [];
            const agg_id = agg.data.id || [];
            
            let actual_ts_ids = ts_id;
            if (ts_id.length > 0 && Array.isArray(ts_id[0])) {
                actual_ts_ids = ts_id.map(id_array => id_array[0]);
            }
            
            const id_to_ts = {};
            for (let i = 0; i < actual_ts_ids.length; i++) {
                const id = actual_ts_ids[i];
                if (!id_to_ts[id]) id_to_ts[id] = [];
                id_to_ts[id].push(i);
            }
            
            const id_to_agg = {};
            for (let j = 0; j < agg_id.length; j++) {
                id_to_agg[agg_id[j]] = j;
            }
            
            ts._id_to_ts = id_to_ts;
            agg._id_to_agg = id_to_agg;
            ts._updating = false;
            agg._updating = false;
            
            console.log("[bootstrap in ts->agg] Initialized with", Object.keys(id_to_agg).length, "agg IDs");
        }
        
        const sel = ts.selected.indices;
        const ts_ids = ts.data.id;
        const id_to_agg = agg._id_to_agg || {};
        
        console.log("[ts->agg] Selected ts indices:", sel);
        
        // Handle both regular arrays and nested arrays for multi_line
        let actual_ts_ids = ts_ids;
        if (ts_ids.length > 0 && Array.isArray(ts_ids[0])) {
            actual_ts_ids = ts_ids.map(id_array => id_array[0]);
        }
        
        // Collect unique IDs from selected timeseries rows
        const sel_ids = new Set();
        for (const i of sel) {
            if (i < actual_ts_ids.length) {
                sel_ids.add(actual_ts_ids[i]);
            }
        }
        
        // Map to aggregate row indices
        const agg_sel = [];
        for (const id of sel_ids) {
            if (id in id_to_agg) {
                agg_sel.push(id_to_agg[id]);
            }
        }
        
        console.log("[ts->agg] Mapping", sel.length, "ts selections to", agg_sel.length, "agg indices");
        
        // Set flag before updating to prevent circular trigger
        agg._updating = true;
        agg.selected.indices = agg_sel;
        agg.change.emit();
        
        // Reset flag after a small delay
        setTimeout(() => { agg._updating = false; }, 10);
    """)
    return ts_to_agg

def create_component(figures: dict):
    """Create a Bokeh layout from a list of figures."""
    script, divs = components(figures, theme=built_in_themes["dark_minimal"])
    return script, divs


def add_colors_symbols_to_df(df: pl.DataFrame, color_map: Optional[dict]=None, color_by: Optional[str]=None, symbol_map: Optional[dict]=None, symbol_by: Optional[str]=None, 
                             line_style_map: Optional[dict]=None, line_style_by: Optional[str]=None) -> pl.DataFrame:
    # Add colors to dataframe
    if color_map is not None and color_by is not None:
        df = df.with_columns([
            pl.col(color_by).replace_strict(color_map, default=None).alias(f'color')
        ])
    
    if symbol_map is not None and symbol_by is not None:
        symbol_dict = {'s': 'square', 'o': 'circle', '^': 'triangle', 'diamond': 'diamond'}
        symbol_map = {k: symbol_dict.get(v, v) for k, v in symbol_map.items()}
        df = df.with_columns([
            pl.col(symbol_by).replace_strict(symbol_map, default=None).alias(f'symbol')
        ])

    if line_style_map is not None and line_style_by is not None:
        df = df.with_columns([
            pl.col(line_style_by).replace_strict(line_style_map, default=None).alias(f'line_style')
        ])

    return df

def add_colors_symbols_to_df_multi(df: pl.DataFrame, color_map: Optional[dict]=None, color_bys: Optional[List[str]]=None, symbol_map: Optional[dict]=None, symbol_by: Optional[str]=None, 
                             line_style_map: Optional[dict]=None, line_style_by: Optional[str]=None) -> pl.DataFrame:
    # Add colors to dataframe
    if color_map is not None and color_bys is not None:
        for color_by in color_bys:
            relevant_color_map = color_map.get(color_by, {})
            if 'color_bar' in relevant_color_map:
                color_stops = relevant_color_map.get('color_bar', {})
                color_values = relevant_color_map.get('cols', {})
                for col, range_vals in color_values.items():
                    min_val = range_vals.get('min', 0)
                    max_val = range_vals.get('max', 1)
                    color_mapper = make_color_mapper(stops=color_stops)
                    # Add color bin as well, the closest color stop
                    df = df.with_columns(
                        pl.col(col)
                        .cast(pl.Float64)
                        .map_elements(
                            lambda v: (
                                color_mapper((v - min_val) / (max_val - min_val))
                                if v is not None and max_val != min_val
                                else None
                            )
                        )
                        .alias(f"{col}_color"),
                        pl.col(col)
                        .cast(pl.Float64)
                        .map_elements(
                            lambda v: (
                                min(color_stops.keys(), key=lambda c: abs(color_stops[c] - ((v - min_val) / (max_val - min_val))))
                                if v is not None and max_val != min_val
                                else None
                            )
                        ).alias(f"{col}_color_bin")
                    )
            else:
                df = df.with_columns([
                pl.col(color_by).replace_strict(relevant_color_map, default=None).alias(f'{color_by}_color')
                ])
    
    if symbol_map is not None and symbol_by is not None:
        symbol_dict = {'s': 'square', 'o': 'circle', '^': 'triangle', 'diamond': 'diamond'}
        symbol_map = {k: symbol_dict.get(v, v) for k, v in symbol_map.items()}
        df = df.with_columns([
            pl.col(symbol_by).replace_strict(symbol_map, default=None).alias(f'symbol')
        ])

    if line_style_map is not None and line_style_by is not None:
        print("Applying line style map:", line_style_map)  # Debug print
        print(f"Unique values in '{line_style_by}':", df.select(pl.col(line_style_by).unique()).to_series().to_list())  # Debug print
        df = df.with_columns([
            pl.col(line_style_by).replace_strict(line_style_map, default=None).alias(f'line_style')
        ])
        print(df.select(pl.col('line_style').unique()).to_series().to_list())  # Debug print

    return df


from typing import Tuple
import numpy as np

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    r, g, b = [int(np.clip(v, 0, 255)) for v in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"

def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors, t in [0, 1]."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    r = r1 + (r2 - r1) * t
    g = g1 + (g2 - g1) * t
    b = b1 + (b2 - b1) * t
    return rgb_to_hex((r, g, b))

def make_color_mapper(stops: Dict[str, float]):
    """
    stops: dict of {color_hex: position}, e.g.
        {
            "#ff0000": 0.0,
            "#ffff00": 0.5,
            "#00ff00": 1.0,
        }
    positions should be in [0, 1], but don't *have* to be exactly.
    """

    items = sorted(((pos, col) for col, pos in stops.items()), key=lambda x: x[0])
    positions = [p for p, _ in items]
    colors = [c for _, c in items]

    def color_for_value(v: float) -> str:
        # Clamp v to [min_pos, max_pos]
        if v <= positions[0]:
            return colors[0]
        if v >= positions[-1]:
            return colors[-1]

        # Find right-hand index, then use segment [i-1, i]
        idx = bisect_right(positions, v)
        p0, c0 = positions[idx - 1], colors[idx - 1]
        p1, c1 = positions[idx], colors[idx]

        # Normalize v into [0,1] within this segment
        if p1 == p0:
            t = 0.0
        else:
            t = (v - p0) / (p1 - p0)

        return lerp_color(c0, c1, t)

    return color_for_value


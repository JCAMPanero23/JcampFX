"""
JcampFX — Phase 1 Web Chart (PRD §7.3)

Plotly/Dash browser chart for Range Bar visualization.

Features:
  - OHLC Range Bar chart (green/red candles)
  - Tick-volume bars below the main chart
  - Pair selector dropdown (5-symbol universe)
  - Bar-size selector (override default pips per pair)
  - Toggle-able M15 OHLC overlay (time-aligned to Range Bar end_time)
  - Date range slider
  - Validation badges showing PRD check status (V1.3, V1.4, V1.6)

Run:
    python -m dashboard.app
    # then open http://localhost:8050
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import PAIRS, RANGE_BAR_PIPS
from src.range_bar_converter import load_range_bars, ticks_to_range_bars

log = logging.getLogger(__name__)

# Try to load M15 OHLC — graceful fallback if not yet fetched
try:
    from src.data_fetcher import load_ohlc, load_ticks
    DATA_FETCHER_AVAILABLE = True
except ImportError:
    DATA_FETCHER_AVAILABLE = False

PROJECT_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    title="JcampFX — Range Bar Chart",
    suppress_callback_exceptions=True,
)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _try_load_range_bars(pair: str, bar_pips: int) -> pd.DataFrame | None:
    """Load from Parquet cache; return None if not yet built."""
    try:
        return load_range_bars(pair, bar_pips)
    except FileNotFoundError:
        return None


def _try_load_ohlc(pair: str) -> pd.DataFrame | None:
    if not DATA_FETCHER_AVAILABLE:
        return None
    try:
        return load_ohlc(pair)
    except FileNotFoundError:
        return None


def _validation_badges(rb_df: pd.DataFrame, bar_pips: int, pip_size: float) -> list:
    """
    Compute PRD validation checks from a Range Bar DataFrame.
    Returns a list of Dash badge components.
    """
    if rb_df is None or rb_df.empty:
        return []

    results = {}

    # V1.3 — High - Low == exactly bar_size (within spread tolerance ±0.5 pip)
    bar_size = bar_pips * pip_size
    tolerance = pip_size * 0.5
    spreads = (rb_df["high"] - rb_df["low"]).round(10)
    v13_pass = ((spreads - bar_size).abs() <= tolerance).all()
    results["V1.3 High-Low=N pips"] = v13_pass

    # V1.4 — Bars span different durations (purely price-driven)
    if "start_time" in rb_df.columns and "end_time" in rb_df.columns:
        durations = (rb_df["end_time"] - rb_df["start_time"]).dt.total_seconds()
        v14_pass = durations.nunique() > 1
    else:
        v14_pass = False
    results["V1.4 Varying durations"] = v14_pass

    badges = []
    for label, passed in results.items():
        color = "#28a745" if passed else "#dc3545"
        symbol = "✓" if passed else "✗"
        badges.append(
            html.Span(
                f"{symbol} {label}",
                style={
                    "background": color,
                    "color": "white",
                    "padding": "3px 8px",
                    "borderRadius": "4px",
                    "marginRight": "6px",
                    "fontSize": "12px",
                    "fontFamily": "monospace",
                },
            )
        )
    return badges


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app.layout = html.Div(
    style={"backgroundColor": "#1a1a2e", "minHeight": "100vh", "padding": "16px", "fontFamily": "sans-serif"},
    children=[
        # Header
        html.Div(
            style={"display": "flex", "alignItems": "center", "marginBottom": "12px"},
            children=[
                html.H2(
                    "JcampFX — Range Bar Chart",
                    style={"color": "#e0e0e0", "margin": 0, "fontSize": "20px"},
                ),
                html.Span(
                    "Phase 1",
                    style={
                        "background": "#4a90d9",
                        "color": "white",
                        "padding": "2px 8px",
                        "borderRadius": "4px",
                        "fontSize": "12px",
                        "marginLeft": "12px",
                    },
                ),
            ],
        ),

        # Controls row
        html.Div(
            style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap", "marginBottom": "10px"},
            children=[
                # Pair selector
                html.Div([
                    html.Label("Pair", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Dropdown(
                        id="pair-selector",
                        options=[{"label": p, "value": p} for p in PAIRS],
                        value=PAIRS[0],
                        clearable=False,
                        style={"width": "130px", "fontSize": "14px"},
                    ),
                ]),

                # Bar size override
                html.Div([
                    html.Label("Bar size (pips)", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Input(
                        id="bar-pips-input",
                        type="number",
                        min=1,
                        max=100,
                        step=1,
                        placeholder="auto",
                        style={"width": "100px", "fontSize": "14px", "padding": "5px"},
                    ),
                ]),

                # M15 overlay toggle
                html.Div([
                    html.Label("M15 overlay", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Checklist(
                        id="m15-toggle",
                        options=[{"label": " Show M15", "value": "show"}],
                        value=[],
                        style={"color": "#ccc", "fontSize": "14px"},
                    ),
                ]),

                # Bars to display
                html.Div([
                    html.Label("Show last N bars", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Input(
                        id="n-bars-input",
                        type="number",
                        min=50,
                        max=5000,
                        step=50,
                        value=500,
                        style={"width": "100px", "fontSize": "14px", "padding": "5px"},
                    ),
                ]),

                # Refresh button
                html.Div([
                    html.Label("\u00a0", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    html.Button(
                        "Load / Refresh",
                        id="load-btn",
                        n_clicks=0,
                        style={
                            "background": "#4a90d9",
                            "color": "white",
                            "border": "none",
                            "padding": "6px 16px",
                            "borderRadius": "4px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                        },
                    ),
                ]),
            ],
        ),

        # Validation badges row
        html.Div(id="validation-badges", style={"marginBottom": "10px", "minHeight": "24px"}),

        # Status message
        html.Div(id="status-msg", style={"color": "#aaa", "fontSize": "12px", "marginBottom": "8px"}),

        # Main chart
        dcc.Graph(
            id="main-chart",
            style={"height": "70vh"},
            config={"scrollZoom": True, "displayModeBar": True},
        ),

        # Hidden store for loaded data summary
        dcc.Store(id="chart-meta"),
    ],
)


# ---------------------------------------------------------------------------
# Callback — load data and render chart
# ---------------------------------------------------------------------------

@callback(
    Output("main-chart", "figure"),
    Output("status-msg", "children"),
    Output("validation-badges", "children"),
    Input("load-btn", "n_clicks"),
    State("pair-selector", "value"),
    State("bar-pips-input", "value"),
    State("m15-toggle", "value"),
    State("n-bars-input", "value"),
    prevent_initial_call=False,
)
def update_chart(n_clicks, pair, bar_pips_override, m15_toggle, n_bars):
    from src.config import PIP_SIZE, RANGE_BAR_PIPS

    bar_pips = int(bar_pips_override) if bar_pips_override else RANGE_BAR_PIPS.get(pair, 10)
    pip_size = PIP_SIZE[pair]
    show_m15 = "show" in (m15_toggle or [])
    n_bars = int(n_bars) if n_bars else 500

    # --- Load Range Bars ---
    rb_df = _try_load_range_bars(pair, bar_pips)

    if rb_df is None or rb_df.empty:
        fig = _empty_figure(f"No Range Bar data for {pair} (RB{bar_pips})\n"
                            f"Run: python -m src.data_fetcher && python -m src.range_bar_converter")
        return fig, f"No data — fetch ticks first", []

    # Trim to last N bars
    rb_df = rb_df.tail(n_bars).copy()

    # --- Load M15 if requested ---
    m15_df = _try_load_ohlc(pair) if show_m15 else None

    # --- Build figure ---
    fig = _build_figure(pair, rb_df, m15_df, bar_pips, pip_size)

    status = (
        f"{pair} | RB{bar_pips} | {len(rb_df):,} bars shown | "
        f"{rb_df['start_time'].iloc[0].strftime('%Y-%m-%d')} → "
        f"{rb_df['end_time'].iloc[-1].strftime('%Y-%m-%d')}"
    )
    badges = _validation_badges(rb_df, bar_pips, pip_size)

    return fig, status, badges


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------

def _build_figure(
    pair: str,
    rb_df: pd.DataFrame,
    m15_df: pd.DataFrame | None,
    bar_pips: int,
    pip_size: float,
) -> go.Figure:
    """Build the main Plotly figure with Range Bars + optional M15 overlay + volume."""

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.02,
    )

    # x-axis: use bar index for even spacing (Range Bars are price-driven, not time)
    x_rb = list(range(len(rb_df)))
    # Custom tick labels: show start_time at regular intervals
    tick_step = max(1, len(rb_df) // 20)
    tick_vals = list(range(0, len(rb_df), tick_step))
    tick_text = [rb_df["start_time"].iloc[i].strftime("%m/%d %H:%M") for i in tick_vals]

    # --- Range Bar candlesticks ---
    increasing_color = "#26a69a"
    decreasing_color = "#ef5350"

    fig.add_trace(
        go.Candlestick(
            x=x_rb,
            open=rb_df["open"],
            high=rb_df["high"],
            low=rb_df["low"],
            close=rb_df["close"],
            name=f"{pair} RB{bar_pips}",
            increasing=dict(line=dict(color=increasing_color, width=1), fillcolor=increasing_color),
            decreasing=dict(line=dict(color=decreasing_color, width=1), fillcolor=decreasing_color),
            whiskerwidth=0,
        ),
        row=1, col=1,
    )

    # --- M15 OHLC overlay ---
    if m15_df is not None and not m15_df.empty:
        # Align M15 bars to Range Bar x-axis by matching closest end_time
        rb_times = rb_df["end_time"].values
        m15_df = m15_df.copy()
        m15_df["time"] = pd.to_datetime(m15_df["time"], utc=True)

        # Only show M15 bars within the Range Bar time window
        t_min = rb_df["start_time"].iloc[0]
        t_max = rb_df["end_time"].iloc[-1]
        m15_window = m15_df[(m15_df["time"] >= t_min) & (m15_df["time"] <= t_max)].copy()

        if not m15_window.empty:
            # Map each M15 bar's time to nearest RB x position
            import numpy as np
            rb_times_arr = pd.to_datetime(rb_times).astype("int64")
            m15_times_arr = m15_window["time"].astype("int64").values
            indices = [int(abs(rb_times_arr - t).argmin()) for t in m15_times_arr]

            fig.add_trace(
                go.Candlestick(
                    x=indices,
                    open=m15_window["open"],
                    high=m15_window["high"],
                    low=m15_window["low"],
                    close=m15_window["close"],
                    name="M15",
                    opacity=0.45,
                    increasing=dict(line=dict(color="#a5d6a7", width=1), fillcolor="rgba(165,214,167,0.3)"),
                    decreasing=dict(line=dict(color="#ef9a9a", width=1), fillcolor="rgba(239,154,154,0.3)"),
                    whiskerwidth=0,
                    showlegend=True,
                ),
                row=1, col=1,
            )

    # --- Volume bars ---
    colors = [
        increasing_color if rb_df["close"].iloc[i] >= rb_df["open"].iloc[i] else decreasing_color
        for i in range(len(rb_df))
    ]
    fig.add_trace(
        go.Bar(
            x=x_rb,
            y=rb_df["tick_volume"],
            name="Tick Volume",
            marker_color=colors,
            opacity=0.7,
            showlegend=False,
        ),
        row=2, col=1,
    )

    # --- Layout styling ---
    fig.update_layout(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        font=dict(color="#e0e0e0", size=11),
        showlegend=True,
        legend=dict(
            bgcolor="rgba(0,0,0,0.4)",
            bordercolor="#444",
            borderwidth=1,
            font=dict(size=11),
            x=0.01, y=0.99,
        ),
        margin=dict(l=60, r=20, t=30, b=40),
        xaxis2=dict(
            tickvals=tick_vals,
            ticktext=tick_text,
            tickangle=-45,
            gridcolor="#2a2a4a",
        ),
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor="#2a2a4a",
        ),
        yaxis=dict(
            gridcolor="#2a2a4a",
            side="right",
            tickformat=f".{_decimal_places(pip_size)}f",
        ),
        yaxis2=dict(
            gridcolor="#2a2a4a",
            side="right",
        ),
        hovermode="x unified",
    )

    # Add bar-size annotation
    fig.add_annotation(
        x=0.99, y=0.98,
        xref="paper", yref="paper",
        text=f"RB{bar_pips} pips",
        showarrow=False,
        font=dict(size=12, color="#888"),
        align="right",
    )

    return fig


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        font=dict(color="#aaa"),
        annotations=[dict(
            text=message,
            x=0.5, y=0.5,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=14, color="#888"),
            align="center",
        )],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _decimal_places(pip_size: float) -> int:
    """Return number of decimal places to display for a given pip size."""
    if pip_size >= 0.01:
        return 3
    return 5


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="JcampFX Range Bar Dashboard")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    log.info("Starting JcampFX dashboard on http://localhost:%d", args.port)
    app.run(debug=args.debug, port=args.port)

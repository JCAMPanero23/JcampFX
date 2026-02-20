"""
JcampFX — Web Dashboard (Phase 1 + Phase 3)

Tabs:
  Tab 1 — Range Bar Chart (Phase 1, PRD §7.3)
  Tab 2 — Cinema (Phase 3, PRD §9.2): Backtester equity curve, DCRD timeline,
           trade markers, trade log table

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

from src.config import BACKTEST_RESULTS_DIR, PAIRS, RANGE_BAR_PIPS
from src.range_bar_converter import load_range_bars, ticks_to_range_bars

# Backtester imports (Phase 3) — graceful fallback if not yet installed
try:
    from backtester.engine import BacktestEngine
    from backtester.results import BacktestResults
    from backtester.walk_forward import WalkForwardManager
    BACKTESTER_AVAILABLE = True
except ImportError:
    BACKTESTER_AVAILABLE = False

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
    title="JcampFX Dashboard",
    suppress_callback_exceptions=True,
    use_pages=True,
    pages_folder=str(Path(__file__).parent / "pages"),
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

_TAB_STYLE = {"backgroundColor": "#1a1a2e", "color": "#aaa", "border": "1px solid #333", "padding": "6px 18px"}
_TAB_SELECTED = {"backgroundColor": "#16213e", "color": "#e0e0e0", "border": "1px solid #4a90d9", "padding": "6px 18px"}

# ---------------------------------------------------------------------------
# Tab 1 layout (Range Bar Chart — Phase 1)
# ---------------------------------------------------------------------------

_tab1_layout = html.Div(
    style={"padding": "16px"},
    children=[
        # Controls row
        html.Div(
            style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap", "marginBottom": "10px"},
            children=[
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
                html.Div([
                    html.Label("Bar size (pips)", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Input(
                        id="bar-pips-input",
                        type="number", min=1, max=100, step=1, placeholder="auto",
                        style={"width": "100px", "fontSize": "14px", "padding": "5px"},
                    ),
                ]),
                html.Div([
                    html.Label("M15 overlay", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Checklist(
                        id="m15-toggle",
                        options=[{"label": " Show M15", "value": "show"}],
                        value=[],
                        style={"color": "#ccc", "fontSize": "14px"},
                    ),
                ]),
                html.Div([
                    html.Label("Show last N bars", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Input(
                        id="n-bars-input",
                        type="number", min=50, max=5000, step=50, value=500,
                        style={"width": "100px", "fontSize": "14px", "padding": "5px"},
                    ),
                ]),
                html.Div([
                    html.Label("\u00a0", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    html.Button(
                        "Load / Refresh", id="load-btn", n_clicks=0,
                        style={"background": "#4a90d9", "color": "white", "border": "none",
                               "padding": "6px 16px", "borderRadius": "4px", "cursor": "pointer", "fontSize": "14px"},
                    ),
                ]),
            ],
        ),
        html.Div(id="validation-badges", style={"marginBottom": "10px", "minHeight": "24px"}),
        html.Div(id="status-msg", style={"color": "#aaa", "fontSize": "12px", "marginBottom": "8px"}),
        dcc.Graph(id="main-chart", style={"height": "70vh"}, config={"scrollZoom": True, "displayModeBar": True}),
        dcc.Store(id="chart-meta"),
    ],
)


# ---------------------------------------------------------------------------
# Tab 2 layout (Cinema — Phase 3)
# ---------------------------------------------------------------------------

_STRATEGY_COLORS = {
    "TrendRider": "#4a90d9",
    "BreakoutRider": "#f0a500",
    "RangeRider": "#9b59b6",
}

_tab2_layout = html.Div(
    style={"padding": "16px"},
    children=[
        # Controls row
        html.Div(
            style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap", "marginBottom": "12px"},
            children=[
                html.Div([
                    html.Label("Pairs", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.Dropdown(
                        id="cinema-pairs",
                        options=[{"label": p, "value": p} for p in PAIRS],
                        value=PAIRS[:3],
                        multi=True,
                        style={"width": "280px", "fontSize": "13px"},
                    ),
                ]),
                html.Div([
                    html.Label("Date Range", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.DatePickerRange(
                        id="cinema-date-range",
                        start_date="2023-01-01",
                        end_date="2024-12-31",
                        display_format="YYYY-MM-DD",
                        style={"fontSize": "13px"},
                    ),
                ]),
                html.Div([
                    html.Label("Mode", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    dcc.RadioItems(
                        id="cinema-mode",
                        options=[
                            {"label": " Walk-Forward (4 cycles)", "value": "walkforward"},
                            {"label": " Single Run", "value": "single"},
                        ],
                        value="single",
                        style={"color": "#ccc", "fontSize": "13px"},
                        inline=False,
                    ),
                ]),
                html.Div([
                    html.Label("\u00a0", style={"color": "#aaa", "fontSize": "12px", "display": "block", "marginBottom": "3px"}),
                    html.Button(
                        "Run Backtest", id="cinema-run-btn", n_clicks=0,
                        style={"background": "#2ecc71", "color": "white", "border": "none",
                               "padding": "6px 18px", "borderRadius": "4px", "cursor": "pointer", "fontSize": "14px"},
                    ),
                    html.Button(
                        "Load Last Run", id="cinema-load-btn", n_clicks=0,
                        style={"background": "#555", "color": "white", "border": "none",
                               "padding": "6px 18px", "borderRadius": "4px", "cursor": "pointer",
                               "fontSize": "14px", "marginLeft": "8px"},
                    ),
                ]),
            ],
        ),

        # Status bar
        html.Div(id="cinema-status", style={
            "color": "#aaa", "fontSize": "12px", "marginBottom": "10px",
            "background": "#16213e", "padding": "8px 12px", "borderRadius": "4px",
        }),

        # Equity + Drawdown chart
        html.Div([
            html.H4("Equity Curve", style={"color": "#aaa", "fontSize": "13px", "margin": "0 0 4px 0"}),
            dcc.Graph(id="cinema-equity-chart", style={"height": "250px"},
                      config={"scrollZoom": True, "displayModeBar": False}),
        ], style={"marginBottom": "12px"}),

        # DCRD Timeline
        html.Div([
            html.H4("DCRD CompositeScore Timeline", style={"color": "#aaa", "fontSize": "13px", "margin": "0 0 4px 0"}),
            dcc.Graph(id="cinema-dcrd-chart", style={"height": "200px"},
                      config={"scrollZoom": True, "displayModeBar": False}),
        ], style={"marginBottom": "12px"}),

        # Trade markers on Range Bars
        html.Div([
            html.H4("Range Bar Chart + Trade Markers", style={"color": "#aaa", "fontSize": "13px", "margin": "0 0 4px 0"}),
            html.Div([
                html.Label("Pair for chart", style={"color": "#aaa", "fontSize": "12px", "marginRight": "8px"}),
                dcc.Dropdown(
                    id="cinema-rb-pair",
                    options=[{"label": p, "value": p} for p in PAIRS],
                    value=PAIRS[0],
                    clearable=False,
                    style={"width": "130px", "fontSize": "13px", "display": "inline-block"},
                ),
            ], style={"marginBottom": "6px"}),
            dcc.Graph(id="cinema-rb-chart", style={"height": "350px"},
                      config={"scrollZoom": True, "displayModeBar": True}),
        ], style={"marginBottom": "12px"}),

        # Trade log table
        html.Div([
            html.H4("Trade Log", style={"color": "#aaa", "fontSize": "13px", "margin": "0 0 4px 0"}),
            html.Div(id="cinema-trade-table", style={"overflowX": "auto"}),
        ]),

        # Hidden store for results
        dcc.Store(id="cinema-results-store"),
    ],
)


# ---------------------------------------------------------------------------
# Main layout with tabs
# ---------------------------------------------------------------------------

_main_layout = html.Div(
    style={"backgroundColor": "#1a1a2e", "minHeight": "100vh", "fontFamily": "sans-serif"},
    children=[
        # Header
        html.Div(
            style={"display": "flex", "alignItems": "center", "padding": "12px 16px 4px 16px"},
            children=[
                html.H2("JcampFX", style={"color": "#e0e0e0", "margin": 0, "fontSize": "20px"}),
                html.Span("Regime-Adaptive Engine", style={"color": "#888", "fontSize": "13px", "marginLeft": "12px"}),
            ],
        ),
        dcc.Tabs(
            id="main-tabs",
            value="tab-rb",
            style={"backgroundColor": "#1a1a2e"},
            children=[
                dcc.Tab(
                    label="Range Bar Chart",
                    value="tab-rb",
                    style=_TAB_STYLE,
                    selected_style=_TAB_SELECTED,
                    children=[_tab1_layout],
                ),
                dcc.Tab(
                    label="Cinema",
                    value="tab-cinema",
                    style=_TAB_STYLE,
                    selected_style=_TAB_SELECTED,
                    children=[_tab2_layout],
                ),
            ],
        ),
    ],
)


# Register home page
dash.register_page("home", path="/", layout=_main_layout)

# Wrap in page_container for multi-page support
app.layout = html.Div([dash.page_container])


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
# Cinema helpers
# ---------------------------------------------------------------------------

def _results_to_store(results) -> dict:
    """Serialize BacktestResults to JSON-serialisable dict for dcc.Store."""

    def _safe_val(v):
        if hasattr(v, "isoformat"):
            return str(v)
        return v

    def _rows_to_json(df):
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        return [{k: _safe_val(v) for k, v in row.items()} for row in records]

    eq = results.equity_curve
    dd = results.drawdown_curve
    dcrd_tl = results.dcrd_timeline

    return {
        "run_id": getattr(results, "run_id", None),
        "trades": _rows_to_json(results.to_trade_log_df()),
        "equity": {
            "timestamps": [str(t) for t in eq.index] if eq is not None else [],
            "values": list(eq.values) if eq is not None else [],
        },
        "drawdown": {
            "timestamps": [str(t) for t in dd.index] if dd is not None else [],
            "values": list(dd.values) if dd is not None else [],
        },
        "dcrd": _rows_to_json(dcrd_tl),
        "summary": {
            "net_profit_usd": results.net_profit_usd(),
            "sharpe": results.sharpe_ratio(),
            "max_drawdown_pct": results.max_drawdown_pct(),
            "profit_factor": results.profit_factor(),
            "win_rate": results.win_rate(),
            "total_trades": len(results.all_trades),
            "total_r": results.total_r(),
            "cycles_passed": sum(1 for c in results.cycles if c.passed) if results.cycles else None,
            "total_cycles": len(results.cycles) if results.cycles else None,
        },
    }


def _build_equity_figure(store_data: dict) -> go.Figure:
    """Equity curve + drawdown overlay (secondary y-axis)."""
    eq = store_data.get("equity", {})
    dd = store_data.get("drawdown", {})
    eq_ts = eq.get("timestamps", [])
    eq_vals = eq.get("values", [])
    dd_ts = dd.get("timestamps", [])
    dd_vals = dd.get("values", [])

    if not eq_ts:
        return _empty_figure("No equity data")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=eq_ts, y=eq_vals,
        name="Equity ($)", mode="lines",
        line=dict(color="#2ecc71", width=2),
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=dd_ts, y=[v * 100 for v in dd_vals],
        name="Drawdown %", mode="lines",
        line=dict(color="#e74c3c", width=1),
        fill="tozeroy",
        fillcolor="rgba(231,76,60,0.2)",
    ), secondary_y=True)

    fig.update_layout(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        font=dict(color="#e0e0e0", size=11),
        margin=dict(l=60, r=70, t=20, b=30),
        legend=dict(bgcolor="rgba(0,0,0,0.4)", x=0.01, y=0.99),
        hovermode="x unified",
        xaxis=dict(gridcolor="#2a2a4a"),
    )
    fig.update_yaxes(title_text="Equity ($)", gridcolor="#2a2a4a", secondary_y=False)
    fig.update_yaxes(title_text="Drawdown %", gridcolor="#2a2a4a", secondary_y=True)
    return fig


def _build_dcrd_figure(store_data: dict) -> go.Figure:
    """DCRD composite-score timeline with regime colour bands."""
    dcrd_rows = store_data.get("dcrd", [])

    if not dcrd_rows:
        return _empty_figure("No DCRD timeline data")

    dcrd_df = pd.DataFrame(dcrd_rows)

    fig = go.Figure()

    # Background regime bands
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(46,204,113,0.08)", line_width=0, layer="below")
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(241,196,15,0.08)", line_width=0, layer="below")
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(231,76,60,0.08)", line_width=0, layer="below")

    if {"pair", "score", "time"}.issubset(dcrd_df.columns):
        for pair in dcrd_df["pair"].unique():
            pair_df = dcrd_df[dcrd_df["pair"] == pair].sort_values("time")
            fig.add_trace(go.Scatter(
                x=pair_df["time"],
                y=pair_df["score"],
                name=pair,
                mode="lines",
                line=dict(width=1.5),
            ))

    # Threshold lines
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(46,204,113,0.5)", line_width=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(231,76,60,0.5)", line_width=1)

    fig.update_layout(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        font=dict(color="#e0e0e0", size=11),
        margin=dict(l=60, r=20, t=20, b=30),
        legend=dict(bgcolor="rgba(0,0,0,0.4)", x=0.01, y=0.99),
        yaxis=dict(range=[0, 100], gridcolor="#2a2a4a", title="CS"),
        xaxis=dict(gridcolor="#2a2a4a"),
        hovermode="x unified",
    )
    return fig


def _build_rb_figure(store_data: dict, rb_pair: str) -> go.Figure:
    """Range Bar candlesticks + entry/partial-exit/close trade markers."""
    from src.config import PIP_SIZE, RANGE_BAR_PIPS

    bar_pips = RANGE_BAR_PIPS.get(rb_pair, 10)
    pip_size = PIP_SIZE.get(rb_pair, 0.0001)

    rb_df = _try_load_range_bars(rb_pair, bar_pips)
    if rb_df is None or rb_df.empty:
        return _empty_figure(f"No Range Bar cache for {rb_pair}\nRun data fetcher first")

    rb_df = rb_df.tail(500).copy().reset_index(drop=True)
    x_rb = list(range(len(rb_df)))

    tick_step = max(1, len(rb_df) // 20)
    tick_vals = list(range(0, len(rb_df), tick_step))
    tick_text = [rb_df["start_time"].iloc[i].strftime("%m/%d %H:%M") for i in tick_vals]

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=x_rb,
        open=rb_df["open"], high=rb_df["high"],
        low=rb_df["low"], close=rb_df["close"],
        name=f"{rb_pair} RB{bar_pips}",
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
        whiskerwidth=0,
    ))

    # Helper: map timestamp string to nearest RB x index
    rb_end_times = pd.to_datetime(rb_df["end_time"], utc=True)

    def _ts_to_x(ts_str):
        if not ts_str:
            return None
        try:
            ts = pd.Timestamp(ts_str)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            return int((rb_end_times - ts).abs().argmin())
        except Exception:
            return None

    # Collect marker coordinates
    entry_x, entry_y, entry_text = [], [], []
    partial_x, partial_y, partial_text = [], [], []
    close_x, close_y, close_text = [], [], []

    pair_trades = [t for t in store_data.get("trades", []) if t.get("pair") == rb_pair]
    for t in pair_trades:
        strategy = t.get("strategy", "")

        ex = _ts_to_x(t.get("entry_time"))
        if ex is not None:
            entry_x.append(ex)
            entry_y.append(t.get("entry_price"))
            entry_text.append(
                f"{strategy}<br>Entry: {t.get('entry_price')}<br>Dir: {t.get('direction')}"
            )

        pe_x = _ts_to_x(t.get("partial_exit_time"))
        if pe_x is not None and t.get("partial_exit_price"):
            partial_x.append(pe_x)
            partial_y.append(t.get("partial_exit_price"))
            partial_text.append(f"1.5R partial: {t.get('partial_exit_price')}")

        cx = _ts_to_x(t.get("close_time"))
        if cx is not None and t.get("close_price"):
            close_x.append(cx)
            close_y.append(t.get("close_price"))
            close_text.append(
                f"Close ({t.get('close_reason')})<br>R: {t.get('r_multiple_total', 0):.2f}"
            )

    if entry_x:
        fig.add_trace(go.Scatter(
            x=entry_x, y=entry_y, mode="markers", name="Entry",
            marker=dict(symbol="triangle-up", size=11, color="#2ecc71",
                        line=dict(color="white", width=1)),
            text=entry_text, hoverinfo="text",
        ))

    if partial_x:
        fig.add_trace(go.Scatter(
            x=partial_x, y=partial_y, mode="markers", name="1.5R Partial",
            marker=dict(symbol="diamond", size=9, color="#f0a500",
                        line=dict(color="white", width=1)),
            text=partial_text, hoverinfo="text",
        ))

    if close_x:
        fig.add_trace(go.Scatter(
            x=close_x, y=close_y, mode="markers", name="Close",
            marker=dict(symbol="x", size=10, color="#e74c3c",
                        line=dict(color="#e74c3c", width=2)),
            text=close_text, hoverinfo="text",
        ))

    fig.update_layout(
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        font=dict(color="#e0e0e0", size=11),
        margin=dict(l=60, r=20, t=20, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0.4)", x=0.01, y=0.99),
        xaxis=dict(
            rangeslider=dict(visible=False),
            tickvals=tick_vals, ticktext=tick_text, tickangle=-45,
            gridcolor="#2a2a4a",
        ),
        yaxis=dict(gridcolor="#2a2a4a", side="right",
                   tickformat=f".{_decimal_places(pip_size)}f"),
        hovermode="x unified",
    )
    return fig


def _build_trade_table(store_data: dict) -> list:
    """Build HTML trade log table from store data."""
    trades = store_data.get("trades", [])
    if not trades:
        return [html.P("No trades to display.", style={"color": "#666", "fontSize": "13px"})]

    columns = [
        "entry_time", "pair", "strategy", "direction", "composite_score",
        "entry_price", "partial_exit_price", "close_price",
        "close_reason", "r_multiple_total", "pnl_usd",
    ]
    headers = [
        "Date", "Pair", "Strategy", "Dir", "CS",
        "Entry", "Part.Exit", "Close", "Reason", "R-Mult", "PnL ($)", "Inspect",
    ]

    def _fmt(val, col):
        if val is None:
            return "\u2014"
        if col in ("entry_price", "partial_exit_price", "close_price"):
            try:
                return f"{float(val):.5f}"
            except (TypeError, ValueError):
                return str(val)
        if col == "r_multiple_total":
            try:
                return f"{float(val):+.2f}R"
            except (TypeError, ValueError):
                return str(val)
        if col == "pnl_usd":
            try:
                return f"${float(val):+.2f}"
            except (TypeError, ValueError):
                return str(val)
        if col == "composite_score":
            try:
                return f"{float(val):.0f}"
            except (TypeError, ValueError):
                return str(val)
        if col == "entry_time":
            return str(val)[:16]
        return str(val) if val else "\u2014"

    def _row_bg(t):
        try:
            r = float(t.get("r_multiple_total") or 0)
        except (TypeError, ValueError):
            r = 0
        if r > 0:
            return "rgba(46,204,113,0.08)"
        if r < 0:
            return "rgba(231,76,60,0.08)"
        return "transparent"

    th_style = {
        "padding": "6px 10px", "color": "#aaa", "fontWeight": "bold",
        "borderBottom": "1px solid #333", "fontSize": "12px", "textAlign": "center",
    }
    td_style = {
        "padding": "4px 10px", "color": "#ccc", "fontSize": "12px",
        "textAlign": "center", "borderBottom": "1px solid #222",
    }

    # Extract run_id from store_data
    run_id = store_data.get("run_id", "unknown")
    
    header_row = html.Tr([html.Th(h, style=th_style) for h in headers])
    rows = [header_row]
    for idx, t in enumerate(trades[:200]):  # cap at 200 rows for browser performance
        cells = [html.Td(_fmt(t.get(col), col), style=td_style) for col in columns]
        # Add Inspect link cell
        inspect_cell = html.Td(
            dcc.Link("Inspect", href=f"/inspector?run={run_id}&trade={idx}"),
            style=td_style,
        )
        cells.append(inspect_cell)
        rows.append(html.Tr(cells, style={"backgroundColor": _row_bg(t)}))

    return [html.Table(
        rows,
        style={"width": "100%", "borderCollapse": "collapse",
               "backgroundColor": "#16213e", "borderRadius": "4px"},
    )]


# ---------------------------------------------------------------------------
# Cinema callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("cinema-results-store", "data"),
    Output("cinema-status", "children"),
    Input("cinema-run-btn", "n_clicks"),
    Input("cinema-load-btn", "n_clicks"),
    State("cinema-pairs", "value"),
    State("cinema-date-range", "start_date"),
    State("cinema-date-range", "end_date"),
    State("cinema-mode", "value"),
    prevent_initial_call=True,
)
def cinema_run_or_load(run_clicks, load_clicks, pairs, start_date, end_date, mode):
    """Run a new backtest or load the latest saved run into the results store."""
    from dash import ctx

    triggered = ctx.triggered_id

    if not BACKTESTER_AVAILABLE:
        return None, "Backtester not available — check package imports."

    if triggered == "cinema-load-btn":
        results_dir = Path(BACKTEST_RESULTS_DIR)
        if not results_dir.exists():
            return None, "No results directory found. Run a backtest first."
        run_dirs = sorted(results_dir.glob("run_*"), reverse=True)
        if not run_dirs:
            return None, "No saved runs found. Click 'Run Backtest' first."
        try:
            results = BacktestResults.load(str(run_dirs[0]))
            store = _results_to_store(results)
            store["run_id"] = run_dirs[0].name  # Set run_id from directory name
            s = store["summary"]
            status = (
                f"Loaded: {run_dirs[0].name} | "
                f"Net P&L: ${s['net_profit_usd']:+.2f} | "
                f"Sharpe: {s['sharpe']:.2f} | "
                f"Max DD: {s['max_drawdown_pct']:.1f}% | "
                f"Trades: {s['total_trades']}"
            )
            return store, status
        except Exception as e:
            return None, f"Error loading results: {e}"

    # cinema-run-btn triggered
    if not pairs:
        return None, "Select at least one pair before running."
    try:
        start = pd.Timestamp(start_date, tz="UTC")
        end = pd.Timestamp(end_date, tz="UTC")
    except Exception as e:
        return None, f"Invalid date range: {e}"

    try:
        engine = BacktestEngine(pairs=pairs)

        if mode == "walkforward":
            wf = WalkForwardManager()
            results = wf.run_all(
                engine=engine,
                pairs=pairs,
                data_start=start,
                data_end=end,
                initial_equity=500.0,
            )
        else:
            results = engine.run(start=start, end=end, initial_equity=500.0)

        # Persist results
        results_dir = Path(BACKTEST_RESULTS_DIR)
        results_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone as _tz
        ts_tag = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{ts_tag}"
        results.save(str(results_dir / run_id))

        store = _results_to_store(results)
        store["run_id"] = run_id  # Set run_id
        s = store["summary"]
        cycles_str = (
            f" | Cycles: {s['cycles_passed']}/{s['total_cycles']}"
            if s["total_cycles"] else ""
        )
        status = (
            f"Net P&L: ${s['net_profit_usd']:+.2f} | "
            f"Sharpe: {s['sharpe']:.2f} | "
            f"Max DD: {s['max_drawdown_pct']:.1f}% | "
            f"Win Rate: {s['win_rate']:.1%} | "
            f"PF: {s['profit_factor']:.2f} | "
            f"Trades: {s['total_trades']}"
            f"{cycles_str}"
        )
        return store, status

    except Exception as e:
        log.exception("Backtest run failed")
        return None, f"Backtest failed: {e}"


@callback(
    Output("cinema-equity-chart", "figure"),
    Output("cinema-dcrd-chart", "figure"),
    Output("cinema-rb-chart", "figure"),
    Output("cinema-trade-table", "children"),
    Input("cinema-results-store", "data"),
    Input("cinema-rb-pair", "value"),
)
def cinema_update_charts(store_data, rb_pair):
    """Populate all Cinema panels from the results store."""
    if not store_data:
        empty = _empty_figure("Run a backtest or load a previous run")
        return (
            empty, empty, empty,
            [html.P("No results loaded.", style={"color": "#666", "fontSize": "13px"})],
        )

    equity_fig = _build_equity_figure(store_data)
    dcrd_fig = _build_dcrd_figure(store_data)
    rb_fig = _build_rb_figure(store_data, rb_pair or PAIRS[0])
    trade_tbl = _build_trade_table(store_data)

    return equity_fig, dcrd_fig, rb_fig, trade_tbl


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

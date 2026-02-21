"""
JcampFX — Trade Inspector Page (Phase 3.5)

Bar-by-bar playback visualization for individual trades.
Shows 20-bar context window + entry/pullback/close markers + DCRD timeline.
"""

import logging
from pathlib import Path

import dash
from dash import dcc, html, callback, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester.playback import get_trade_context

dash.register_page(__name__, path="/inspector", title="Trade Inspector")

log = logging.getLogger(__name__)

# Version marker for debugging cache issues
_INSPECTOR_VERSION = "2026-02-21-v17"

# Print at module load time to verify file is being imported
print(f"[INSPECTOR MODULE LOADED] Version {_INSPECTOR_VERSION}", flush=True)

# ============================================================================
# Layout
# ============================================================================

layout = html.Div([
    # Header with controls
    html.Div([
        html.H2("Trade Inspector", style={"margin": "0", "color": "#1a1a1a", "display": "inline-block", "marginRight": "30px"}),
        html.Div([
            html.Label("Bars Before Entry:", style={"color": "#666", "fontSize": "12px", "marginRight": "8px"}),
            dcc.Input(
                id="bars-before-input",
                type="number",
                value=20,
                min=5,
                max=100,
                step=5,
                style={"width": "70px", "marginRight": "20px", "fontSize": "13px"},
            ),
            html.Label("Bars After Close:", style={"color": "#666", "fontSize": "12px", "marginRight": "8px"}),
            dcc.Input(
                id="bars-after-input",
                type="number",
                value=5,
                min=0,
                max=50,
                step=5,
                style={"width": "70px", "marginRight": "20px", "fontSize": "13px"},
            ),
            html.Button(
                "Update View",
                id="update-context-btn",
                n_clicks=0,
                style={"background": "#4a90d9", "color": "white", "border": "none",
                       "padding": "4px 12px", "borderRadius": "4px", "cursor": "pointer", "fontSize": "13px"},
            ),
        ], style={"display": "inline-block"}),
    ], style={"marginBottom": "20px", "display": "flex", "alignItems": "center"}),

    # Trade metadata panel
    html.Div(id="inspector-metadata", style={
        "background": "#1e1e1e",
        "padding": "15px",
        "border-radius": "5px",
        "margin-bottom": "20px",
        "font-family": "monospace",
        "color": "#e0e0e0",  # Light gray text for dark background
    }),

    # Main chart: Range Bars + DCRD timeline
    dcc.Graph(id="inspector-chart", style={"height": "70vh"}),

    # Hidden stores for state
    dcc.Store(id="inspector-run-id"),
    dcc.Store(id="inspector-trade-id"),
    dcc.Store(id="inspector-all-trade-ids"),  # list of all trade IDs in run (for prev/next)
])


# ============================================================================
# Callbacks
# ============================================================================

@callback(
    [
        Output("inspector-metadata", "children"),
        Output("inspector-chart", "figure"),
        Output("inspector-run-id", "data"),
        Output("inspector-trade-id", "data"),
        Output("inspector-all-trade-ids", "data"),
    ],
    [
        Input("url", "search"),  # URL query string: ?run=X&trade=Y
        Input("update-context-btn", "n_clicks"),
    ],
    [
        State("url", "pathname"),
        State("bars-before-input", "value"),
        State("bars-after-input", "value"),
    ],
    prevent_initial_call=False,
)
def load_inspector_view(search_query: str | None, n_clicks: int, pathname: str | None,
                        bars_before: int = 20, bars_after: int = 5):
    """
    Parse URL parameters, load trade context, render metadata + chart.
    """
    import traceback

    # Only process if we're actually on the inspector page
    if pathname != "/inspector":
        raise PreventUpdate

    # Wrap EVERYTHING in try/except to catch any errors
    try:
        # DEBUG: Log what we actually receive
        print(f"[Inspector v{_INSPECTOR_VERSION}] Callback triggered with search_query={search_query!r}", flush=True)
        log.info(f"[Inspector v{_INSPECTOR_VERSION}] Callback triggered with search_query={search_query!r}")

        # Parse query string
        params = _parse_query_string(search_query)
        print(f"[Inspector] Parsed params={params}", flush=True)
        run_id = params.get("run")
        trade_id = params.get("trade")

        if not run_id or not trade_id:
            print(f"[Inspector] No run_id or trade_id, returning empty", flush=True)
            return (
                html.Div(f"No trade specified. Navigate from Cinema tab. (Inspector {_INSPECTOR_VERSION})",
                         style={"color": "red"}),
                go.Figure(),
                None,
                None,
                [],
            )

        # Build run directory path
        run_dir = Path("data/backtest_results") / run_id
        print(f"[Inspector] run_dir={run_dir}, exists={run_dir.exists()}", flush=True)
        if not run_dir.exists():
            return (
                html.Div(f"Run directory not found: {run_dir}", style={"color": "red"}),
                go.Figure(),
                None,
                None,
                [],
            )

        # Load all trade IDs for prev/next navigation
        print(f"[Inspector] Loading trades.parquet...", flush=True)
        trades_df = pd.read_parquet(run_dir / "trades.parquet")
        all_trade_ids = trades_df["trade_id"].tolist()
        print(f"[Inspector] Loaded {len(all_trade_ids)} trade IDs", flush=True)

        # Load trade context
        print(f"[Inspector] Loading trade context for {trade_id}...", flush=True)
        try:
            # Use user-specified context window or defaults
            ctx = get_trade_context(
                str(run_dir),
                trade_id,
                context_bars=bars_before or 20,
                bars_after_close=bars_after or 5,
            )
            print(f"[Inspector] Trade context loaded successfully", flush=True)
        except Exception as exc:
            print(f"[Inspector] ERROR loading trade context: {exc}", flush=True)
            traceback.print_exc()
            log.exception("Failed to load trade context")
            return (
                html.Div(f"Error loading trade: {exc}", style={"color": "red"}),
                go.Figure(),
                run_id,
                trade_id,
                all_trade_ids,
            )

        # Build metadata panel
        print(f"[Inspector] Building metadata panel...", flush=True)
        metadata_panel = _build_metadata_panel(ctx)
        print(f"[Inspector] Metadata panel built", flush=True)

        # Build chart
        print(f"[Inspector] Building chart...", flush=True)
        chart_fig = _build_inspector_chart(ctx, context_bars=bars_before or 20)
        print(f"[Inspector] Chart built with {len(chart_fig.data)} traces", flush=True)

        print(f"[Inspector] Returning successful result", flush=True)
        return metadata_panel, chart_fig, run_id, trade_id, all_trade_ids

    except Exception as e:
        # Catch ANY error and print full traceback
        print(f"[Inspector] FATAL ERROR: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        # Re-raise so Dash knows there was an error
        raise


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_query_string(search: str | None) -> dict:
    """Parse URL query string like '?run=X&trade=Y' into dict."""
    if not search or not isinstance(search, str) or not search.startswith("?"):
        return {}
    params = {}
    for part in search[1:].split("&"):
        if "=" in part:
            key, val = part.split("=", 1)
            params[key] = val
    return params


def _build_metadata_panel(ctx: dict) -> html.Div:
    """
    Build HTML metadata panel showing trade details, DCRD scores, and outcome.
    """
    trade = ctx["trade"]
    dcrd = ctx["dcrd_at_entry"]

    # Determine outcome
    partial_exit_time = trade.get("partial_exit_time")
    if partial_exit_time is not None and not pd.isna(partial_exit_time):
        outcome = f"✅ WIN (reached 1.5R at partial exit)"
    else:
        outcome = f"❌ LOSS (SL hit before partial)"

    # Build metadata rows
    metadata_rows = [
        html.Div([
            html.Span(f"Trade ID: {trade['trade_id']}", style={"font-weight": "bold", "margin-right": "20px", "color": "#fff"}),
            html.Span(f"{trade['pair']} {trade['direction']}", style={"margin-right": "20px", "color": "#4fc3f7"}),
            html.Span(outcome, style={"margin-right": "20px"}),
            html.Span(f"Total R: {trade.get('r_multiple_total', 0):.2f}R", style={"margin-right": "20px", "color": "#fff"}),
        ]),
        html.Hr(style={"margin": "10px 0", "border-color": "#444"}),
        html.Div([
            html.Span(f"Entry: {trade['entry_price']} @ {trade['entry_time']}", style={"margin-right": "20px", "color": "#aaa"}),
            html.Span(f"SL: {trade['sl_price']}", style={"margin-right": "20px", "color": "#aaa"}),
            html.Span(f"TP: {trade.get('tp_price', 'N/A')}", style={"margin-right": "20px", "color": "#aaa"}),
        ]),
        html.Hr(style={"margin": "10px 0", "border-color": "#444"}),
        html.Div([
            html.Span(f"Composite Score at Entry: {dcrd['composite_score']:.1f}",
                      style={"font-weight": "bold", "margin-right": "20px", "color": "#ffd54f"}),
            html.Span(f"Regime: {dcrd['regime'].upper()}", style={"margin-right": "20px", "color": "#81c784"}),
            html.Span(f"Strategy: {trade.get('strategy', 'N/A')}", style={"margin-right": "20px", "color": "#81c784"}),
        ]),
        html.Div([
            html.Span(f"L1 Structural: {dcrd['layer1_structural']:.1f}", style={"margin-right": "15px", "color": "#888"}),
            html.Span(f"L2 Modifier: {dcrd['layer2_modifier']:+.1f}", style={"margin-right": "15px", "color": "#888"}),
            html.Span(f"L3 RB Intel: {dcrd['layer3_rb_intelligence']:.1f}", style={"margin-right": "15px", "color": "#888"}),
        ], style={"margin-top": "10px"}),
    ]

    # Add TrendRider-specific debug metadata if present
    if trade.get("staircase_depth"):
        tr_meta = html.Div([
            html.Hr(style={"margin": "10px 0", "border-color": "#444"}),
            html.Div([
                html.Span(f"Staircase Depth: {trade.get('staircase_depth', 0)} bars",
                          style={"margin-right": "15px", "color": "#ce93d8"}),
                html.Span(f"ADX at Entry: {trade.get('adx_at_entry', 0):.1f}",
                          style={"margin-right": "15px", "color": "#ce93d8"}),
                html.Span(f"ADX Rising: {trade.get('adx_slope_rising', False)}",
                          style={"margin-right": "15px", "color": "#ce93d8"}),
            ]),
            html.Div([
                html.Span(f"Pullback Bar Idx: {trade.get('pullback_bar_idx', 'N/A')}",
                          style={"margin-right": "15px", "color": "#888"}),
                html.Span(f"Pullback Depth: {trade.get('pullback_depth_pips', 0):.1f} pips",
                          style={"margin-right": "15px", "color": "#888"}),
                html.Span(f"Entry Bar Idx: {trade.get('entry_bar_idx', 'N/A')}",
                          style={"margin-right": "15px", "color": "#888"}),
            ], style={"margin-top": "5px"}),
        ])
        metadata_rows.append(tr_meta)

    return html.Div(metadata_rows)


def _build_inspector_chart(ctx: dict, context_bars: int = 20) -> go.Figure:
    """
    Build 2-panel chart:
      Top: Range Bar candlesticks with entry/pullback/partial/close markers
      Bottom: DCRD Composite Score timeline

    Parameters
    ----------
    ctx : Trade context from get_trade_context()
    context_bars : Number of bars before entry (used for staircase offset calculation)
    """
    rb = ctx["range_bars"]
    dcrd_per_bar = ctx["dcrd_per_bar"]
    trade = ctx["trade"]

    entry_local = ctx["entry_bar_local_idx"]
    partial_local = ctx["partial_exit_bar_local_idx"]
    close_local = ctx["close_bar_local_idx"]

    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],  # Give more space to price action
        subplot_titles=("Range Bar Price Action", "DCRD Composite Score"),
    )

    # === Top panel: Range Bar candlesticks ===
    fig.add_trace(
        go.Candlestick(
            x=rb.index,
            open=rb["open"],
            high=rb["high"],
            low=rb["low"],
            close=rb["close"],
            name="Range Bars",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            showlegend=False,  # Don't clutter legend with candlesticks
        ),
        row=1, col=1,
    )

    # Add trade markers (Cinema-style scatter markers instead of lines)
    entry_price = trade["entry_price"]
    sl_price = trade["sl_price"]
    tp_price = trade.get("tp_price")
    close_price = trade.get("close_price")
    strategy = trade.get("strategy", "")
    direction = trade.get("direction", "")

    # Entry marker
    if entry_local is not None:
        fig.add_trace(
            go.Scatter(
                x=[entry_local],
                y=[entry_price],
                mode="markers",
                name="Entry",
                marker=dict(
                    symbol="triangle-up",
                    size=12,
                    color="#2ecc71",
                    line=dict(color="white", width=1.5),
                ),
                text=[f"{strategy}<br>Entry: {entry_price:.5f}<br>Dir: {direction}"],
                hoverinfo="text",
                showlegend=True,
            ),
            row=1, col=1,
        )

    # Partial exit marker (1.5R)
    if partial_local is not None:
        partial_price = rb.iloc[partial_local]["close"] if partial_local < len(rb) else entry_price
        fig.add_trace(
            go.Scatter(
                x=[partial_local],
                y=[partial_price],
                mode="markers",
                name="1.5R Partial",
                marker=dict(
                    symbol="diamond",
                    size=10,
                    color="#f0a500",
                    line=dict(color="white", width=1.5),
                ),
                text=[f"1.5R partial: {partial_price:.5f}"],
                hoverinfo="text",
                showlegend=True,
            ),
            row=1, col=1,
        )

    # Close marker
    if close_local is not None and close_price:
        close_reason = trade.get("close_reason", "")
        r_total = trade.get("r_multiple_total", 0)
        fig.add_trace(
            go.Scatter(
                x=[close_local],
                y=[close_price],
                mode="markers",
                name="Close",
                marker=dict(
                    symbol="x",
                    size=11,
                    color="#e74c3c",
                    line=dict(color="#e74c3c", width=2.5),
                ),
                text=[f"Close ({close_reason})<br>R: {r_total:.2f}"],
                hoverinfo="text",
                showlegend=True,
            ),
            row=1, col=1,
        )

    # Add subtle horizontal reference lines for SL/TP (thin, not intrusive)
    fig.add_hline(y=entry_price, line_color="rgba(46,204,113,0.3)", line_width=0.5, line_dash="dot", row=1)
    fig.add_hline(y=sl_price, line_color="rgba(231,76,60,0.3)", line_width=0.5, line_dash="dot", row=1)

    # Highlight staircase bars if TrendRider trade (only if debug fields exist)
    if (trade.get("strategy") == "TrendRider" and
        trade.get("pullback_bar_idx") is not None and
        trade.get("entry_bar_idx") is not None and
        trade.get("staircase_depth") is not None):
        pullback_abs_idx = trade["pullback_bar_idx"]
        entry_abs_idx = trade["entry_bar_idx"]
        staircase_depth = trade["staircase_depth"]

        # Find local indices for staircase
        # Staircase is: pullback_bar_idx - staircase_depth → pullback_bar_idx
        staircase_start_abs = pullback_abs_idx - staircase_depth + 1

        # Map absolute indices to local indices
        # rb window starts at (entry_abs_idx - context_bars), so:
        # local = abs - (entry_abs_idx - context_bars) = abs - entry_abs_idx + context_bars
        offset = entry_abs_idx - context_bars
        staircase_start_local = staircase_start_abs - offset
        pullback_local = pullback_abs_idx - offset

        if staircase_start_local >= 0 and pullback_local < len(rb):
            fig.add_vrect(
                x0=max(0, staircase_start_local) - 0.5,
                x1=pullback_local + 0.5,
                fillcolor="purple",
                opacity=0.15,
                layer="below",
                line_width=0,
                annotation_text="Staircase",
                annotation_position="top left",
                row=1,
            )

    # === Bottom panel: DCRD timeline ===
    if not dcrd_per_bar.empty and "composite_score" in dcrd_per_bar.columns:
        # Match DCRD bars to Range Bar indices
        # dcrd_per_bar has 'time' column, rb has 'end_time'
        dcrd_x = []
        dcrd_y = []
        for i, rb_row in rb.iterrows():
            matches = dcrd_per_bar[dcrd_per_bar["time"] <= rb_row["end_time"]]
            if not matches.empty:
                dcrd_x.append(i)
                dcrd_y.append(matches.iloc[-1]["composite_score"])

        fig.add_trace(
            go.Scatter(
                x=dcrd_x,
                y=dcrd_y,
                mode="lines+markers",
                name="Composite Score",
                line=dict(color="orange", width=2),
                marker=dict(size=4),
                showlegend=False,
            ),
            row=2, col=1,
        )

        # Add regime threshold lines
        fig.add_hline(y=70, line_color="green", line_dash="dot", line_width=1,
                      annotation_text="TrendRider", annotation_position="right", row=2)
        fig.add_hline(y=30, line_color="blue", line_dash="dot", line_width=1,
                      annotation_text="RangeRider", annotation_position="right", row=2)

    # Layout - Calculate pip-based grid spacing
    pair = trade["pair"]
    pip_multiplier = 0.01 if "JPY" in pair else 0.0001

    # Get price range and expand it for better vertical spacing
    y_min = rb["low"].min()
    y_max = rb["high"].max()
    y_range = y_max - y_min

    # Add 30% padding on each side for better vertical spacing
    y_padding = y_range * 0.3
    y_min_padded = y_min - y_padding
    y_max_padded = y_max + y_padding

    # Calculate pip spacing in price units
    pip_10_price = 10 * pip_multiplier  # Grid lines every 10 pips
    pip_20_price = 20 * pip_multiplier  # Labels every 20 pips

    # Calculate pip distance from entry for secondary axis
    pips_from_entry_min = (y_min_padded - entry_price) / pip_multiplier
    pips_from_entry_max = (y_max_padded - entry_price) / pip_multiplier

    # Update axes
    fig.update_xaxes(title_text="Bar Index", row=2, col=1)
    fig.update_yaxes(
        title_text="Price",
        side="left",
        range=[y_min_padded, y_max_padded],
        tick0=0,
        dtick=pip_20_price,  # Labels every 20 pips
        showgrid=False,  # Grid added manually below
        tickfont=dict(size=11),
        row=1,
        col=1,
    )

    fig.update_yaxes(
        title_text="CS",
        range=[0, 100],
        showgrid=True,
        gridcolor="#333",
        row=2,
        col=1,
    )

    # Add 10-pip grid lines manually using shapes (subtle background lines)
    import numpy as np
    # Round to nearest 10-pip boundary
    y_start = np.floor(y_min_padded / pip_10_price) * pip_10_price
    y_end = np.ceil(y_max_padded / pip_10_price) * pip_10_price

    # Add thin grid lines at every 10 pips
    num_lines = int((y_end - y_start) / pip_10_price) + 1
    for i in range(num_lines):
        y_val = y_start + (i * pip_10_price)
        if y_min_padded <= y_val <= y_max_padded:
            # Every other line (20 pips) is slightly more visible
            if i % 2 == 0:
                fig.add_hline(y=y_val, line_color="#333", line_width=0.8, row=1)
            else:
                fig.add_hline(y=y_val, line_color="#222", line_width=0.5, row=1)

    # Configure layout with secondary y-axis and zoom controls
    fig.update_layout(
        yaxis2=dict(
            title=dict(text="<b>Pips from Entry</b>", font=dict(size=12, color="#ffd54f")),
            overlaying="y",
            side="right",
            range=[pips_from_entry_min, pips_from_entry_max],
            tickmode="linear",
            dtick=20,  # Labels every 20 pips
            showgrid=False,
            tickfont=dict(size=11, color="#ffd54f"),
        ),
        height=900,  # Increased height for better vertical space
        margin=dict(l=60, r=80, t=80, b=40),  # Tighter margins
        template="plotly_dark",
        showlegend=True,
        legend=dict(
            bgcolor="rgba(0,0,0,0.6)",
            bordercolor="#444",
            borderwidth=1,
            font=dict(size=10),
            x=0.01,
            y=0.99,
        ),
        hovermode="x unified",
        dragmode="zoom",  # Enable zoom/pan
    )

    return fig

"""
JcampFX — Trade Inspector Page (Phase 3.5)

Bar-by-bar playback visualization for individual trades.
Shows 20-bar context window + entry/pullback/close markers + DCRD timeline.
"""

import logging
from pathlib import Path

import dash
from dash import dcc, html, callback, Input, Output, State
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester.playback import get_trade_context

dash.register_page(__name__, path="/inspector")

log = logging.getLogger(__name__)

# ============================================================================
# Layout
# ============================================================================

layout = html.Div([
    # Header with navigation
    html.Div([
        html.H2("Trade Inspector", style={"display": "inline-block", "margin-right": "20px"}),
        html.Button("← Back to Cinema", id="inspector-back-btn", n_clicks=0,
                    style={"margin-right": "10px"}),
        html.Button("← Prev Trade", id="inspector-prev-btn", n_clicks=0,
                    style={"margin-right": "10px"}),
        html.Button("Next Trade →", id="inspector-next-btn", n_clicks=0),
    ], style={"margin-bottom": "20px"}),

    # Trade metadata panel
    html.Div(id="inspector-metadata", style={
        "background": "#1e1e1e",
        "padding": "15px",
        "border-radius": "5px",
        "margin-bottom": "20px",
        "font-family": "monospace",
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
    ],
    prevent_initial_call=False,
)
def load_inspector_view(search_query: str | None):
    """
    Parse URL parameters, load trade context, render metadata + chart.
    """
    # Parse query string
    params = _parse_query_string(search_query)
    run_id = params.get("run")
    trade_id = params.get("trade")

    if not run_id or not trade_id:
        return (
            html.Div("No trade specified. Navigate from Cinema tab.", style={"color": "red"}),
            go.Figure(),
            None,
            None,
            [],
        )

    # Build run directory path
    run_dir = Path("data/backtest_results") / run_id
    if not run_dir.exists():
        return (
            html.Div(f"Run directory not found: {run_dir}", style={"color": "red"}),
            go.Figure(),
            None,
            None,
            [],
        )

    # Load all trade IDs for prev/next navigation
    trades_df = pd.read_parquet(run_dir / "trades.parquet")
    all_trade_ids = trades_df["trade_id"].tolist()

    # Load trade context
    try:
        ctx = get_trade_context(str(run_dir), trade_id, context_bars=20)
    except Exception as exc:
        log.exception("Failed to load trade context")
        return (
            html.Div(f"Error loading trade: {exc}", style={"color": "red"}),
            go.Figure(),
            run_id,
            trade_id,
            all_trade_ids,
        )

    # Build metadata panel
    metadata_panel = _build_metadata_panel(ctx)

    # Build chart
    chart_fig = _build_inspector_chart(ctx)

    return metadata_panel, chart_fig, run_id, trade_id, all_trade_ids


@callback(
    Output("url", "pathname", allow_duplicate=True),
    [
        Input("inspector-back-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def navigate_back_to_cinema(n_clicks):
    """Return to Cinema tab (home page)."""
    if n_clicks > 0:
        return "/"  # Navigate to home page
    return dash.no_update


@callback(
    Output("url", "search", allow_duplicate=True),
    [
        Input("inspector-prev-btn", "n_clicks"),
        Input("inspector-next-btn", "n_clicks"),
    ],
    [
        State("inspector-run-id", "data"),
        State("inspector-trade-id", "data"),
        State("inspector-all-trade-ids", "data"),
    ],
    prevent_initial_call=True,
)
def navigate_prev_next_trade(prev_clicks, next_clicks, run_id, trade_id, all_trade_ids):
    """Navigate to previous or next trade in the same run."""
    if not run_id or not trade_id or not all_trade_ids:
        return dash.no_update

    try:
        current_idx = all_trade_ids.index(trade_id)
    except ValueError:
        return dash.no_update

    triggered_id = dash.callback_context.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "inspector-prev-btn" and prev_clicks > 0:
        new_idx = max(0, current_idx - 1)
    elif triggered_id == "inspector-next-btn" and next_clicks > 0:
        new_idx = min(len(all_trade_ids) - 1, current_idx + 1)
    else:
        return dash.no_update

    new_trade_id = all_trade_ids[new_idx]
    return f"?run={run_id}&trade={new_trade_id}"


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
            html.Span(f"Trade ID: {trade['trade_id']}", style={"font-weight": "bold", "margin-right": "20px"}),
            html.Span(f"{trade['pair']} {trade['direction']}", style={"margin-right": "20px"}),
            html.Span(outcome, style={"margin-right": "20px"}),
            html.Span(f"Total R: {trade.get('r_multiple_total', 0):.2f}R", style={"margin-right": "20px"}),
        ]),
        html.Hr(style={"margin": "10px 0"}),
        html.Div([
            html.Span(f"Entry: {trade['entry_price']} @ {trade['entry_time']}", style={"margin-right": "20px"}),
            html.Span(f"SL: {trade['sl_price']}", style={"margin-right": "20px"}),
            html.Span(f"TP: {trade.get('tp_price', 'N/A')}", style={"margin-right": "20px"}),
        ]),
        html.Hr(style={"margin": "10px 0"}),
        html.Div([
            html.Span(f"Composite Score at Entry: {dcrd['composite_score']:.1f}",
                      style={"font-weight": "bold", "margin-right": "20px"}),
            html.Span(f"Regime: {dcrd['regime'].upper()}", style={"margin-right": "20px"}),
            html.Span(f"Strategy: {trade.get('strategy', 'N/A')}", style={"margin-right": "20px"}),
        ]),
        html.Div([
            html.Span(f"L1 Structural: {dcrd['layer1_structural']:.1f}", style={"margin-right": "15px"}),
            html.Span(f"L2 Modifier: {dcrd['layer2_modifier']:+.1f}", style={"margin-right": "15px"}),
            html.Span(f"L3 RB Intel: {dcrd['layer3_rb_intelligence']:.1f}", style={"margin-right": "15px"}),
        ], style={"margin-top": "10px", "color": "#888"}),
    ]

    # Add TrendRider-specific debug metadata if present
    if trade.get("staircase_depth"):
        tr_meta = html.Div([
            html.Hr(style={"margin": "10px 0"}),
            html.Div([
                html.Span(f"Staircase Depth: {trade.get('staircase_depth', 0)} bars",
                          style={"margin-right": "15px"}),
                html.Span(f"ADX at Entry: {trade.get('adx_at_entry', 0):.1f}",
                          style={"margin-right": "15px"}),
                html.Span(f"ADX Rising: {trade.get('adx_slope_rising', False)}",
                          style={"margin-right": "15px"}),
            ]),
            html.Div([
                html.Span(f"Pullback Bar Idx: {trade.get('pullback_bar_idx', 'N/A')}",
                          style={"margin-right": "15px"}),
                html.Span(f"Pullback Depth: {trade.get('pullback_depth_pips', 0):.1f} pips",
                          style={"margin-right": "15px"}),
                html.Span(f"Entry Bar Idx: {trade.get('entry_bar_idx', 'N/A')}",
                          style={"margin-right": "15px"}),
            ], style={"margin-top": "5px", "color": "#888"}),
        ], style={"color": "#aaa"})
        metadata_rows.append(tr_meta)

    return html.Div(metadata_rows)


def _build_inspector_chart(ctx: dict) -> go.Figure:
    """
    Build 2-panel chart:
      Top: Range Bar candlesticks with entry/pullback/partial/close markers
      Bottom: DCRD Composite Score timeline
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
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
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
        ),
        row=1, col=1,
    )

    # Add vertical markers for key events
    if entry_local is not None:
        fig.add_vline(x=entry_local, line_color="yellow", line_width=2, line_dash="dash",
                      annotation_text="Entry", annotation_position="top", row=1)

    if partial_local is not None:
        fig.add_vline(x=partial_local, line_color="cyan", line_width=2, line_dash="dot",
                      annotation_text="Partial Exit (1.5R)", annotation_position="top", row=1)

    if close_local is not None:
        fig.add_vline(x=close_local, line_color="red", line_width=2,
                      annotation_text="Close", annotation_position="top", row=1)

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
        # rb window starts at (entry_abs_idx - 20), so:
        # local = abs - (entry_abs_idx - 20) = abs - entry_abs_idx + 20
        offset = entry_abs_idx - 20
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
            ),
            row=2, col=1,
        )

        # Add regime threshold lines
        fig.add_hline(y=70, line_color="green", line_dash="dot", line_width=1,
                      annotation_text="TrendRider", annotation_position="right", row=2)
        fig.add_hline(y=30, line_color="blue", line_dash="dot", line_width=1,
                      annotation_text="RangeRider", annotation_position="right", row=2)

    # Layout
    fig.update_xaxes(title_text="Bar Index", row=2, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="CS", range=[0, 100], row=2, col=1)

    fig.update_layout(
        height=800,
        template="plotly_dark",
        showlegend=False,
        hovermode="x unified",
    )

    return fig

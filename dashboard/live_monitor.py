"""
JcampFX — Live Trading Dashboard (Phase 4)

Real-time web monitoring dashboard for live trading system.
Accessible at http://localhost:8050

Features:
- Live equity curve
- Open positions with R-multiples
- Recent trades history
- DCRD scores per pair
- Connection status
- News events
- System statistics
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Optional

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import pandas as pd

log = logging.getLogger(__name__)


class LiveDashboard:
    """
    Live monitoring dashboard for JcampFX trading system.

    Runs in a separate thread and provides web interface at http://localhost:8050
    """

    def __init__(self, orchestrator, port: int = 8050):
        """
        Initialize live dashboard.

        Args:
            orchestrator: BrainOrchestrator instance
            port: Port for web server (default 8050)
        """
        self.orchestrator = orchestrator
        self.port = port
        self.app = None
        self.server_thread = None

        # Data storage for charts
        self.equity_history = []
        self.trade_history = []

        log.info("LiveDashboard initialized (port %d)", port)

    def start(self):
        """Start dashboard in background thread."""
        if self.server_thread and self.server_thread.is_alive():
            log.warning("Dashboard already running")
            return

        # Create Dash app
        self.app = dash.Dash(__name__,
                            title="JcampFX Live Monitor",
                            update_title=None)  # Prevent "Updating..." title

        # Setup layout
        self._setup_layout()

        # Setup callbacks
        self._setup_callbacks()

        # Start server in background thread
        self.server_thread = Thread(target=self._run_server, daemon=True, name="Dashboard")
        self.server_thread.start()

        log.info("=" * 70)
        log.info("🎨 Live Dashboard started: http://localhost:%d", self.port)
        log.info("=" * 70)

    def _run_server(self):
        """Run Dash server (called in background thread)."""
        try:
            self.app.run(debug=False, host='0.0.0.0', port=self.port, use_reloader=False)
        except Exception as e:
            log.error("Dashboard server error: %s", e, exc_info=True)

    def _setup_layout(self):
        """Setup dashboard layout (dark mode)."""
        self.app.layout = html.Div([
            # Header
            html.Div([
                html.H1("🚀 JcampFX Live Trading Monitor",
                       style={'textAlign': 'center', 'color': '#ecf0f1', 'marginBottom': 10}),
                html.H3("Phase 4 Demo Validation",
                       style={'textAlign': 'center', 'color': '#95a5a6', 'marginTop': 0}),
            ], style={'backgroundColor': '#1a1a2e', 'padding': '20px', 'marginBottom': 20, 'borderBottom': '2px solid #16213e'}),

            # Auto-refresh interval
            dcc.Interval(
                id='interval-component',
                interval=5*1000,  # Update every 5 seconds
                n_intervals=0
            ),

            # Top row: Account stats
            html.Div([
                html.Div([
                    html.H4("💰 Account Equity", style={'textAlign': 'center', 'color': '#2ecc71'}),
                    html.H2(id='equity-value', style={'textAlign': 'center', 'color': '#2ecc71'}),
                ], className='stat-box', style={'width': '23%', 'display': 'inline-block', 'margin': '1%',
                                                'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                                                'border': '1px solid #374151'}),

                html.Div([
                    html.H4("📊 Net P&L", style={'textAlign': 'center', 'color': '#3498db'}),
                    html.H2(id='pnl-value', style={'textAlign': 'center'}),
                ], className='stat-box', style={'width': '23%', 'display': 'inline-block', 'margin': '1%',
                                                'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                                                'border': '1px solid #374151'}),

                html.Div([
                    html.H4("📈 Open Positions", style={'textAlign': 'center', 'color': '#f39c12'}),
                    html.H2(id='positions-count', style={'textAlign': 'center', 'color': '#f39c12'}),
                ], className='stat-box', style={'width': '23%', 'display': 'inline-block', 'margin': '1%',
                                                'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                                                'border': '1px solid #374151'}),

                html.Div([
                    html.H4("🎯 Daily R Used", style={'textAlign': 'center', 'color': '#9b59b6'}),
                    html.H2(id='daily-r-value', style={'textAlign': 'center', 'color': '#9b59b6'}),
                ], className='stat-box', style={'width': '23%', 'display': 'inline-block', 'margin': '1%',
                                                'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                                                'border': '1px solid #374151'}),
            ], style={'marginBottom': 20}),

            # Connection Status Row
            html.Div([
                html.Div([
                    html.H4("🔌 Connection Status", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                    html.Div(id='connection-status'),
                ], style={'width': '48%', 'display': 'inline-block', 'margin': '1%',
                         'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                         'border': '1px solid #374151'}),

                html.Div([
                    html.H4("📊 System Statistics", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                    html.Div(id='system-stats'),
                ], style={'width': '48%', 'display': 'inline-block', 'margin': '1%',
                         'backgroundColor': '#1f2937', 'padding': 15, 'borderRadius': 5,
                         'border': '1px solid #374151'}),
            ], style={'marginBottom': 20}),

            # Equity Curve
            html.Div([
                html.H3("📈 Equity Curve", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                dcc.Graph(id='equity-chart'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # DCRD Scores
            html.Div([
                html.H3("🎨 DCRD CompositeScores (Live)", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                dcc.Graph(id='dcrd-chart'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # Strategy Tallies
            html.Div([
                html.H3("🎯 Strategy Performance", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                dcc.Graph(id='strategy-chart'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # Signal Analysis Overview (NEW)
            html.Div([
                html.H3("🔍 Signal Analysis Overview (Last 20 Evaluations)", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                html.Div(id='signal-analysis'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # Open Positions Table
            html.Div([
                html.H3("💼 Open Positions", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                html.Div(id='positions-table'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # Recent Trades Table
            html.Div([
                html.H3("📜 Recent Trades (Last 10)", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                html.Div(id='trades-table'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # News Events
            html.Div([
                html.H3("📰 Upcoming News Events (Next 24h)", style={'textAlign': 'center', 'color': '#ecf0f1'}),
                html.Div(id='news-table'),
            ], style={'backgroundColor': '#1f2937', 'padding': 15, 'marginBottom': 20, 'borderRadius': 5,
                     'border': '1px solid #374151'}),

            # Footer
            html.Div([
                html.P("JcampFX Phase 4 Live Trading System | Auto-refresh: 5 seconds",
                      style={'textAlign': 'center', 'color': '#6b7280', 'fontSize': 12}),
            ], style={'marginTop': 30, 'padding': 10}),
        ], style={'fontFamily': 'Arial, sans-serif', 'backgroundColor': '#0f1419', 'padding': 20})

    def _setup_callbacks(self):
        """Setup Dash callbacks for live updates."""

        @self.app.callback(
            [Output('equity-value', 'children'),
             Output('pnl-value', 'children'),
             Output('pnl-value', 'style'),
             Output('positions-count', 'children'),
             Output('daily-r-value', 'children'),
             Output('connection-status', 'children'),
             Output('system-stats', 'children'),
             Output('equity-chart', 'figure'),
             Output('dcrd-chart', 'figure'),
             Output('strategy-chart', 'figure'),
             Output('signal-analysis', 'children'),
             Output('positions-table', 'children'),
             Output('trades-table', 'children'),
             Output('news-table', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            """Update all dashboard components."""
            # Get account state
            equity = self.orchestrator.account_state.equity
            starting_equity = 500.0  # Known starting point
            pnl = equity - starting_equity
            pnl_pct = (pnl / starting_equity) * 100

            open_count = len(self.orchestrator.positions)
            daily_r = self.orchestrator.account_state.daily_r_used

            # Format values
            equity_text = f"${equity:.2f}"
            pnl_text = f"${pnl:+.2f} ({pnl_pct:+.1f}%)"
            pnl_color = '#27ae60' if pnl >= 0 else '#e74c3c'
            positions_text = str(open_count)
            daily_r_text = f"{daily_r:.2f}R"

            # Connection status
            zmq_stats = self.orchestrator.zmq_bridge.get_stats() if self.orchestrator.zmq_bridge else {}
            connection_html = self._format_connection_status(zmq_stats)

            # System stats
            uptime = (datetime.now(timezone.utc) - self.orchestrator.start_time).total_seconds() if self.orchestrator.start_time else 0
            system_html = self._format_system_stats(uptime)

            # Equity chart
            equity_fig = self._create_equity_chart(equity, datetime.now(timezone.utc))

            # DCRD chart
            dcrd_fig = self._create_dcrd_chart()

            # Strategy chart
            strategy_fig = self._create_strategy_chart()

            # Signal analysis overview
            signal_analysis_html = self._create_signal_analysis()

            # Positions table
            positions_html = self._create_positions_table()

            # Trades table
            trades_html = self._create_trades_table()

            # News table
            news_html = self._create_news_table()

            return (equity_text, pnl_text, {'textAlign': 'center', 'color': pnl_color},
                   positions_text, daily_r_text, connection_html, system_html,
                   equity_fig, dcrd_fig, strategy_fig, signal_analysis_html,
                   positions_html, trades_html, news_html)

    def _format_connection_status(self, zmq_stats: dict) -> html.Div:
        """Format connection status display (dark mode)."""
        running = zmq_stats.get('running', False)
        total_ticks = zmq_stats.get('total_ticks', 0)
        last_hb = zmq_stats.get('last_heartbeat')

        status_color = '#2ecc71' if running else '#e74c3c'
        status_text = '✅ Connected' if running else '❌ Disconnected'

        return html.Div([
            html.P(f"Status: {status_text}", style={'color': status_color, 'fontWeight': 'bold'}),
            html.P(f"Total Ticks: {total_ticks:,}", style={'color': '#d1d5db'}),
            html.P(f"Last Heartbeat: {last_hb if last_hb else 'N/A'}", style={'color': '#d1d5db'}),
        ])

    def _format_system_stats(self, uptime: float) -> html.Div:
        """Format system statistics display (dark mode)."""
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        rb_stats = self.orchestrator.range_bar_engine.get_stats() if self.orchestrator.range_bar_engine else {}
        bars_produced = sum(rb_stats.get('bars_produced', {}).values())

        return html.Div([
            html.P(f"Uptime: {hours}h {minutes}m", style={'color': '#d1d5db'}),
            html.P(f"Signals Generated: {self.orchestrator.signals_generated}", style={'color': '#d1d5db'}),
            html.P(f"Signals Approved: {self.orchestrator.signals_approved}", style={'color': '#d1d5db'}),
            html.P(f"Range Bars Created: {bars_produced}", style={'color': '#d1d5db'}),
        ])

    def _create_equity_chart(self, current_equity: float, timestamp: datetime) -> go.Figure:
        """Create equity curve chart."""
        # Store equity point
        self.equity_history.append({'time': timestamp, 'equity': current_equity})

        # Keep last 1000 points
        if len(self.equity_history) > 1000:
            self.equity_history = self.equity_history[-1000:]

        # Create chart
        df = pd.DataFrame(self.equity_history)

        fig = go.Figure()

        if not df.empty:
            fig.add_trace(go.Scatter(
                x=df['time'],
                y=df['equity'],
                mode='lines',
                name='Equity',
                line=dict(color='#3498db', width=2),
                fill='tozeroy',
                fillcolor='rgba(52, 152, 219, 0.1)'
            ))

            # Add starting equity line
            fig.add_hline(y=500.0, line_dash="dash", line_color="gray",
                         annotation_text="Starting Equity ($500)")

        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Equity ($)",
            hovermode='x unified',
            showlegend=True,
            height=400,
            margin=dict(l=50, r=50, t=30, b=50),
            # Dark mode styling
            plot_bgcolor='#111827',
            paper_bgcolor='#111827',
            font=dict(color='#d1d5db'),
            xaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
            yaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
        )

        return fig

    def _create_dcrd_chart(self) -> go.Figure:
        """Create DCRD scores bar chart."""
        pairs = self.orchestrator.pairs
        scores = [self.orchestrator.dcrd_scores.get(p, 0.0) for p in pairs]
        regimes = [self.orchestrator.dcrd_regimes.get(p, 'unknown') for p in pairs]

        # Color by regime
        colors = []
        for regime in regimes:
            if regime == 'trending':
                colors.append('#27ae60')  # Green
            elif regime == 'transitional':
                colors.append('#f39c12')  # Orange
            else:
                colors.append('#e74c3c')  # Red

        fig = go.Figure(data=[
            go.Bar(x=pairs, y=scores, marker_color=colors,
                  text=regimes, textposition='outside')
        ])

        # Add regime boundaries
        fig.add_hline(y=30, line_dash="dash", line_color="red",
                     annotation_text="Range/Transitional (CS=30)")
        fig.add_hline(y=70, line_dash="dash", line_color="green",
                     annotation_text="Transitional/Trending (CS=70)")

        fig.update_layout(
            xaxis_title="Pair",
            yaxis_title="CompositeScore (0-100)",
            yaxis_range=[0, 100],
            height=350,
            margin=dict(l=50, r=50, t=30, b=50),
            # Dark mode styling
            plot_bgcolor='#111827',
            paper_bgcolor='#111827',
            font=dict(color='#d1d5db'),
            xaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
            yaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
        )

        return fig

    def _create_strategy_chart(self) -> go.Figure:
        """Create strategy performance chart."""
        strategy_stats = self.orchestrator.strategy_stats
        strategies = list(strategy_stats.keys())

        # Prepare data for grouped bar chart
        generated = [strategy_stats[s]['generated'] for s in strategies]
        approved = [strategy_stats[s]['approved'] for s in strategies]
        blocked = [strategy_stats[s]['blocked'] for s in strategies]
        active = [strategy_stats[s]['active'] for s in strategies]

        fig = go.Figure()

        # Add traces
        fig.add_trace(go.Bar(
            x=strategies,
            y=generated,
            name='Generated',
            marker_color='#60a5fa',
            text=generated,
            textposition='outside'
        ))

        fig.add_trace(go.Bar(
            x=strategies,
            y=approved,
            name='Approved',
            marker_color='#34d399',
            text=approved,
            textposition='outside'
        ))

        fig.add_trace(go.Bar(
            x=strategies,
            y=blocked,
            name='Blocked',
            marker_color='#f87171',
            text=blocked,
            textposition='outside'
        ))

        fig.add_trace(go.Bar(
            x=strategies,
            y=active,
            name='Active',
            marker_color='#a78bfa',
            text=active,
            textposition='outside'
        ))

        fig.update_layout(
            xaxis_title="Strategy",
            yaxis_title="Count",
            barmode='group',
            height=350,
            margin=dict(l=50, r=50, t=30, b=50),
            # Dark mode styling
            plot_bgcolor='#111827',
            paper_bgcolor='#111827',
            font=dict(color='#d1d5db'),
            xaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
            yaxis=dict(gridcolor='#374151', zerolinecolor='#374151'),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )

        return fig

    def _create_positions_table(self) -> html.Div:
        """Create open positions table."""
        if not self.orchestrator.positions:
            return html.P("No open positions", style={'textAlign': 'center', 'color': '#95a5a6', 'padding': 20})

        # Build table data
        rows = []
        for ticket, pos in self.orchestrator.positions.items():
            # Calculate current R (placeholder - need current price)
            current_r = 0.0  # TODO: Calculate from current price

            rows.append({
                'Ticket': ticket,
                'Pair': pos.pair,
                'Direction': pos.direction,
                'Entry': f"{pos.entry:.5f}",
                'SL': f"{pos.sl:.5f}",
                'Lots': f"{pos.lot_size:.2f}",
                'Strategy': pos.strategy,
                'Entry CS': f"{pos.entry_cs:.1f}",
                'Current R': f"{current_r:.2f}R",
                'Partial': '✅' if pos.partial_exited else '❌',
            })

        df = pd.DataFrame(rows)

        return dash_table.DataTable(
            data=df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in df.columns],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'center',
                'padding': '10px',
                'backgroundColor': '#111827',
                'color': '#d1d5db',
                'border': '1px solid #374151'
            },
            style_header={
                'backgroundColor': '#1e40af',
                'color': 'white',
                'fontWeight': 'bold',
                'border': '1px solid #374151'
            },
            style_data_conditional=[
                {'if': {'filter_query': '{Direction} = "BUY"'}, 'backgroundColor': '#064e3b', 'color': '#6ee7b7'},
                {'if': {'filter_query': '{Direction} = "SELL"'}, 'backgroundColor': '#7f1d1d', 'color': '#fca5a5'},
            ]
        )

    def _create_trades_table(self) -> html.Div:
        """Create recent trades table."""
        if not self.trade_history:
            return html.P("No trades yet", style={'textAlign': 'center', 'color': '#95a5a6', 'padding': 20})

        # Get last 10 trades
        recent = self.trade_history[-10:]

        df = pd.DataFrame(recent)

        return dash_table.DataTable(
            data=df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in df.columns],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'center',
                'padding': '10px',
                'backgroundColor': '#111827',
                'color': '#d1d5db',
                'border': '1px solid #374151'
            },
            style_header={
                'backgroundColor': '#1f2937',
                'color': 'white',
                'fontWeight': 'bold',
                'border': '1px solid #374151'
            },
        )

    def _create_news_table(self) -> html.Div:
        """Create upcoming news events table."""
        # Placeholder - news events would come from NewsLayer
        return html.P("News events will appear here when MT5 calendar is active",
                     style={'textAlign': 'center', 'color': '#95a5a6', 'padding': 20})

    def _create_signal_analysis(self) -> html.Div:
        """Create signal analysis overview table showing recent evaluations."""
        evaluations = self.orchestrator.signal_evaluations[-20:]  # Last 20

        if not evaluations:
            return html.P("Signal evaluations will appear here as Range Bars close",
                         style={'textAlign': 'center', 'color': '#95a5a6', 'padding': 20})

        # Prepare data for table
        table_data = []
        for eval_data in reversed(evaluations):  # Most recent first
            # Format timestamp
            time_str = eval_data['timestamp'].strftime('%H:%M:%S')

            # Color-code result
            if eval_data['result'] == 'APPROVED':
                result_badge = '✅ APPROVED'
                result_color = '#27ae60'
            elif eval_data['result'] == 'BLOCKED':
                result_badge = '❌ BLOCKED'
                result_color = '#e74c3c'
            else:
                result_badge = '⚪ NO_PATTERN'
                result_color = '#95a5a6'

            # Extract blocking reason (short form)
            reason = eval_data['reason']
            if reason:
                # Shorten common reasons
                reason = reason.replace('SESSION_BLOCKED:', 'Session:')
                reason = reason.replace('PRICE_LEVEL_COOLDOWN', 'Cooldown')
                reason = reason.replace('INSUFFICIENT_', 'Need ')
                reason = reason.replace('ADX_TOO_LOW', 'ADX<25')
                if len(reason) > 40:
                    reason = reason[:37] + '...'
            else:
                reason = '—'

            table_data.append({
                'Time': time_str,
                'Pair': eval_data['pair'],
                'Strategy': eval_data['strategy'],
                'Dir': eval_data['direction'],
                'CS': f"{eval_data['cs']:.0f}",
                'Regime': eval_data['regime'].capitalize(),
                'Result': result_badge,
                'Reason': reason,
            })

        # Create DataFrame for table
        df = pd.DataFrame(table_data)

        return dash_table.DataTable(
            data=df.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in df.columns],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'left',
                'padding': '8px',
                'backgroundColor': '#111827',
                'color': '#d1d5db',
                'border': '1px solid #374151',
                'fontSize': '12px',
            },
            style_header={
                'backgroundColor': '#1f2937',
                'color': 'white',
                'fontWeight': 'bold',
                'border': '1px solid #374151'
            },
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Result} contains "APPROVED"'},
                    'backgroundColor': '#1a3a1a',
                },
                {
                    'if': {'filter_query': '{Result} contains "BLOCKED"'},
                    'backgroundColor': '#3a1a1a',
                },
            ],
        )

    def add_trade(self, trade_data: dict):
        """Add a completed trade to history."""
        self.trade_history.append(trade_data)

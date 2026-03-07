"""Quick test of Cycle 4 period with 4-pair baseline vs 5-pair SwingRider."""
from backtester.engine import BacktestEngine
from datetime import datetime
import pandas as pd

# Test Cycle 4 period (Dec 2025 - Jan 2026)
start = pd.Timestamp("2025-12-01", tz="UTC")
end = pd.Timestamp("2026-01-31", tz="UTC")

print("=" * 60)
print("Cycle 4 Period Analysis (Dec 2025 - Jan 2026)")
print("=" * 60)

# 4-pair baseline (Phase 3.6 validated system)
print("\n1. Running 4-pair baseline (no GBPJPY)...")
engine_4pair = BacktestEngine(["EURUSD", "USDJPY", "AUDJPY", "USDCHF"])
results_4pair = engine_4pair.run(start=start, end=end, initial_equity=500.0)

print(f"   Trades: {len(results_4pair.all_trades)}")
print(f"   Net PnL: ${results_4pair.net_profit_usd():.2f}")
print(f"   Win Rate: {results_4pair.win_rate():.1f}%")
print(f"   Total R: {results_4pair.total_r():.2f}R")

# 5-pair SwingRider system
print("\n2. Running 5-pair SwingRider system (with GBPJPY)...")
engine_5pair = BacktestEngine(["EURUSD", "USDJPY", "AUDJPY", "USDCHF", "GBPJPY"])
results_5pair = engine_5pair.run(start=start, end=end, initial_equity=500.0)

print(f"   Trades: {len(results_5pair.all_trades)}")
print(f"   Net PnL: ${results_5pair.net_profit_usd():.2f}")
print(f"   Win Rate: {results_5pair.win_rate():.1f}%")
print(f"   Total R: {results_5pair.total_r():.2f}R")

# Per-pair breakdown
print("\n3. Per-pair breakdown (5-pair system):")
pair_stats = {}
for trade in results_5pair.all_trades:
    if trade.pair not in pair_stats:
        pair_stats[trade.pair] = {"count": 0, "pnl": 0.0, "wins": 0}
    pair_stats[trade.pair]["count"] += 1
    pair_stats[trade.pair]["pnl"] += trade.pnl_usd if trade.pnl_usd else 0.0
    if trade.exit_status and "SL" not in trade.exit_status:
        pair_stats[trade.pair]["wins"] += 1

for pair, stats in sorted(pair_stats.items()):
    wr = (stats["wins"] / stats["count"] * 100) if stats["count"] > 0 else 0.0
    print(f"   {pair}: {stats['count']} trades, ${stats['pnl']:.2f}, {wr:.1f}% WR")

print("\n" + "=" * 60)
print("Conclusion:")
diff = results_5pair.net_profit_usd() - results_4pair.net_profit_usd()
print(f"Adding GBPJPY changed PnL by ${diff:+.2f}")
if diff < 0:
    print(f"❌ GBPJPY made Cycle 4 WORSE by ${abs(diff):.2f}")
else:
    print(f"✅ GBPJPY improved Cycle 4 by ${diff:.2f}")
print("=" * 60)

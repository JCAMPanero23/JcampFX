using System;
using System.Collections.Generic;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace JcampFX
{
    /// <summary>
    /// JcampFX Brain cBot - Phase 4 ZMQ Bridge to Python
    ///
    /// Translates cTrader to MT5-equivalent functionality:
    /// - Tick streaming (all 4 pairs)
    /// - Order execution (entry/exit/modify)
    /// - Execution reports back to Python
    ///
    /// Architecture:
    /// - cTrader cBot (C#) ↔ ZMQ Bridge ↔ Python Brain (unchanged)
    /// - Port 5555 PUSH: Send ticks/reports to Python
    /// - Port 5556 SUB: Receive signals from Python
    /// - Port 5557 PUSH: News events (Phase 5+ placeholder)
    /// </summary>
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class JcampFX_Brain : Robot
    {
        // ============================================================
        // Parameters
        // ============================================================

        [Parameter("Trading Pairs", DefaultValue = "EURUSD,USDJPY,AUDJPY,USDCHF")]
        public string TradingPairs { get; set; }

        [Parameter("Broker Suffix", DefaultValue = "")]
        public string BrokerSuffix { get; set; }

        [Parameter("Heartbeat Interval (sec)", DefaultValue = 30, MinValue = 10, MaxValue = 300)]
        public int HeartbeatSeconds { get; set; }

        [Parameter("Enable Trading", DefaultValue = true)]
        public bool EnableTrading { get; set; }

        [Parameter("Magic Number", DefaultValue = 777001)]
        public int MagicNumber { get; set; }

        [Parameter("Slippage (pips)", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 10)]
        public double SlippagePips { get; set; }

        // ============================================================
        // Internal State
        // ============================================================

        private ZMQBridge _zmqBridge;
        private List<string> _pairs;
        private Dictionary<string, Symbol> _symbols;  // Map canonical name → Symbol object
        private Timer _heartbeatTimer;
        private bool _initialized;

        // ============================================================
        // Initialization
        // ============================================================

        protected override void OnStart()
        {
            Print("==========================================================");
            Print("JcampFX Brain cBot - Phase 4 (cTrader → Python ZMQ Bridge)");
            Print("==========================================================");

            // Parse trading pairs
            _pairs = TradingPairs.Split(',')
                .Select(p => p.Trim().ToUpper())
                .Where(p => !string.IsNullOrEmpty(p))
                .ToList();

            Print($"[INFO] Monitoring {_pairs.Count} pairs: {string.Join(", ", _pairs)}");

            // Load symbols
            _symbols = new Dictionary<string, Symbol>();
            foreach (var canonicalName in _pairs)
            {
                string brokerSymbol = GetBrokerSymbol(canonicalName);

                try
                {
                    var symbol = Symbols.GetSymbol(brokerSymbol);
                    _symbols[canonicalName] = symbol;
                    Print($"[INFO] Loaded symbol: {canonicalName} → {brokerSymbol} (Digits={symbol.Digits}, PipSize={symbol.PipSize})");
                }
                catch (Exception ex)
                {
                    Print($"[ERROR] Failed to load symbol {brokerSymbol}: {ex.Message}");
                }
            }

            if (_symbols.Count == 0)
            {
                Print("[ERROR] No valid symbols loaded - cBot cannot start");
                Stop();
                return;
            }

            // Initialize ZMQ bridge
            try
            {
                _zmqBridge = new ZMQBridge(this, OnCommandReceived);
                _zmqBridge.Start();
            }
            catch (Exception ex)
            {
                Print($"[ERROR] Failed to initialize ZMQ bridge: {ex.Message}");
                Stop();
                return;
            }

            // Setup heartbeat timer
            _heartbeatTimer = new Timer(TimeSpan.FromSeconds(HeartbeatSeconds), SendHeartbeat);

            _initialized = true;
            Print("[SUCCESS] JcampFX Brain cBot initialized");
            Print("==========================================================");
        }

        protected override void OnStop()
        {
            Print("==========================================================");
            Print("[INFO] JcampFX Brain cBot shutting down...");

            _heartbeatTimer?.Stop();
            _heartbeatTimer?.Dispose();

            if (_zmqBridge != null)
            {
                Print($"[STATS] {_zmqBridge.GetStats()}");
                _zmqBridge.Stop();
                _zmqBridge.Dispose();
            }

            Print("[INFO] Shutdown complete");
            Print("==========================================================");
        }

        // ============================================================
        // Tick Event (Main Thread)
        // ============================================================

        protected override void OnTick()
        {
            if (!_initialized || _zmqBridge == null)
                return;

            // Send ticks for ALL monitored pairs (not just chart symbol)
            foreach (var kvp in _symbols)
            {
                string canonicalName = kvp.Key;
                Symbol symbol = kvp.Value;

                // Get current tick data
                var tick = symbol.Tick;

                // Send to Python with BROKER symbol (Python will strip suffix)
                string brokerSymbol = GetBrokerSymbol(canonicalName);
                _zmqBridge.SendTick(
                    symbol: brokerSymbol,
                    time: tick.Time,
                    bid: tick.Bid,
                    ask: tick.Ask,
                    last: (tick.Bid + tick.Ask) / 2.0,  // cTrader has no "last" price
                    volume: 0  // cTrader tick doesn't expose volume
                );
            }
        }

        // ============================================================
        // Heartbeat Timer
        // ============================================================

        private void SendHeartbeat()
        {
            if (_zmqBridge != null)
            {
                _zmqBridge.SendHeartbeat();
            }
        }

        // ============================================================
        // Command Processing (Python → cTrader)
        // ============================================================

        /// <summary>
        /// Callback for commands received from Python Brain via ZMQ.
        /// Invoked on main thread (thread-safe via BeginInvokeOnMainThread).
        /// </summary>
        private void OnCommandReceived(CommandMessage command)
        {
            if (!EnableTrading)
            {
                Print("[WARNING] Trading disabled - ignoring command");
                return;
            }

            Print($"[COMMAND] Processing: {command.Type}");

            try
            {
                switch (command.Type)
                {
                    case "entry":
                        ExecuteEntry(command);
                        break;

                    case "exit":
                        ExecuteExit(command);
                        break;

                    case "modify":
                        ExecuteModify(command);
                        break;

                    default:
                        Print($"[ERROR] Unknown command type: {command.Type}");
                        break;
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] Command processing failed: {ex.Message}");
                Print($"[ERROR] Stack trace: {ex.StackTrace}");
            }
        }

        /// <summary>
        /// Execute entry signal: open new position.
        /// </summary>
        private void ExecuteEntry(CommandMessage cmd)
        {
            string canonicalSymbol = cmd.Symbol;
            string direction = cmd.Direction;
            double? slPrice = cmd.StopLoss;
            double? tpPrice = cmd.TakeProfit;
            double lots = cmd.Lots ?? 0.01;

            // Validate
            if (string.IsNullOrEmpty(canonicalSymbol) || string.IsNullOrEmpty(direction))
            {
                Print($"[ERROR] Invalid entry signal: missing symbol or direction");
                return;
            }

            // Get symbol object
            if (!_symbols.TryGetValue(canonicalSymbol, out Symbol symbol))
            {
                Print($"[ERROR] Symbol not found: {canonicalSymbol}");
                return;
            }

            // Determine trade type
            TradeType tradeType = direction.ToUpper() == "BUY" ? TradeType.Buy : TradeType.Sell;

            // Convert lots to volume (1 lot = 100,000 units)
            double volumeInUnits = lots * 100000;

            // Normalize volume to symbol's volume step
            volumeInUnits = symbol.NormalizeVolumeInUnits(volumeInUnits, RoundingMode.ToNearest);

            // Validate volume
            if (volumeInUnits < symbol.VolumeInUnitsMin)
            {
                Print($"[ERROR] Volume {volumeInUnits} below minimum {symbol.VolumeInUnitsMin}");
                volumeInUnits = symbol.VolumeInUnitsMin;
            }
            if (volumeInUnits > symbol.VolumeInUnitsMax)
            {
                Print($"[ERROR] Volume {volumeInUnits} above maximum {symbol.VolumeInUnitsMax}");
                volumeInUnits = symbol.VolumeInUnitsMax;
            }

            // Convert slippage to price distance
            double slippagePrice = SlippagePips * symbol.PipSize;

            // Execute order
            Print($"[ENTRY] Opening {tradeType} {canonicalSymbol} {lots} lots (SL={slPrice:F5}, TP={tpPrice:F5})");

            var result = ExecuteMarketOrder(
                tradeType: tradeType,
                symbolName: symbol.Name,
                volumeInUnits: volumeInUnits,
                label: "JcampFX_Brain",
                stopLossPips: null,  // Set price-based SL/TP below
                takeProfitPips: null,
                slippagePrice,
                comment: $"Magic:{MagicNumber}"
            );

            // Send execution report
            if (result.IsSuccessful)
            {
                var position = result.Position;
                Print($"[SUCCESS] Position opened: Ticket #{position.Id} @ {position.EntryPrice:F5}");

                // Set SL/TP if provided (cTrader API requires separate call)
                if (slPrice.HasValue || tpPrice.HasValue)
                {
                    ModifyPosition(position, slPrice, tpPrice);
                }

                _zmqBridge.SendExecutionReport(
                    success: true,
                    symbol: GetBrokerSymbol(canonicalSymbol),
                    direction: direction,
                    ticket: position.Id,
                    price: position.EntryPrice,
                    retcode: 10009,  // MT5-equivalent: TRADE_RETCODE_DONE
                    message: "Success"
                );
            }
            else
            {
                Print($"[ERROR] Order failed: {result.Error}");
                _zmqBridge.SendExecutionReport(
                    success: false,
                    symbol: GetBrokerSymbol(canonicalSymbol),
                    direction: direction,
                    ticket: 0,
                    price: 0.0,
                    retcode: 10013,  // MT5-equivalent: TRADE_RETCODE_ERROR
                    message: result.Error.ToString()
                );
            }
        }

        /// <summary>
        /// Execute exit signal: close existing position.
        /// </summary>
        private void ExecuteExit(CommandMessage cmd)
        {
            long ticket = cmd.Ticket ?? 0;

            if (ticket <= 0)
            {
                Print($"[ERROR] Invalid exit signal: missing or invalid ticket");
                return;
            }

            // Find position by ID
            var position = Positions.FirstOrDefault(p => p.Id == ticket);

            if (position == null)
            {
                Print($"[ERROR] Position not found: Ticket #{ticket}");
                return;
            }

            Print($"[EXIT] Closing position: Ticket #{ticket} {position.SymbolName} {position.TradeType} {position.VolumeInUnits} units");

            // Close position
            var result = ClosePosition(position);

            if (result.IsSuccessful)
            {
                Print($"[SUCCESS] Position closed: Ticket #{ticket} @ {result.Position.EntryPrice:F5}");
            }
            else
            {
                Print($"[ERROR] Close failed: {result.Error}");
            }
        }

        /// <summary>
        /// Execute modify signal: update SL/TP on existing position.
        /// </summary>
        private void ExecuteModify(CommandMessage cmd)
        {
            long ticket = cmd.Ticket ?? 0;
            double? newSL = cmd.StopLoss;
            double? newTP = cmd.TakeProfit;

            if (ticket <= 0)
            {
                Print($"[ERROR] Invalid modify signal: missing or invalid ticket");
                return;
            }

            // Find position by ID
            var position = Positions.FirstOrDefault(p => p.Id == ticket);

            if (position == null)
            {
                Print($"[ERROR] Position not found: Ticket #{ticket}");
                return;
            }

            Print($"[MODIFY] Updating position: Ticket #{ticket} SL={newSL:F5} TP={newTP:F5}");

            ModifyPosition(position, newSL, newTP);
        }

        // ============================================================
        // Helper Methods
        // ============================================================

        /// <summary>
        /// Get broker symbol name from canonical name.
        /// Adds broker suffix if needed (e.g., EURUSD → EURUSD.ct).
        /// </summary>
        private string GetBrokerSymbol(string canonicalName)
        {
            if (string.IsNullOrEmpty(BrokerSuffix))
                return canonicalName;

            return canonicalName + BrokerSuffix;
        }

        /// <summary>
        /// Modify position SL/TP.
        /// </summary>
        private void ModifyPosition(Position position, double? stopLoss, double? takeProfit)
        {
            try
            {
                var result = ModifyPosition(position, stopLoss, takeProfit);

                if (result.IsSuccessful)
                {
                    Print($"[SUCCESS] Position modified: Ticket #{position.Id} SL={stopLoss:F5} TP={takeProfit:F5}");
                }
                else
                {
                    Print($"[ERROR] Modify failed: {result.Error}");
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] ModifyPosition exception: {ex.Message}");
            }
        }
    }
}

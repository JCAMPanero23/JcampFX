using NetMQ.Sockets;
using NetMQ;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using System.Text.Json;
using System.Text;
using System.Threading.Tasks;
using System.Threading;
using System;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;
using cAlgo.API;

namespace JcampFX
{
    // ============================================================
    // From: MessageTypes.cs
    // ============================================================
        /// <summary>
        /// Message DTOs for ZMQ communication between cTrader cBot and Python Brain.
        /// All messages use JSON serialization with System.Text.Json.
        /// </summary>

        // ============================================================
        // Outbound Messages (cTrader → Python)
        // ============================================================

        /// <summary>
        /// Tick data message sent on every OnTick event.
        /// </summary>
        public class TickMessage
        {
            [JsonPropertyName("type")]
            public string Type { get; set; } = "tick";

            [JsonPropertyName("symbol")]
            public string Symbol { get; set; }

            [JsonPropertyName("time")]
            public long Time { get; set; }  // Unix timestamp (seconds)

            [JsonPropertyName("bid")]
            public double Bid { get; set; }

            [JsonPropertyName("ask")]
            public double Ask { get; set; }

            [JsonPropertyName("last")]
            public double Last { get; set; }

            [JsonPropertyName("volume")]
            public long Volume { get; set; }

            [JsonPropertyName("flags")]
            public int Flags { get; set; }  // Reserved for future use
        }

        /// <summary>
        /// Heartbeat message sent every 30 seconds to verify connection health.
        /// </summary>
        public class HeartbeatMessage
        {
            [JsonPropertyName("type")]
            public string Type { get; set; } = "heartbeat";

            [JsonPropertyName("time")]
            public long Time { get; set; }  // Unix timestamp (seconds)
        }

        /// <summary>
        /// Execution report sent after order execution (entry/exit/modify).
        /// </summary>
        public class ExecutionReportMessage
        {
            [JsonPropertyName("type")]
            public string Type { get; set; } = "execution_report";

            [JsonPropertyName("success")]
            public bool Success { get; set; }

            [JsonPropertyName("symbol")]
            public string Symbol { get; set; }

            [JsonPropertyName("direction")]
            public string Direction { get; set; }  // "BUY" or "SELL"

            [JsonPropertyName("ticket")]
            public long Ticket { get; set; }  // Position ID

            [JsonPropertyName("price")]
            public double Price { get; set; }

            [JsonPropertyName("retcode")]
            public int Retcode { get; set; }  // cTrader result code

            [JsonPropertyName("time")]
            public long Time { get; set; }  // Unix timestamp (seconds)

            [JsonPropertyName("message")]
            public string Message { get; set; }  // Error message (if failed)
        }

        /// <summary>
        /// News event message (placeholder for Phase 5+).
        /// cTrader has no native calendar API - will integrate external API later.
        /// </summary>
        public class NewsEventMessage
        {
            [JsonPropertyName("type")]
            public string Type { get; set; } = "news_event";

            [JsonPropertyName("currency")]
            public string Currency { get; set; }

            [JsonPropertyName("event_name")]
            public string EventName { get; set; }

            [JsonPropertyName("time")]
            public long Time { get; set; }

            [JsonPropertyName("importance")]
            public int Importance { get; set; }  // 1=Low, 2=Medium, 3=High
        }

        // ============================================================
        // Inbound Messages (Python → cTrader)
        // ============================================================

        /// <summary>
        /// Entry signal from Python Brain to open a new position.
        /// </summary>
        public class EntrySignal
        {
            [JsonPropertyName("type")]
            public string Type { get; set; }  // Should be "entry"

            [JsonPropertyName("symbol")]
            public string Symbol { get; set; }  // Canonical name (e.g., "EURUSD")

            [JsonPropertyName("direction")]
            public string Direction { get; set; }  // "BUY" or "SELL"

            [JsonPropertyName("sl")]
            public double? StopLoss { get; set; }  // Nullable (0.0 = no SL)

            [JsonPropertyName("tp")]
            public double? TakeProfit { get; set; }  // Nullable (0.0 = no TP)

            [JsonPropertyName("lots")]
            public double Lots { get; set; }  // Lot size (0.01 = 1 microlot)
        }

        /// <summary>
        /// Exit signal from Python Brain to close an existing position.
        /// </summary>
        public class ExitSignal
        {
            [JsonPropertyName("type")]
            public string Type { get; set; }  // Should be "exit"

            [JsonPropertyName("ticket")]
            public long Ticket { get; set; }  // Position ID to close
        }

        /// <summary>
        /// Modify signal from Python Brain to update SL/TP on existing position.
        /// </summary>
        public class ModifySignal
        {
            [JsonPropertyName("type")]
            public string Type { get; set; }  // Should be "modify"

            [JsonPropertyName("ticket")]
            public long Ticket { get; set; }  // Position ID to modify

            [JsonPropertyName("sl")]
            public double? StopLoss { get; set; }  // New SL (nullable)

            [JsonPropertyName("tp")]
            public double? TakeProfit { get; set; }  // New TP (nullable)
        }

        /// <summary>
        /// Generic command wrapper for deserialization.
        /// Used to determine command type before casting to specific signal type.
        /// </summary>
        public class CommandMessage
        {
            [JsonPropertyName("type")]
            public string Type { get; set; }

            [JsonPropertyName("symbol")]
            public string Symbol { get; set; }

            [JsonPropertyName("direction")]
            public string Direction { get; set; }

            [JsonPropertyName("sl")]
            public double? StopLoss { get; set; }

            [JsonPropertyName("tp")]
            public double? TakeProfit { get; set; }

            [JsonPropertyName("lots")]
            public double? Lots { get; set; }

            [JsonPropertyName("ticket")]
            public long? Ticket { get; set; }
        }

        // ============================================================
        // Helper Extensions
        // ============================================================

        public static class DateTimeExtensions
        {
            private static readonly DateTime UnixEpoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);

            /// <summary>
            /// Convert DateTime to Unix timestamp (seconds since 1970-01-01).
            /// </summary>
            public static long ToUnixTimestamp(this DateTime dateTime)
            {
                return (long)(dateTime.ToUniversalTime() - UnixEpoch).TotalSeconds;
            }

            /// <summary>
            /// Convert Unix timestamp to DateTime (UTC).
            /// </summary>
            public static DateTime FromUnixTimestamp(long timestamp)
            {
                return UnixEpoch.AddSeconds(timestamp);
            }
        }

    // ============================================================
    // From: ZMQBridge.cs
    // ============================================================
        /// <summary>
        /// ZMQ bridge for bidirectional communication between cTrader cBot and Python Brain.
        ///
        /// Architecture:
        /// - Port 5555 (PUSH): Send tick data, execution reports, heartbeats to Python
        /// - Port 5556 (SUB): Receive trading signals (entry/exit/modify) from Python
        /// - Port 5557 (PUSH): Reserved for news events (Phase 5+)
        ///
        /// Threading Model:
        /// - Main thread: cBot OnTick event (sends tick data)
        /// - Background thread: ZMQ SUB socket listener (receives signals)
        /// </summary>
        public class ZMQBridge : IDisposable
        {
            private readonly Robot _robot;  // cBot instance for logging

            // ZMQ sockets
            private PushSocket _signalSocket;   // Port 5555 (send to Python)
            private SubscriberSocket _commandSocket;   // Port 5556 (receive from Python)
            private PushSocket _newsSocket;     // Port 5557 (news events - Phase 5+)

            // State
            private bool _isRunning;
            private Task _receiverTask;
            private CancellationTokenSource _cancellationTokenSource;
            private DateTime _lastHeartbeat;

            // Statistics
            private int _ticksSent;
            private int _commandsReceived;
            private int _executionReportsSent;

            // Callbacks
            private Action<CommandMessage> _onCommandReceived;

            /// <summary>
            /// Initialize ZMQ bridge.
            /// </summary>
            /// <param name="robot">cBot instance (for logging)</param>
            /// <param name="onCommandReceived">Callback for incoming commands from Python</param>
            public ZMQBridge(Robot robot, Action<CommandMessage> onCommandReceived)
            {
                _robot = robot;
                _onCommandReceived = onCommandReceived;
                _lastHeartbeat = DateTime.UtcNow;
            }

            /// <summary>
            /// Start ZMQ bridge and connect to Python Brain.
            /// </summary>
            public void Start()
            {
                if (_isRunning)
                {
                    _robot.Print("[ZMQ] Bridge already running");
                    return;
                }

                _robot.Print("========================================");
                _robot.Print("[ZMQ] Starting bridge...");

                try
                {
                    // Create PUSH socket (send to Python on port 5555)
                    _signalSocket = new PushSocket();
                    _signalSocket.Connect("tcp://localhost:5555");
                    _robot.Print("[ZMQ] Signal socket connected to tcp://localhost:5555 (PUSH)");

                    // Create SUB socket (receive from Python on port 5556)
                    _commandSocket = new SubscriberSocket();
                    _commandSocket.Connect("tcp://localhost:5556");
                    _commandSocket.SubscribeToAnyTopic();  // Subscribe to all messages
                    _robot.Print("[ZMQ] Command socket connected to tcp://localhost:5556 (SUB)");

                    // Create NEWS socket (Phase 5+ - placeholder)
                    _newsSocket = new PushSocket();
                    _newsSocket.Connect("tcp://localhost:5557");
                    _robot.Print("[ZMQ] News socket connected to tcp://localhost:5557 (PUSH)");

                    // Start background receiver thread
                    _cancellationTokenSource = new CancellationTokenSource();
                    _receiverTask = Task.Run(() => ReceiveLoop(_cancellationTokenSource.Token));

                    _isRunning = true;
                    _robot.Print("[ZMQ] Bridge started successfully");
                    _robot.Print("========================================");
                }
                catch (Exception ex)
                {
                    _robot.Print($"[ZMQ] ERROR: Failed to start bridge: {ex.Message}");
                    _robot.Print($"[ZMQ] Stack trace: {ex.StackTrace}");
                    Cleanup();
                }
            }

            /// <summary>
            /// Stop ZMQ bridge and close sockets.
            /// </summary>
            public void Stop()
            {
                if (!_isRunning)
                    return;

                _robot.Print("[ZMQ] Stopping bridge...");
                _isRunning = false;

                // Cancel receiver thread
                _cancellationTokenSource?.Cancel();

                // Wait for thread to finish (max 2 seconds)
                if (_receiverTask != null)
                {
                    _receiverTask.Wait(TimeSpan.FromSeconds(2));
                }

                Cleanup();
                _robot.Print("[ZMQ] Bridge stopped");
            }

            /// <summary>
            /// Cleanup ZMQ sockets and resources.
            /// </summary>
            private void Cleanup()
            {
                try
                {
                    _signalSocket?.Close();
                    _signalSocket?.Dispose();
                    _signalSocket = null;

                    _commandSocket?.Close();
                    _commandSocket?.Dispose();
                    _commandSocket = null;

                    _newsSocket?.Close();
                    _newsSocket?.Dispose();
                    _newsSocket = null;

                    _cancellationTokenSource?.Dispose();
                    _cancellationTokenSource = null;

                    NetMQConfig.Cleanup(false);
                }
                catch (Exception ex)
                {
                    _robot.Print($"[ZMQ] Cleanup error: {ex.Message}");
                }
            }

            /// <summary>
            /// Send tick data to Python Brain.
            /// Called from cBot OnTick event (main thread).
            /// </summary>
            public void SendTick(string symbol, DateTime time, double bid, double ask, double last, long volume)
            {
                if (!_isRunning || _signalSocket == null)
                    return;

                try
                {
                    var tick = new TickMessage
                    {
                        Symbol = symbol,
                        Time = time.ToUnixTimestamp(),
                        Bid = bid,
                        Ask = ask,
                        Last = last,
                        Volume = volume,
                        Flags = 0
                    };

                    string json = JsonSerializer.Serialize(tick);
                    _signalSocket.SendFrame(json);
                    _ticksSent++;
                }
                catch (Exception ex)
                {
                    _robot.Print($"[ZMQ] ERROR sending tick: {ex.Message}");
                }
            }

            /// <summary>
            /// Send execution report to Python Brain.
            /// Called after order execution (entry/exit/modify).
            /// </summary>
            public void SendExecutionReport(bool success, string symbol, string direction, long ticket, double price, int retcode, string message = "")
            {
                if (!_isRunning || _signalSocket == null)
                    return;

                try
                {
                    var report = new ExecutionReportMessage
                    {
                        Success = success,
                        Symbol = symbol,
                        Direction = direction,
                        Ticket = ticket,
                        Price = price,
                        Retcode = retcode,
                        Time = DateTime.UtcNow.ToUnixTimestamp(),
                        Message = message
                    };

                    string json = JsonSerializer.Serialize(report);
                    _signalSocket.SendFrame(json);
                    _executionReportsSent++;

                    if (success)
                        _robot.Print($"[ZMQ] Execution report sent: SUCCESS - {symbol} {direction} Ticket #{ticket} @ {price:F5}");
                    else
                        _robot.Print($"[ZMQ] Execution report sent: FAILED - {symbol} {direction} (retcode={retcode}, {message})");
                }
                catch (Exception ex)
                {
                    _robot.Print($"[ZMQ] ERROR sending execution report: {ex.Message}");
                }
            }

            /// <summary>
            /// Send heartbeat to Python Brain.
            /// Called every 30 seconds by cBot timer.
            /// </summary>
            public void SendHeartbeat()
            {
                if (!_isRunning || _signalSocket == null)
                    return;

                try
                {
                    var heartbeat = new HeartbeatMessage
                    {
                        Time = DateTime.UtcNow.ToUnixTimestamp()
                    };

                    string json = JsonSerializer.Serialize(heartbeat);
                    _signalSocket.SendFrame(json);
                    _lastHeartbeat = DateTime.UtcNow;
                }
                catch (Exception ex)
                {
                    _robot.Print($"[ZMQ] ERROR sending heartbeat: {ex.Message}");
                }
            }

            /// <summary>
            /// Background thread: continuously receive commands from Python Brain.
            /// Runs in separate thread to avoid blocking cBot main thread.
            /// </summary>
            private void ReceiveLoop(CancellationToken cancellationToken)
            {
                _robot.Print("[ZMQ] Receiver thread started");

                while (!cancellationToken.IsCancellationRequested && _isRunning)
                {
                    try
                    {
                        // Non-blocking receive with 100ms timeout
                        if (_commandSocket.TryReceiveFrameString(TimeSpan.FromMilliseconds(100), out string message))
                        {
                            _commandsReceived++;
                            _robot.Print($"[ZMQ] Command received: {message}");

                            // Parse JSON
                            var command = JsonSerializer.Deserialize<CommandMessage>(message);

                            // Invoke callback on main thread (thread-safe)
                            _robot.BeginInvokeOnMainThread(() =>
                            {
                                try
                                {
                                    _onCommandReceived?.Invoke(command);
                                }
                                catch (Exception ex)
                                {
                                    _robot.Print($"[ZMQ] ERROR in command callback: {ex.Message}");
                                }
                            });
                        }
                    }
                    catch (Exception ex)
                    {
                        if (_isRunning)  // Only log if not intentionally stopped
                        {
                            _robot.Print($"[ZMQ] Receiver error: {ex.Message}");
                        }
                    }
                }

                _robot.Print("[ZMQ] Receiver thread stopped");
            }

            /// <summary>
            /// Get bridge statistics.
            /// </summary>
            public string GetStats()
            {
                var uptime = DateTime.UtcNow - _lastHeartbeat;
                return $"Ticks: {_ticksSent}, Commands: {_commandsReceived}, Reports: {_executionReportsSent}, Uptime: {uptime.TotalSeconds:F0}s";
            }

            /// <summary>
            /// IDisposable implementation.
            /// </summary>
            public void Dispose()
            {
                Stop();
            }
        }

    // ============================================================
    // From: JcampFX_Brain.cs
    // ============================================================
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
            private cAlgo.API.Timer _heartbeatTimer;
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
using System;
using System.Collections.Generic;
using System.Text.Json;
using cAlgo.API;
using NetMQ;
using NetMQ.Sockets;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class JcampFX_Brain : Robot
    {
        [Parameter("Trading Pairs", DefaultValue = "EURUSD,USDJPY,AUDJPY,USDCHF")]
        public string TradingPairs { get; set; }

        [Parameter("Broker Suffix", DefaultValue = "")]
        public string BrokerSuffix { get; set; }

        [Parameter("Enable Trading", DefaultValue = false)]
        public bool EnableTrading { get; set; }

        private PushSocket _sendSocket;
        private SubscriberSocket _receiveSocket;
        private List<string> _pairs;
        private int _tickCount;

        protected override void OnStart()
        {
            Print("==========================================================");
            Print("JcampFX Brain cBot - Simplified Version");
            Print("==========================================================");

            // Parse pairs
            _pairs = new List<string>();
            foreach (var pair in TradingPairs.Split(','))
            {
                var trimmed = pair.Trim().ToUpper();
                if (!string.IsNullOrEmpty(trimmed))
                    _pairs.Add(trimmed);
            }

            Print($"[INFO] Monitoring {_pairs.Count} pairs");

            // Initialize ZMQ
            try
            {
                _sendSocket = new PushSocket();
                _sendSocket.Connect("tcp://localhost:5555");
                Print("[ZMQ] Send socket connected to port 5555");

                _receiveSocket = new SubscriberSocket();
                _receiveSocket.Connect("tcp://localhost:5556");
                _receiveSocket.SubscribeToAnyTopic();
                Print("[ZMQ] Receive socket connected to port 5556");

                Print("[SUCCESS] ZMQ Bridge initialized");
            }
            catch (Exception ex)
            {
                Print($"[ERROR] ZMQ initialization failed: {ex.Message}");
            }

            Print("==========================================================");
        }

        protected override void OnTick()
        {
            if (_sendSocket == null)
                return;

            _tickCount++;

            // Send tick every 100 ticks to avoid flooding
            if (_tickCount % 100 != 0)
                return;

            try
            {
                // Get current symbol info
                string symbol = SymbolName + BrokerSuffix;
                var bid = Symbol.Bid;
                var ask = Symbol.Ask;
                var time = Server.Time;

                // Create simple JSON message
                var message = string.Format(
                    "{{\"type\":\"tick\",\"symbol\":\"{0}\",\"time\":{1},\"bid\":{2},\"ask\":{3},\"last\":{4},\"volume\":0,\"flags\":0}}",
                    symbol,
                    new DateTimeOffset(time).ToUnixTimeSeconds(),
                    bid,
                    ask,
                    (bid + ask) / 2
                );

                // Send via ZMQ
                _sendSocket.SendFrame(message);

                // Print status every 1000 ticks
                if (_tickCount % 1000 == 0)
                {
                    Print($"[TICK] Sent {_tickCount} ticks - {symbol} Bid={bid:F5} Ask={ask:F5}");
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] OnTick failed: {ex.Message}");
            }

            // Check for incoming commands (non-blocking)
            try
            {
                if (_receiveSocket != null && _receiveSocket.TryReceiveFrameString(TimeSpan.Zero, out string command))
                {
                    Print($"[COMMAND] Received: {command}");
                    ProcessCommand(command);
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] Receive failed: {ex.Message}");
            }
        }

        private void ProcessCommand(string json)
        {
            if (!EnableTrading)
            {
                Print("[WARNING] Trading disabled - ignoring command");
                return;
            }

            try
            {
                // Simple JSON parsing
                var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;
                var type = root.GetProperty("type").GetString();

                Print($"[COMMAND] Type: {type}");

                if (type == "entry")
                {
                    var symbol = root.GetProperty("symbol").GetString();
                    var direction = root.GetProperty("direction").GetString();
                    var lots = root.GetProperty("lots").GetDouble();

                    Print($"[ENTRY] {symbol} {direction} {lots} lots - NOT IMPLEMENTED YET");
                    // TODO: Implement order execution
                }
                else if (type == "exit")
                {
                    var ticket = root.GetProperty("ticket").GetInt64();
                    Print($"[EXIT] Ticket {ticket} - NOT IMPLEMENTED YET");
                    // TODO: Implement position closing
                }
                else if (type == "modify")
                {
                    var ticket = root.GetProperty("ticket").GetInt64();
                    Print($"[MODIFY] Ticket {ticket} - NOT IMPLEMENTED YET");
                    // TODO: Implement SL/TP modification
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] Command processing failed: {ex.Message}");
            }
        }

        protected override void OnStop()
        {
            Print("==========================================================");
            Print($"[INFO] Shutting down - Total ticks sent: {_tickCount}");

            try
            {
                if (_sendSocket != null)
                {
                    _sendSocket.Close();
                    _sendSocket.Dispose();
                }

                if (_receiveSocket != null)
                {
                    _receiveSocket.Close();
                    _receiveSocket.Dispose();
                }

                NetMQConfig.Cleanup(false);
                Print("[INFO] ZMQ cleanup complete");
            }
            catch (Exception ex)
            {
                Print($"[ERROR] Cleanup failed: {ex.Message}");
            }

            Print("==========================================================");
        }
    }
}

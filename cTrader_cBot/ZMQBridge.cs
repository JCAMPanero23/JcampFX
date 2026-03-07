using System;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NetMQ;
using NetMQ.Sockets;
using cAlgo.API;

namespace JcampFX
{
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
        private SubSocket _commandSocket;   // Port 5556 (receive from Python)
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
                _commandSocket = new SubSocket();
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
}

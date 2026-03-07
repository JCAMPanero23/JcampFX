using System;
using System.Text.Json.Serialization;

namespace JcampFX
{
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
}

//+------------------------------------------------------------------+
//|                                                   ZMQ_Bridge.mqh |
//|                                      JcampFX ZMQ Bridge Wrapper  |
//|                                 Phase 4: MT5 <-> Python Bridge   |
//+------------------------------------------------------------------+
#property copyright "JcampFX"
#property link      "https://github.com/jcampo/JcampFX"
#property version   "1.00"
#property strict

//--- Include MQL5 ZMQ library
#include <Zmq/Zmq.mqh>

//+------------------------------------------------------------------+
//| ZMQ Bridge Class - Handles communication with Python Brain       |
//+------------------------------------------------------------------+
class CZMQBridge
{
private:
    // ZMQ Context and Sockets
    void*             m_context;
    void*             m_signal_socket;      // PUSH to 5555 (tick data → Python)
    void*             m_command_socket;     // SUB from 5556 (signals ← Python)
    void*             m_news_socket;        // PUSH to 5557 (news events → Python)

    // Connection state
    bool              m_is_connected;
    datetime          m_last_heartbeat;
    int               m_reconnect_attempts;

    // Configuration
    string            m_signal_endpoint;
    string            m_command_endpoint;
    string            m_news_endpoint;
    int               m_timeout_ms;

public:
    //--- Constructor/Destructor
                     CZMQBridge(void);
                    ~CZMQBridge(void);

    //--- Initialization
    bool             Initialize(string signal_addr="tcp://localhost:5555",
                               string command_addr="tcp://localhost:5556",
                               string news_addr="tcp://localhost:5557");
    void             Shutdown(void);

    //--- Connection management
    bool             IsConnected(void) const { return m_is_connected; }
    bool             Reconnect(void);
    void             SendHeartbeat(void);
    bool             CheckHealth(void);

    //--- Message sending
    bool             SendTickData(const string symbol, const MqlTick &tick);
    bool             SendBarClose(const string symbol, const MqlRates &bar);
    bool             SendNewsEvent(const MqlCalendarValue &event);
    bool             SendMessage(const string channel, const string json_data);

    //--- Message receiving
    string           ReceiveCommand(bool blocking=false);
    bool             HasPendingCommands(void);

private:
    //--- Helper methods
    string           TickToJSON(const string symbol, const MqlTick &tick);
    string           BarToJSON(const string symbol, const MqlRates &bar);
    string           NewsToJSON(const MqlCalendarValue &event);
    bool             SendToSocket(void* socket, const string message);
    string           ReceiveFromSocket(void* socket, bool blocking);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CZMQBridge::CZMQBridge(void)
{
    m_context = NULL;
    m_signal_socket = NULL;
    m_command_socket = NULL;
    m_news_socket = NULL;
    m_is_connected = false;
    m_last_heartbeat = 0;
    m_reconnect_attempts = 0;
    m_timeout_ms = 100;  // 100ms timeout for non-blocking receives
}

//+------------------------------------------------------------------+
//| Destructor                                                        |
//+------------------------------------------------------------------+
CZMQBridge::~CZMQBridge(void)
{
    Shutdown();
}

//+------------------------------------------------------------------+
//| Initialize ZMQ sockets                                            |
//+------------------------------------------------------------------+
bool CZMQBridge::Initialize(string signal_addr, string command_addr, string news_addr)
{
    Print("[ZMQ] Initializing bridge...");

    m_signal_endpoint = signal_addr;
    m_command_endpoint = command_addr;
    m_news_endpoint = news_addr;

    // Create ZMQ context
    m_context = zmq_ctx_new();
    if(m_context == NULL)
    {
        Print("[ZMQ] ERROR: Failed to create context");
        return false;
    }

    // Signal socket (PUSH) - Send tick data to Python
    m_signal_socket = zmq_socket(m_context, ZMQ_PUSH);
    if(m_signal_socket == NULL)
    {
        Print("[ZMQ] ERROR: Failed to create signal socket");
        return false;
    }

    if(zmq_connect(m_signal_socket, m_signal_endpoint) != 0)
    {
        Print("[ZMQ] ERROR: Failed to connect signal socket to ", m_signal_endpoint);
        return false;
    }
    Print("[ZMQ] Signal socket connected: ", m_signal_endpoint);

    // Command socket (SUB) - Receive signals from Python
    m_command_socket = zmq_socket(m_context, ZMQ_SUB);
    if(m_command_socket == NULL)
    {
        Print("[ZMQ] ERROR: Failed to create command socket");
        return false;
    }

    // Subscribe to all messages (empty filter)
    if(zmq_setsockopt(m_command_socket, ZMQ_SUBSCRIBE, "", 0) != 0)
    {
        Print("[ZMQ] ERROR: Failed to set subscription filter");
        return false;
    }

    if(zmq_connect(m_command_socket, m_command_endpoint) != 0)
    {
        Print("[ZMQ] ERROR: Failed to connect command socket to ", m_command_endpoint);
        return false;
    }
    Print("[ZMQ] Command socket connected: ", m_command_endpoint);

    // News socket (PUSH) - Send news events to Python
    m_news_socket = zmq_socket(m_context, ZMQ_PUSH);
    if(m_news_socket == NULL)
    {
        Print("[ZMQ] ERROR: Failed to create news socket");
        return false;
    }

    if(zmq_connect(m_news_socket, m_news_endpoint) != 0)
    {
        Print("[ZMQ] ERROR: Failed to connect news socket to ", m_news_endpoint);
        return false;
    }
    Print("[ZMQ] News socket connected: ", m_news_endpoint);

    // Set non-blocking receive timeout
    zmq_setsockopt(m_command_socket, ZMQ_RCVTIMEO, m_timeout_ms);

    m_is_connected = true;
    m_last_heartbeat = TimeCurrent();

    Print("[ZMQ] Bridge initialized successfully");
    return true;
}

//+------------------------------------------------------------------+
//| Shutdown ZMQ connections                                          |
//+------------------------------------------------------------------+
void CZMQBridge::Shutdown(void)
{
    if(!m_is_connected)
        return;

    Print("[ZMQ] Shutting down bridge...");

    // Close sockets
    if(m_signal_socket != NULL)
    {
        zmq_close(m_signal_socket);
        m_signal_socket = NULL;
    }

    if(m_command_socket != NULL)
    {
        zmq_close(m_command_socket);
        m_command_socket = NULL;
    }

    if(m_news_socket != NULL)
    {
        zmq_close(m_news_socket);
        m_news_socket = NULL;
    }

    // Destroy context
    if(m_context != NULL)
    {
        zmq_ctx_destroy(m_context);
        m_context = NULL;
    }

    m_is_connected = false;
    Print("[ZMQ] Bridge shutdown complete");
}

//+------------------------------------------------------------------+
//| Send tick data to Python Brain                                   |
//+------------------------------------------------------------------+
bool CZMQBridge::SendTickData(const string symbol, const MqlTick &tick)
{
    if(!m_is_connected)
        return false;

    string json = TickToJSON(symbol, tick);
    return SendToSocket(m_signal_socket, json);
}

//+------------------------------------------------------------------+
//| Send Range Bar close to Python Brain                             |
//+------------------------------------------------------------------+
bool CZMQBridge::SendBarClose(const string symbol, const MqlRates &bar)
{
    if(!m_is_connected)
        return false;

    string json = BarToJSON(symbol, bar);
    return SendToSocket(m_signal_socket, json);
}

//+------------------------------------------------------------------+
//| Convert tick to JSON format                                      |
//+------------------------------------------------------------------+
string CZMQBridge::TickToJSON(const string symbol, const MqlTick &tick)
{
    // Format: {"type":"tick","symbol":"EURUSD","time":123456,"bid":1.0850,"ask":1.0852,"last":1.0851,"volume":100,"flags":2}
    string json = StringFormat(
        "{\"type\":\"tick\",\"symbol\":\"%s\",\"time\":%I64d,\"bid\":%.5f,\"ask\":%.5f,\"last\":%.5f,\"volume\":%I64d,\"flags\":%d}",
        symbol,
        (long)tick.time,
        tick.bid,
        tick.ask,
        tick.last,
        tick.volume,
        tick.flags
    );

    return json;
}

//+------------------------------------------------------------------+
//| Convert bar to JSON format                                       |
//+------------------------------------------------------------------+
string CZMQBridge::BarToJSON(const string symbol, const MqlRates &bar)
{
    // Format: {"type":"bar","symbol":"EURUSD","time":123456,"open":1.0850,"high":1.0860,"low":1.0845,"close":1.0855,"volume":1000}
    string json = StringFormat(
        "{\"type\":\"bar\",\"symbol\":\"%s\",\"time\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%I64d}",
        symbol,
        (long)bar.time,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.tick_volume
    );

    return json;
}

//+------------------------------------------------------------------+
//| Send generic message to signal socket                            |
//+------------------------------------------------------------------+
bool CZMQBridge::SendMessage(const string channel, const string json_data)
{
    if(!m_is_connected)
        return false;

    // Add channel prefix for routing
    string message = StringFormat("{\"channel\":\"%s\",\"data\":%s}", channel, json_data);
    return SendToSocket(m_signal_socket, message);
}

//+------------------------------------------------------------------+
//| Send message to socket (helper)                                  |
//+------------------------------------------------------------------+
bool CZMQBridge::SendToSocket(void* socket, const string message)
{
    if(socket == NULL)
        return false;

    // Convert string to char array for ZMQ
    uchar data[];
    StringToCharArray(message, data, 0, WHOLE_ARRAY, CP_UTF8);

    // Send message
    int result = zmq_send(socket, data, ArraySize(data) - 1, ZMQ_DONTWAIT);  // -1 to exclude null terminator

    if(result < 0)
    {
        int error = zmq_errno();
        Print("[ZMQ] Send error: ", error);
        return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| Receive command from Python Brain                                |
//+------------------------------------------------------------------+
string CZMQBridge::ReceiveCommand(bool blocking=false)
{
    if(!m_is_connected)
        return "";

    return ReceiveFromSocket(m_command_socket, blocking);
}

//+------------------------------------------------------------------+
//| Receive message from socket (helper)                             |
//+------------------------------------------------------------------+
string CZMQBridge::ReceiveFromSocket(void* socket, bool blocking)
{
    if(socket == NULL)
        return "";

    // Set blocking/non-blocking mode
    int timeout = blocking ? -1 : m_timeout_ms;
    zmq_setsockopt(socket, ZMQ_RCVTIMEO, timeout);

    // Receive message
    uchar buffer[4096];
    int received = zmq_recv(socket, buffer, 4096, 0);

    if(received < 0)
    {
        int error = zmq_errno();
        if(error != EAGAIN)  // EAGAIN means no message available (expected for non-blocking)
            Print("[ZMQ] Receive error: ", error);
        return "";
    }

    // Convert to string
    string message = CharArrayToString(buffer, 0, received, CP_UTF8);
    return message;
}

//+------------------------------------------------------------------+
//| Check if there are pending commands                              |
//+------------------------------------------------------------------+
bool CZMQBridge::HasPendingCommands(void)
{
    if(!m_is_connected)
        return false;

    // Try non-blocking receive
    string msg = ReceiveCommand(false);
    return (StringLen(msg) > 0);
}

//+------------------------------------------------------------------+
//| Send heartbeat to Python Brain                                   |
//+------------------------------------------------------------------+
void CZMQBridge::SendHeartbeat(void)
{
    if(!m_is_connected)
        return;

    string json = StringFormat("{\"type\":\"heartbeat\",\"time\":%I64d}", (long)TimeCurrent());
    SendMessage("heartbeat", json);
    m_last_heartbeat = TimeCurrent();
}

//+------------------------------------------------------------------+
//| Check connection health                                          |
//+------------------------------------------------------------------+
bool CZMQBridge::CheckHealth(void)
{
    if(!m_is_connected)
        return false;

    // If last heartbeat was more than 60 seconds ago, reconnect
    if(TimeCurrent() - m_last_heartbeat > 60)
    {
        Print("[ZMQ] Heartbeat timeout, attempting reconnect...");
        return Reconnect();
    }

    return true;
}

//+------------------------------------------------------------------+
//| Reconnect ZMQ sockets                                            |
//+------------------------------------------------------------------+
bool CZMQBridge::Reconnect(void)
{
    Print("[ZMQ] Reconnecting... (attempt ", m_reconnect_attempts + 1, ")");

    Shutdown();
    Sleep(1000);  // Wait 1 second before reconnecting

    bool success = Initialize(m_signal_endpoint, m_command_endpoint, m_news_endpoint);

    if(success)
    {
        m_reconnect_attempts = 0;
        Print("[ZMQ] Reconnected successfully");
    }
    else
    {
        m_reconnect_attempts++;
        Print("[ZMQ] Reconnect failed");
    }

    return success;
}

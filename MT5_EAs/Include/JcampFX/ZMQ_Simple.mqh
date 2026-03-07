//+------------------------------------------------------------------+
//|                                                   ZMQ_Simple.mqh |
//|                              Simplified ZMQ wrapper for JcampFX  |
//|                       Direct DLL imports - no external library   |
//+------------------------------------------------------------------+
#property copyright "JcampFX"
#property link      "https://github.com/jcampo/JcampFX"
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| ZMQ Constants                                                     |
//+------------------------------------------------------------------+
#define ZMQ_PUSH 8
#define ZMQ_PULL 7
#define ZMQ_PUB 1
#define ZMQ_SUB 2
#define ZMQ_DONTWAIT 1
#define ZMQ_SUBSCRIBE 6
#define ZMQ_RCVTIMEO 27
#define EAGAIN 11

//+------------------------------------------------------------------+
//| DLL Imports - libzmq.dll                                         |
//+------------------------------------------------------------------+
#import "libzmq.dll"
   long zmq_ctx_new();
   int zmq_ctx_term(long context);
   long zmq_socket(long context, int type);
   int zmq_close(long socket);
   int zmq_connect(long socket, const char &addr[]);
   int zmq_bind(long socket, const char &addr[]);
   int zmq_setsockopt(long socket, int option, const int &value, int size);
   int zmq_send(long socket, const uchar &data[], int length, int flags);
   int zmq_recv(long socket, uchar &buffer[], int length, int flags);
   int zmq_errno();
#import

//+------------------------------------------------------------------+
//| Simple ZMQ Bridge Class                                          |
//+------------------------------------------------------------------+
class CZMQSimple
{
private:
    long              m_context;
    long              m_signal_socket;      // PUSH (send to Python)
    long              m_command_socket;     // SUB (receive from Python)

    bool              m_is_connected;
    datetime          m_last_heartbeat;

public:
                     CZMQSimple(void);
                    ~CZMQSimple(void);

    bool             Initialize(void);
    void             Shutdown(void);
    bool             IsConnected(void) const { return m_is_connected; }

    bool             SendMessage(const string message);
    string           ReceiveMessage(void);
    void             SendHeartbeat(void);
};

//+------------------------------------------------------------------+
//| Constructor                                                       |
//+------------------------------------------------------------------+
CZMQSimple::CZMQSimple(void)
{
    m_context = 0;
    m_signal_socket = 0;
    m_command_socket = 0;
    m_is_connected = false;
    m_last_heartbeat = 0;
}

//+------------------------------------------------------------------+
//| Destructor                                                        |
//+------------------------------------------------------------------+
CZMQSimple::~CZMQSimple(void)
{
    Shutdown();
}

//+------------------------------------------------------------------+
//| Initialize ZMQ context and sockets                               |
//+------------------------------------------------------------------+
bool CZMQSimple::Initialize(void)
{
    Print("[ZMQ] Initializing simple bridge...");

    // Create context
    m_context = zmq_ctx_new();
    if(m_context == 0)
    {
        Print("[ZMQ] ERROR: Failed to create context");
        return false;
    }

    // Create PUSH socket (send to Python on port 5555)
    m_signal_socket = zmq_socket(m_context, ZMQ_PUSH);
    if(m_signal_socket == 0)
    {
        Print("[ZMQ] ERROR: Failed to create signal socket");
        return false;
    }

    // Connect to Python listener
    char addr[];
    StringToCharArray("tcp://localhost:5555", addr, 0, WHOLE_ARRAY, CP_UTF8);
    if(zmq_connect(m_signal_socket, addr) != 0)
    {
        Print("[ZMQ] ERROR: Failed to connect signal socket");
        return false;
    }
    Print("[ZMQ] Signal socket connected to tcp://localhost:5555");

    // Create SUB socket (receive from Python on port 5556)
    m_command_socket = zmq_socket(m_context, ZMQ_SUB);
    if(m_command_socket == 0)
    {
        Print("[ZMQ] ERROR: Failed to create command socket");
        return false;
    }

    // Subscribe to all messages
    int empty = 0;
    zmq_setsockopt(m_command_socket, ZMQ_SUBSCRIBE, empty, 0);

    // Set receive timeout (100ms)
    int timeout = 100;
    zmq_setsockopt(m_command_socket, ZMQ_RCVTIMEO, timeout, sizeof(int));

    // Connect to Python publisher
    char addr2[];
    StringToCharArray("tcp://localhost:5556", addr2, 0, WHOLE_ARRAY, CP_UTF8);
    if(zmq_connect(m_command_socket, addr2) != 0)
    {
        Print("[ZMQ] ERROR: Failed to connect command socket");
        return false;
    }
    Print("[ZMQ] Command socket connected to tcp://localhost:5556");

    m_is_connected = true;
    m_last_heartbeat = TimeCurrent();

    Print("[ZMQ] Simple bridge initialized successfully");
    return true;
}

//+------------------------------------------------------------------+
//| Shutdown ZMQ sockets and context                                 |
//+------------------------------------------------------------------+
void CZMQSimple::Shutdown(void)
{
    if(!m_is_connected)
        return;

    Print("[ZMQ] Shutting down...");

    if(m_signal_socket != 0)
    {
        zmq_close(m_signal_socket);
        m_signal_socket = 0;
    }

    if(m_command_socket != 0)
    {
        zmq_close(m_command_socket);
        m_command_socket = 0;
    }

    if(m_context != 0)
    {
        zmq_ctx_term(m_context);
        m_context = 0;
    }

    m_is_connected = false;
    Print("[ZMQ] Shutdown complete");
}

//+------------------------------------------------------------------+
//| Send JSON message to Python                                      |
//+------------------------------------------------------------------+
bool CZMQSimple::SendMessage(const string message)
{
    if(!m_is_connected || m_signal_socket == 0)
        return false;

    // Convert string to byte array
    uchar data[];
    int length = StringToCharArray(message, data, 0, WHOLE_ARRAY, CP_UTF8);

    // Send (length-1 to exclude null terminator)
    int result = zmq_send(m_signal_socket, data, length - 1, ZMQ_DONTWAIT);

    if(result < 0)
    {
        int error = zmq_errno();
        Print("[ZMQ] Send error: ", error);
        return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| Receive message from Python (non-blocking)                       |
//+------------------------------------------------------------------+
string CZMQSimple::ReceiveMessage(void)
{
    if(!m_is_connected || m_command_socket == 0)
        return "";

    uchar buffer[4096];
    int received = zmq_recv(m_command_socket, buffer, 4096, 0);

    if(received < 0)
    {
        int error = zmq_errno();
        if(error != EAGAIN)  // EAGAIN = no message available (normal)
            Print("[ZMQ] Receive error: ", error);
        return "";
    }

    // Convert to string
    string message = CharArrayToString(buffer, 0, received, CP_UTF8);
    return message;
}

//+------------------------------------------------------------------+
//| Send heartbeat message                                           |
//+------------------------------------------------------------------+
void CZMQSimple::SendHeartbeat(void)
{
    string json = StringFormat("{\"type\":\"heartbeat\",\"time\":%I64d}", (long)TimeCurrent());
    SendMessage(json);
    m_last_heartbeat = TimeCurrent();
}

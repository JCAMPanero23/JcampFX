//+------------------------------------------------------------------+
//|                                               JcampFX_Brain.mq5  |
//|                        JcampFX - Phase 4 ZMQ Bridge to Python    |
//|                         Real-time tick streaming & signal exec   |
//+------------------------------------------------------------------+
#property copyright "JcampFX"
#property link      "https://github.com/jcampo/JcampFX"
#property version   "4.00"
#property description "Phase 4: Simplified ZMQ bridge - MT5 to Python"
#property strict

//--- Include simplified ZMQ bridge
#include <JcampFX/ZMQ_Simple.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                  |
//+------------------------------------------------------------------+
input string   InpPairs = "EURUSD,USDJPY,AUDJPY,USDCHF";  // Trading pairs (Phase 3.6 validated portfolio)
input string   InpBrokerSuffix = ".r";                    // Broker symbol suffix (e.g. .r for FP Markets)
input int      InpHeartbeatSeconds = 30;                  // Heartbeat interval
input bool     InpEnableTrading = true;                   // Enable trading
input int      InpMagicNumber = 777001;                   // Magic number for order identification
input int      InpSlippagePips = 2;                       // Maximum slippage in pips
input bool     InpEnableNewsGating = true;                // Enable news event monitoring
input int      InpNewsCheckIntervalMinutes = 15;          // News check interval (minutes)

//+------------------------------------------------------------------+
//| Global Variables                                                  |
//+------------------------------------------------------------------+
CZMQSimple*    g_zmq;                  // ZMQ bridge instance
string         g_pairs[];              // Array of trading pairs
datetime       g_last_heartbeat;       // Last heartbeat timestamp
datetime       g_last_news_check;      // Last news check timestamp
bool           g_initialized = false;  // Initialization flag

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("==========================================================");
    Print("JcampFX Brain EA - Phase 4 (Simplified ZMQ)");
    Print("==========================================================");

    // Parse trading pairs
    if(!ParsePairs(InpPairs, g_pairs))
    {
        Print("[ERROR] Failed to parse trading pairs");
        return INIT_PARAMETERS_INCORRECT;
    }

    Print("[INFO] Monitoring ", ArraySize(g_pairs), " pairs");

    // Initialize ZMQ bridge
    g_zmq = new CZMQSimple();
    if(!g_zmq.Initialize())
    {
        Print("[ERROR] Failed to initialize ZMQ bridge");
        delete g_zmq;
        return INIT_FAILED;
    }

    // Subscribe to tick data for all pairs
    for(int i = 0; i < ArraySize(g_pairs); i++)
    {
        string symbol_clean = g_pairs[i];  // Clean symbol (e.g. EURUSD)
        string symbol_full = symbol_clean + InpBrokerSuffix;  // With broker suffix (e.g. EURUSD.r)

        if(!SymbolSelect(symbol_full, true))
        {
            Print("[WARNING] Failed to select symbol: ", symbol_full);
        }
        else
        {
            Print("[INFO] Subscribed to ticks: ", symbol_full);
        }
    }

    g_last_heartbeat = TimeCurrent();
    g_last_news_check = TimeCurrent();
    g_initialized = true;

    Print("[SUCCESS] JcampFX Brain EA initialized");

    if(InpEnableNewsGating)
    {
        Print("[INFO] News gating enabled - checking calendar every ", InpNewsCheckIntervalMinutes, " minutes");
        // Send initial news update
        BroadcastNewsEvents();
    }

    Print("==========================================================");

    // Set timer for heartbeat and news checks (every 10 seconds)
    EventSetTimer(10);

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("==========================================================");
    Print("JcampFX Brain EA shutting down...");

    EventKillTimer();

    // Shutdown ZMQ bridge
    if(g_zmq != NULL)
    {
        g_zmq.Shutdown();
        delete g_zmq;
        g_zmq = NULL;
    }

    Print("JcampFX Brain EA shutdown complete");
    Print("==========================================================");
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
    if(!g_initialized || g_zmq == NULL)
        return;

    // Send ticks for ALL monitored pairs (not just chart symbol)
    for(int i = 0; i < ArraySize(g_pairs); i++)
    {
        string symbol_clean = g_pairs[i];
        string symbol_full = symbol_clean + InpBrokerSuffix;
        MqlTick tick;

        if(!SymbolInfoTick(symbol_full, tick))
            continue;  // Skip if tick unavailable

        // Create JSON message with FULL symbol (including suffix)
        // Python will strip the suffix on its side
        string json = StringFormat(
            "{\"type\":\"tick\",\"symbol\":\"%s\",\"time\":%I64d,\"bid\":%.5f,\"ask\":%.5f,\"last\":%.5f,\"volume\":%I64d,\"flags\":%d}",
            symbol_full,
            (long)tick.time,
            tick.bid,
            tick.ask,
            tick.last,
            tick.volume,
            tick.flags
        );

        // Send to Python
        g_zmq.SendMessage(json);
    }

    // Check for incoming commands
    string command = g_zmq.ReceiveMessage();
    if(StringLen(command) > 0)
    {
        ProcessCommand(command);
    }
}

//+------------------------------------------------------------------+
//| Timer function                                                    |
//+------------------------------------------------------------------+
void OnTimer()
{
    if(!g_initialized || g_zmq == NULL)
        return;

    // Send heartbeat
    if(TimeCurrent() - g_last_heartbeat >= InpHeartbeatSeconds)
    {
        g_zmq.SendHeartbeat();
        g_last_heartbeat = TimeCurrent();
    }

    // Check for pending commands
    string command = g_zmq.ReceiveMessage();
    if(StringLen(command) > 0)
    {
        ProcessCommand(command);
    }

    // Check for news events periodically
    if(InpEnableNewsGating && TimeCurrent() - g_last_news_check >= InpNewsCheckIntervalMinutes * 60)
    {
        BroadcastNewsEvents();
        g_last_news_check = TimeCurrent();
    }
}

//+------------------------------------------------------------------+
//| Broadcast news events to Python Brain                            |
//+------------------------------------------------------------------+
void BroadcastNewsEvents()
{
    if(g_zmq == NULL)
        return;

    // Get news events from calendar
    // Look ahead 24 hours for upcoming events
    datetime from = TimeCurrent();
    datetime to = TimeCurrent() + 86400;  // +24 hours

    MqlCalendarValue values[];
    int count = CalendarValueHistory(values, from, to);

    if(count <= 0)
    {
        // No events found - send empty update
        string json = "{\"type\":\"news_update\",\"events\":[],\"timestamp\":" + IntegerToString((long)TimeCurrent()) + "}";
        g_zmq.SendMessage(json);
        return;
    }

    Print("[NEWS] Found ", count, " upcoming calendar events");

    // Filter high-impact events for relevant currencies
    string relevantCurrencies[] = {"USD", "EUR", "JPY", "AUD", "CHF", "GBP"};
    int sentCount = 0;

    for(int i = 0; i < count; i++)
    {
        MqlCalendarEvent event;
        if(!CalendarEventById(values[i].event_id, event))
            continue;

        MqlCalendarCountry country;
        if(!CalendarCountryById(event.country_id, country))
            continue;

        // Check if currency is relevant
        bool isRelevant = false;
        for(int j = 0; j < ArraySize(relevantCurrencies); j++)
        {
            if(country.currency == relevantCurrencies[j])
            {
                isRelevant = true;
                break;
            }
        }

        if(!isRelevant)
            continue;

        // Filter by importance (High = 3, Medium = 2, Low = 1, None = 0)
        if(event.importance < 2)  // Only Medium (2) and High (3) importance
            continue;

        // Send event to Python
        string eventJson = StringFormat(
            "{\"type\":\"news_event\",\"currency\":\"%s\",\"event_name\":\"%s\",\"time\":%I64d,\"importance\":%d,\"actual\":%.5f,\"forecast\":%.5f,\"previous\":%.5f}",
            country.currency,
            event.name,
            (long)values[i].time,
            event.importance,
            values[i].actual_value,
            values[i].forecast_value,
            values[i].prev_value
        );

        g_zmq.SendMessage(eventJson);
        sentCount++;
    }

    Print("[NEWS] Sent ", sentCount, " relevant news events to Python Brain");

    // Send completion marker
    string json = "{\"type\":\"news_update_complete\",\"count\":" + IntegerToString(sentCount) + ",\"timestamp\":" + IntegerToString((long)TimeCurrent()) + "}";
    g_zmq.SendMessage(json);
}

//+------------------------------------------------------------------+
//| Process command from Python Brain                                |
//+------------------------------------------------------------------+
void ProcessCommand(const string json)
{
    Print("[COMMAND] Received: ", json);

    if(!InpEnableTrading)
    {
        Print("[WARNING] Trading disabled - ignoring command");
        return;
    }

    // Parse JSON command
    // Format: {"type":"entry","symbol":"EURUSD","direction":"BUY","sl":1.0850,"tp":null,"lots":0.01}

    string type = ExtractJSONString(json, "type");

    if(type == "entry")
    {
        ExecuteEntrySignal(json);
    }
    else if(type == "exit")
    {
        ExecuteExitSignal(json);
    }
    else if(type == "modify")
    {
        ExecuteModifySignal(json);
    }
    else
    {
        Print("[ERROR] Unknown command type: ", type);
    }
}

//+------------------------------------------------------------------+
//| Execute entry signal from Python Brain                           |
//+------------------------------------------------------------------+
void ExecuteEntrySignal(const string json)
{
    // Parse signal parameters
    string symbol = ExtractJSONString(json, "symbol");
    string direction = ExtractJSONString(json, "direction");
    double sl = ExtractJSONDouble(json, "sl");
    double tp = ExtractJSONDouble(json, "tp");
    double lots = ExtractJSONDouble(json, "lots");

    // Add broker suffix if needed
    if(StringLen(InpBrokerSuffix) > 0 && StringFind(symbol, InpBrokerSuffix) < 0)
        symbol = symbol + InpBrokerSuffix;

    // Validate parameters
    if(lots <= 0.0)
    {
        Print("[ERROR] Invalid lot size: ", lots);
        return;
    }

    // Determine order type
    ENUM_ORDER_TYPE orderType;
    if(direction == "BUY")
        orderType = ORDER_TYPE_BUY;
    else if(direction == "SELL")
        orderType = ORDER_TYPE_SELL;
    else
    {
        Print("[ERROR] Invalid direction: ", direction);
        return;
    }

    // Get current price
    MqlTick tick;
    if(!SymbolInfoTick(symbol, tick))
    {
        Print("[ERROR] Failed to get tick for ", symbol);
        return;
    }

    double price = (orderType == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

    // Calculate slippage in points
    double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
    int slippage = (int)(InpSlippagePips * 10);  // Convert pips to points

    // Round lot size to valid step
    double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
    lots = MathRound(lots / lotStep) * lotStep;

    // Validate lot size
    double minLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
    if(lots < minLot)
        lots = minLot;
    if(lots > maxLot)
        lots = maxLot;

    // Prepare trade request
    MqlTradeRequest request = {};
    MqlTradeResult result = {};

    request.action = TRADE_ACTION_DEAL;
    request.symbol = symbol;
    request.volume = lots;
    request.type = orderType;
    request.price = price;
    request.sl = sl;
    request.tp = (tp > 0.0) ? tp : 0.0;  // TP optional (managed by Python)
    request.deviation = slippage;
    request.magic = InpMagicNumber;
    request.comment = "JcampFX_Brain";
    request.type_filling = ORDER_FILLING_FOK;  // Fill or Kill

    // Send order
    if(!OrderSend(request, result))
    {
        Print("[ERROR] OrderSend failed: ", GetLastError());
        Print("[ERROR] Result code: ", result.retcode, " (", result.retcode_external, ")");
        SendExecutionReport(false, symbol, direction, 0, 0.0, result.retcode);
        return;
    }

    // Check result
    if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
    {
        Print("[SUCCESS] Order executed: Ticket #", result.order, " ", symbol, " ", direction,
              " lots=", lots, " price=", result.price, " SL=", sl);
        SendExecutionReport(true, symbol, direction, (int)result.order, result.price, result.retcode);
    }
    else
    {
        Print("[ERROR] Order failed: retcode=", result.retcode, " ", result.comment);
        SendExecutionReport(false, symbol, direction, 0, 0.0, result.retcode);
    }
}

//+------------------------------------------------------------------+
//| Execute exit signal from Python Brain                            |
//+------------------------------------------------------------------+
void ExecuteExitSignal(const string json)
{
    int ticket = (int)ExtractJSONDouble(json, "ticket");

    if(ticket <= 0)
    {
        Print("[ERROR] Invalid ticket: ", ticket);
        return;
    }

    // Select position by ticket
    if(!PositionSelectByTicket(ticket))
    {
        Print("[ERROR] Position not found: ", ticket);
        return;
    }

    // Get position details
    string symbol = PositionGetString(POSITION_SYMBOL);
    double volume = PositionGetDouble(POSITION_VOLUME);
    ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

    // Determine close order type
    ENUM_ORDER_TYPE orderType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

    // Get current price
    MqlTick tick;
    if(!SymbolInfoTick(symbol, tick))
    {
        Print("[ERROR] Failed to get tick for ", symbol);
        return;
    }

    double price = (orderType == ORDER_TYPE_SELL) ? tick.bid : tick.ask;

    // Prepare close request
    MqlTradeRequest request = {};
    MqlTradeResult result = {};

    request.action = TRADE_ACTION_DEAL;
    request.symbol = symbol;
    request.volume = volume;
    request.type = orderType;
    request.price = price;
    request.position = ticket;
    request.deviation = InpSlippagePips * 10;
    request.magic = InpMagicNumber;
    request.comment = "JcampFX_Close";
    request.type_filling = ORDER_FILLING_FOK;

    // Send close order
    if(!OrderSend(request, result))
    {
        Print("[ERROR] Close order failed: ", GetLastError());
        return;
    }

    if(result.retcode == TRADE_RETCODE_DONE)
    {
        Print("[SUCCESS] Position closed: Ticket #", ticket, " at ", result.price);
    }
    else
    {
        Print("[ERROR] Close failed: retcode=", result.retcode);
    }
}

//+------------------------------------------------------------------+
//| Execute modify signal (SL/TP adjustment)                         |
//+------------------------------------------------------------------+
void ExecuteModifySignal(const string json)
{
    int ticket = (int)ExtractJSONDouble(json, "ticket");
    double newSL = ExtractJSONDouble(json, "sl");
    double newTP = ExtractJSONDouble(json, "tp");

    if(ticket <= 0)
    {
        Print("[ERROR] Invalid ticket: ", ticket);
        return;
    }

    // Select position
    if(!PositionSelectByTicket(ticket))
    {
        Print("[ERROR] Position not found: ", ticket);
        return;
    }

    string symbol = PositionGetString(POSITION_SYMBOL);

    // Prepare modify request
    MqlTradeRequest request = {};
    MqlTradeResult result = {};

    request.action = TRADE_ACTION_SLTP;
    request.symbol = symbol;
    request.position = ticket;
    request.sl = newSL;
    request.tp = (newTP > 0.0) ? newTP : 0.0;
    request.magic = InpMagicNumber;

    // Send modify order
    if(!OrderSend(request, result))
    {
        Print("[ERROR] Modify failed: ", GetLastError());
        return;
    }

    if(result.retcode == TRADE_RETCODE_DONE)
    {
        Print("[SUCCESS] Position modified: Ticket #", ticket, " SL=", newSL, " TP=", newTP);
    }
    else
    {
        Print("[ERROR] Modify failed: retcode=", result.retcode);
    }
}

//+------------------------------------------------------------------+
//| Send execution report back to Python Brain                       |
//+------------------------------------------------------------------+
void SendExecutionReport(bool success, string symbol, string direction, int ticket, double price, int retcode)
{
    if(g_zmq == NULL)
        return;

    // Create execution report JSON
    string report = StringFormat(
        "{\"type\":\"execution_report\",\"success\":%s,\"symbol\":\"%s\",\"direction\":\"%s\",\"ticket\":%d,\"price\":%.5f,\"retcode\":%d,\"time\":%I64d}",
        success ? "true" : "false",
        symbol,
        direction,
        ticket,
        price,
        retcode,
        (long)TimeCurrent()
    );

    g_zmq.SendMessage(report);
    Print("[REPORT] Execution report sent: ", report);
}

//+------------------------------------------------------------------+
//| Simple JSON parser - extract string value                        |
//+------------------------------------------------------------------+
string ExtractJSONString(const string json, const string key)
{
    // Find key in JSON (handles optional whitespace after colon)
    string searchKey = "\"" + key + "\"";
    int start = StringFind(json, searchKey);
    if(start < 0)
        return "";

    start += StringLen(searchKey);

    // Skip colon and optional whitespace
    while(start < StringLen(json))
    {
        string ch = StringSubstr(json, start, 1);
        if(ch == ":" || ch == " ")
            start++;
        else if(ch == "\"")
        {
            start++;  // Skip opening quote
            break;
        }
        else
            return "";  // Invalid format
    }

    // Find closing quote
    int end = StringFind(json, "\"", start);
    if(end < 0)
        return "";

    return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
//| Simple JSON parser - extract double value                        |
//+------------------------------------------------------------------+
double ExtractJSONDouble(const string json, const string key)
{
    // Find key in JSON
    string searchKey = "\"" + key + "\"";
    int start = StringFind(json, searchKey);
    if(start < 0)
        return 0.0;

    start += StringLen(searchKey);

    // Skip colon and optional whitespace
    while(start < StringLen(json))
    {
        string ch = StringSubstr(json, start, 1);
        if(ch == ":" || ch == " ")
            start++;
        else
            break;
    }

    // Find end of number (comma, brace, or bracket)
    int end = start;
    while(end < StringLen(json))
    {
        string ch = StringSubstr(json, end, 1);
        if(ch == "," || ch == "}" || ch == "]")
            break;
        end++;
    }

    string valueStr = StringSubstr(json, start, end - start);
    StringTrimLeft(valueStr);
    StringTrimRight(valueStr);

    // Handle null
    if(valueStr == "null")
        return 0.0;

    return StringToDouble(valueStr);
}

//+------------------------------------------------------------------+
//| Parse comma-separated pairs string                               |
//+------------------------------------------------------------------+
bool ParsePairs(const string pairs_str, string &pairs[])
{
    string items[];
    int count = StringSplit(pairs_str, ',', items);

    if(count <= 0)
        return false;

    ArrayResize(pairs, count);

    for(int i = 0; i < count; i++)
    {
        string pair = items[i];
        StringTrimLeft(pair);
        StringTrimRight(pair);
        StringToUpper(pair);
        pairs[i] = pair;
    }

    return true;
}

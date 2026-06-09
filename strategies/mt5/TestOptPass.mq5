// TestOptPass.mq5
// Tests whether MQL5 file writes from OnTester() work in headless optimization.
// Two approaches tested in sequence:
//   1. Direct write from OnTester() to opt_test_direct.csv
//   2. Frame-based write via OnTesterPass() to opt_test_frames.csv
// If approach 1 works: we can write results directly from each combo's OnTester().
// If approach 2 works: we can use the frame buffer mechanism.

#property strict

input int FastPeriod = 5;   // Fast: 5:5:15
input int SlowPeriod = 20;  // Slow: 20:5:30

int OnInit()  { return INIT_SUCCEEDED; }
void OnTick() {}
void OnDeinit(const int reason) {}

// Runs in each optimization worker. Writes directly to CSV (approach 1).
// Also sends a frame (approach 2).
double OnTester()
{
    double profit  = TesterStatistics(STAT_PROFIT);
    double dd      = TesterStatistics(STAT_EQUITY_DD_RELATIVE);
    double trades  = TesterStatistics(STAT_TRADES);
    double pf      = TesterStatistics(STAT_PROFIT_FACTOR);

    // --- Approach 1: direct file write ---
    int fh = FileOpen("opt_test_direct.csv",
                      FILE_WRITE | FILE_READ | FILE_CSV | FILE_ANSI | FILE_SHARE_WRITE | FILE_SHARE_READ,
                      ',');
    if(fh != INVALID_HANDLE)
    {
        FileSeek(fh, 0, SEEK_END);
        FileWrite(fh, FastPeriod, SlowPeriod, profit, dd, trades, pf);
        FileClose(fh);
    }
    else
    {
        Print("OnTester: FileOpen failed, error=", GetLastError());
    }

    // --- Approach 2: frame ---
    double data[4];
    data[0] = (double)FastPeriod;
    data[1] = (double)SlowPeriod;
    data[2] = profit;
    data[3] = dd;
    FrameAdd("r", (ulong)MathRound(pf * 1000), trades, data);

    return profit;
}

// Runs in the collecting terminal each time new frame(s) arrive.
void OnTesterPass()
{
    ulong  pass = 0;
    string name;
    long   id;
    double value;
    double data[];

    while(FrameNext(pass, name, id, value, data))
    {
        if(name != "r" || ArraySize(data) < 4) continue;
        int fh = FileOpen("opt_test_frames.csv",
                          FILE_WRITE | FILE_READ | FILE_CSV | FILE_ANSI,
                          ',');
        if(fh == INVALID_HANDLE) continue;
        FileSeek(fh, 0, SEEK_END);
        FileWrite(fh, (long)pass, (int)data[0], (int)data[1], data[2], data[3]);
        FileClose(fh);
    }
}

void OnTesterInit()
{
    // Write headers for both files at the start of optimization.
    int fh1 = FileOpen("opt_test_direct.csv", FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh1 != INVALID_HANDLE)
    {
        FileWrite(fh1, "FastPeriod", "SlowPeriod", "profit", "dd_relative", "trades", "profit_factor");
        FileClose(fh1);
    }
    int fh2 = FileOpen("opt_test_frames.csv", FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh2 != INVALID_HANDLE)
    {
        FileWrite(fh2, "pass", "FastPeriod", "SlowPeriod", "profit", "dd_relative");
        FileClose(fh2);
    }
}

void OnTesterDeinit()
{
    Print("OnTesterDeinit: optimization complete");
}

// TestOptPass.mq5
// Validates that OnTesterDeinit() + FrameAdd() can write optimization results to CSV.
// Run a small 4-9 combo optimization on any pair/timeframe (fast/slow MA periods).
// Check: <MT5 data path>\MQL5\Files\opt_test_results.csv exists and has one row per combo.

#property strict

input int FastPeriod = 5;   // Fast: 5:5:15
input int SlowPeriod = 20;  // Slow: 20:5:30

int OnInit()  { return INIT_SUCCEEDED; }
void OnTick() {}
void OnDeinit(const int reason) {}

// Runs in each optimization worker after its backtest completes.
// Packages the input param values + key stats into a frame and returns the criterion.
double OnTester()
{
    double profit  = TesterStatistics(STAT_PROFIT);
    double dd      = TesterStatistics(STAT_EQUITY_DD_RELATIVE);
    double trades  = TesterStatistics(STAT_TRADES);
    double pf      = TesterStatistics(STAT_PROFIT_FACTOR);

    double data[4];
    data[0] = (double)FastPeriod;
    data[1] = (double)SlowPeriod;
    data[2] = profit;
    data[3] = dd;

    FrameAdd("r", (ulong)MathRound(pf * 1000), (ulong)MathRound(trades), data);
    return profit;
}

// Runs once in the collecting terminal after ALL passes finish.
// Reads every frame and writes CSV.
void OnTesterDeinit()
{
    string path = "opt_test_results.csv";
    int fh = FileOpen(path, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh == INVALID_HANDLE)
    {
        Print("TestOptPass: cannot open output file, error=", GetLastError());
        return;
    }

    FileWrite(fh, "pass", "FastPeriod", "SlowPeriod", "profit", "dd_relative");

    ulong  pass = 0;
    string name;
    long   id;
    double value;
    double data[];

    int rows = 0;
    FrameFirst();
    while(FrameNext(pass, name, id, value, data))
    {
        if(name != "r" || ArraySize(data) < 4) continue;
        FileWrite(fh, (long)pass, (int)data[0], (int)data[1], data[2], data[3]);
        rows++;
    }

    FileClose(fh);
    Print("TestOptPass: wrote ", rows, " rows → ",
          TerminalInfoString(TERMINAL_DATA_PATH), "\\MQL5\\Files\\", path);
}

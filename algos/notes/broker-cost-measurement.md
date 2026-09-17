# Measuring a broker's costs — which tool reads what

**Last measured: 2026-09-17.**

Three broker costs, and they do not live in the same place. That is the whole reason there are
two tools rather than one.

| Cost | Where it lives | Tool |
|---|---|---|
| Spread | the tick stream | `broker_facts.py --sample` / `--history-days` |
| Swap | the symbol specification | `broker_facts.py` |
| Commission | a filled **deal** — nowhere else | `measure_commission.py` |

## Commission is the one that needs a trade

MT5 puts no commission field on a symbol specification. It appears on the deal, after a fill.
`backtest/fills.py` said for months that commission was the one cost here nobody had read, and
that was accurate: it cannot be read without either a filled deal or a trade already in history.

**Two ways to get it, and the cheap one comes first.** If the account has ALREADY traded the
symbol, read its deal history — no new trade needed:

```
python -c "import MetaTrader5 as m,datetime as dt;m.initialize(path='C:/MT5_Demo/terminal64.exe');
print([(d.symbol,d.volume,d.commission) for d in m.history_deals_get(dt.datetime(2025,1,1),dt.datetime.now()) if d.volume])"
```

**MEASURED 2026-09-17 this way, and it is the first time the figure was read rather than
assumed:** `XAUUSD.p` on PU Prime ECN costs **exactly $1.00 per lot per side**, on both
demo 700152905 (24 deals, 6.48 lots, -$6.48) and live 34957946 (2 deals, 0.28 lots, -$0.28).
That confirms the `puprime_ecn` profile's existing 1.0 rather than correcting it. The $3.50 in
the same file is the **Prime** tier and is still unread.

Only when the account has never traded the symbol does `measure_commission.py` earn its keep:
it opens one minimum-size position and closes it immediately.

## Why the demo guard is not `trade_mode`

`account_info().trade_mode` returns **0 — MT5's code for a REAL account — on PU Prime's demo
account 700152905**. The obvious guard is wrong on the exact account the tool was written for,
and it is wrong in the dangerous direction: a tool trusting it would refuse the demo and, on a
live terminal, would see the same 0 and proceed.

So the guard is three things that cannot lie together: the caller NAMES the account it expects,
the login must match, and the server name must end in `-Demo`. This is the repo's
no-vs-cannot-ask rule applied to a guard — a check whose healthy answer and whose dangerous
answer are the same value is not a check.

## The snapshot trap, measured

A 120-second live spread sample on `GBPJPY.p` read a median of **0.18**. The real median, over
956,001 stored ticks across three days, is **0.01** — the sample happened to land in the 21:00
UTC rollover hour, the one hour a day the spread blows out roughly 19x. **Always run
`--history-days` as well as `--sample`**; a short sample is not a distribution, and this one
would have been wrong by eighteen times in the expensive direction.

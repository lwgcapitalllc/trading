# This bot was renamed on 2026-09-03. Nothing else about it changed.

**`mpc_sos_fade_demo` → `sos_fade_demo`.** The MPC prefix was a company name that had nothing to
do with the strategy, and it was dropped across the whole repo in commit `0dfdcbf5`.

**Read every record in this folder as one continuous history of one bot.** The rename moved a
NAME. It did not move the account, the instrument, the strategy, the parameters or the broker.

| | before | after |
|---|---|---|
| bot key | `mpc_sos_fade_demo` | `sos_fade_demo` |
| display name | MPC SOS Fade | SOS Fade |
| strategy package | `strategies/python/mpc_sos_fade` | `strategies/python/sos_fade` |
| strategy class | `MpcSosFadeStrategy` | `SosFadeStrategy` |
| **MT5 magic number** | **770115** | **770115 — unchanged** |
| **broker account** | **700152905** (PU Prime ECN demo) | **700152905 — unchanged** |
| symbol | `XAUUSD.p` | `XAUUSD.p` — unchanged |

## The join key is the magic number, not the name

🔴 **A record and a broker deal are matched by MAGIC NUMBER — an integer, and it did not move.**
That is what makes this rename lossless for any study joining these records to a broker statement.
The bot key appears in an order's COMMENT string (`<key>-ENTRY`, `-LIMIT`, `-CLOSE-<reason>`), so
deals placed before this date carry the old prefix at the broker for ever and cannot be changed.
**Nothing reads that string back** — reconciliation has always been by magic — so the mixed prefixes
in the deal history are cosmetic. Join on magic `770115` and account `700152905` and no trade is
lost or double-counted across the boundary.

## The old name inside the old records is CORRECT and was deliberately not edited

Every one of the 2,781 decision rows written before this date carries `"bot": "mpc_sos_fade_demo"`.
**Not one byte of any record was rewritten.** That stamp is a true statement about what the bot was
called on the day it wrote the line, and a record of what a bot decided is not a document to be
tidied. ⚠ **Nothing in this repo filters on that field** — records are found by PATH
(`<archive>/<bot>/ledger/<stream>-<date>.jsonl`), which is why the folder had to be renamed and the
contents did not.

⚠ **The day of the rename legitimately contains BOTH stamps in one file** — rows written before the
restart say the old name and rows after say the new one. That is not corruption.

⚠ **The `.log` filenames in this folder still carry the old key**, for the same reason. Both readers
of them glob `*.log` rather than the bot's name (`algos/tools/log_backup.py`), so nothing is missed
by leaving them as they were written.

## What is in here

`ledger/decisions-*.jsonl` — 28 days from **2026-07-31**, and it is the ONLY record of what this bot
REFUSED: 292 blocked setups and 280 missed ones that appear in no broker statement anywhere.
`ledger/health-*.jsonl` — the process's own record, through 2026-09-03. The dated `.log` files are
the human-readable log for the same days.

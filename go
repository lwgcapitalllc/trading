#!/usr/bin/env bash
#
# One command to set up and launch the Command Center.
#
#   ./go
#
# Safe to run every time. Everything below checks first and skips if already done,
# so the second run is just the launch.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$ROOT/command-center/backend/config.json"
SSH_CONFIG="$HOME/.ssh/config"
SSH_KEY="$HOME/.ssh/forexvps"

say()  { printf '  %s\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
command -v python3 >/dev/null || { echo "python3 not found. Install Xcode command line tools."; exit 1; }
command -v node    >/dev/null || { echo "node not found. Run: brew install node"; exit 1; }
ok "python3 $(python3 --version | cut -d' ' -f2), node $(node --version)"

# ── 2. config.json points at THIS clone ───────────────────────────────────────
# The file is tracked and ships with the first machine's paths. Rewrite the
# absolute paths to this clone, then hide the change from git so it never shows
# up in git status or collides on a pull.
if grep -q "\"monorepo_root\": \"$ROOT\"" "$CONFIG" 2>/dev/null; then
  ok "config.json points at $ROOT"
else
  python3 - "$CONFIG" "$ROOT" <<'PY'
import json, sys
path, root = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
cfg["monorepo_root"]            = root
cfg["smart_money_root"]         = f"{root}/smart-money"
cfg["smart_money_config_path"]  = f"{root}/smart-money/config/config.json"
cfg["smart_money_reports_dir"]  = f"{root}/smart-money/reports"
cfg["instances_dir"]            = f"{root}/algos/markets/fx/instances"
json.dump(cfg, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY
  ok "config.json rewritten for $ROOT"
fi

if [ "$(git -C "$ROOT" ls-files -v "$CONFIG" | cut -c1)" != "S" ]; then
  git -C "$ROOT" update-index --skip-worktree "$CONFIG"
  ok "config.json hidden from git (--skip-worktree)"
fi

# ── 3. Git hooks ──────────────────────────────────────────────────────────────
# .git/hooks is not tracked, so a hook written on one machine does not exist on
# the other — which is the failure the hook itself is about. The installer points
# git at the tracked .githooks/ folder; it is the single place that logic lives,
# and it also runs from the post-merge hook, conftest.py and Claude Code.
HOOKS_OUT="$("$ROOT/scripts/install_hooks.sh" --quiet 2>&1 || true)"
if [ -z "$HOOKS_OUT" ]; then
  ok "git hooks installed (.githooks)"
else
  printf '%s\n' "$HOOKS_OUT"
fi

# ── 3b. The tools those hooks need ────────────────────────────────────────────
# `pre-commit` formats and lints the files in a commit, and it REFUSES rather than skipping
# when ruff / lint-staged are absent — so a clone that has the hooks and not the tools would
# be unable to commit at all. Installing them here is what keeps the two in step. Silent when
# nothing needs doing; the `|| true` is so a missing npm warns instead of killing `./go` under
# `set -e` (the app itself does not need any of this to run).
TOOLS_OUT="$("$ROOT/scripts/install_dev_tools.sh" --quiet 2>&1 || true)"
if [ -z "$TOOLS_OUT" ]; then
  ok "dev tools installed (ruff, prettier, eslint, lint-staged)"
else
  printf '%s\n' "$TOOLS_OUT"
fi

# ── 4. Directories the app writes into ────────────────────────────────────────
mkdir -p "$ROOT/command-center/backend/data" \
         "$ROOT/command-center/backend/reports/lab" \
         "$ROOT/backtest/cache" \
         "$ROOT/engines/news/data"

# ── 5. SSH to the VPS ─────────────────────────────────────────────────────────
# Needed for NinjaTrader/MT5 backtests, pulling bar history, and the health dots.
# Asks for the IP once, writes the host block, and never asks again.
if grep -qE '^\s*Host\s+.*\bforexvps\b' "$SSH_CONFIG" 2>/dev/null; then
  ok "ssh host 'forexvps' configured"
else
  echo ""
  warn "No ssh host 'forexvps' yet. Setting it up."
  echo ""
  printf "  VPS IP address (blank to skip for now): "
  read -r VPS_IP || VPS_IP=""   # || so a non-interactive run (no tty) skips instead of dying under set -e
  if [ -n "$VPS_IP" ]; then
    mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
    if [ ! -f "$SSH_KEY" ]; then
      ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "$(whoami)-$(hostname -s)" >/dev/null
      ok "created key $SSH_KEY"
    fi
    # 127.0.0.1, never 'localhost' — the VPS resolves localhost to ::1 and the
    # agents bind IPv4 only, so a localhost tunnel looks healthy and forwards
    # nowhere.
    cat >> "$SSH_CONFIG" <<EOF

Host forexvps
    HostName $VPS_IP
    User trader
    Port 22
    IdentityFile $SSH_KEY
    LocalForward 8765 127.0.0.1:8765
    LocalForward 8766 127.0.0.1:8766
EOF
    chmod 600 "$SSH_CONFIG"
    ok "wrote host block for $VPS_IP"
    echo ""
    warn "Send this public key to whoever administers the VPS."
    warn "It must be appended to authorized_keys for the 'trader' user."
    echo ""
    cat "$SSH_KEY.pub"
    echo ""
    say "Until then the SSH / NT8 / MT5 dots stay red. The app still runs."
    echo ""
  else
    say "Skipped. Re-run ./go later to set it up."
  fi
fi

# ── 6. Economic calendar ──────────────────────────────────────────────────────
# This used to check that the file EXISTS, which is the wrong question and was quietly wrong for
# a month: the file has been there since July while the calendar inside it stopped at 31 July, so
# every launch reported it fine and the backend's own startup banner was the only thing that ever
# noticed. What the news filter reads is COVERAGE, and nothing on this machine was topping it up.
#
# So top it up here. `--if-stale` answers "has coverage fallen behind" from the cache alone, with
# no network at all, so a launch pays nothing on the days there is nothing to do — which is most
# of them, since a fetched month covers the whole month. When it does run it fetches only the
# months that are missing (measured 2026-09-01: ~2s for one month).
CAL_PY="$ROOT/command-center/backend/.venv/bin/python"
if [ ! -x "$CAL_PY" ]; then
  # start.sh below builds this venv on a first run, so there is nothing to do yet and this is
  # not a warning — the next ./go tops the calendar up.
  say "news calendar: skipped until the backend venv exists (start.sh builds it on this run)"
elif [ ! -s "$ROOT/engines/news/data/events.json" ]; then
  warn "No news calendar. The News filter will report no coverage."
  say  "Fill it once (needs internet, not the VPS):"
  say  "  command-center/backend/.venv/bin/python engines/news/tools/backfill.py --from 2021-01"
else
  # Never fatal. A calendar that could not be topped up leaves the app entirely usable on the
  # coverage it already has, and killing the launcher over it would be the worse trade — but it
  # must SAY so, because stale coverage and a working filter look identical from the outside.
  #
  # Worked / did not work is read from the EXIT CODE, never from the message. The first version
  # of this grepped stdout for "nothing to top up" and the tool's REFUSAL on an empty cache
  # contains that phrase — so a machine with no calendar at all was told its calendar was
  # current. Same shape as every other lesson here: a failure and a success must never arrive as
  # the same value. Inside the success branch the wording only picks which good news to print.
  if CAL_OUT="$("$CAL_PY" "$ROOT/engines/news/tools/backfill.py" --top-up --if-stale 2>&1)"; then
    if printf '%s' "$CAL_OUT" | grep -q 'nothing to fetch'; then
      ok "news calendar current"
    else
      ok "news calendar topped up"
      printf '%s\n' "$CAL_OUT" | sed 's/^/    /'
    fi
  else
    warn "news calendar could NOT be topped up - the filter still runs, on coverage that stops early"
    printf '%s\n' "$CAL_OUT" | sed 's/^/    /'
  fi
fi

# ── 7. Open the browser once the frontend is actually up ──────────────────────
(
  for _ in $(seq 1 90); do
    if lsof -ti:5173 >/dev/null 2>&1; then
      sleep 1
      open http://localhost:5173
      exit 0
    fi
    sleep 1
  done
) &

# ── 8. Launch ─────────────────────────────────────────────────────────────────
# start.sh creates the venv on first run, installs backend requirements, runs
# npm install, opens the tunnels, and starts both servers. Ctrl-C stops it all.
exec "$ROOT/command-center/start.sh"

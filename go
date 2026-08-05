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
# the other — which is the failure the hook itself is about. Point git at the
# tracked .githooks/ folder instead, on every machine, every run.
if [ "$(git -C "$ROOT" config core.hooksPath)" = ".githooks" ]; then
  ok "git hooks installed (.githooks)"
else
  git -C "$ROOT" config core.hooksPath .githooks
  chmod +x "$ROOT"/.githooks/* 2>/dev/null || true
  ok "git hooks installed - commits now require the matching CLAUDE.md"
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
if [ -s "$ROOT/engines/news/data/events.json" ]; then
  ok "news calendar present"
else
  warn "No news calendar. The News filter will report no coverage."
  say  "Backfill it any time (needs internet, not the VPS):"
  say  "  command-center/backend/.venv/bin/python engines/news/tools/backfill.py --from 2021-01"
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

#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LWG Capital Command Center"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Clear any leftover processes on our ports
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

# ── Persistent SSH tunnels ────────────────────────────────────────────────────
# 8765 → NT8 nt8_agent   (LocalForward also in ~/.ssh/config — compatible)
# 8766 → MT5 mt5_agent   (explicit -L here; add to ~/.ssh/config if needed)
# Kill any stale tunnel from a previous run, then open a fresh one.
pkill -f "ssh -N.*forexvps" 2>/dev/null || true
ssh -N \
  -L 8765:localhost:8765 \
  -L 8766:localhost:8766 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  forexvps &
TUNNEL_PID=$!

# --- Backend ---
cd "$SCRIPT_DIR/backend"
if [ ! -d ".venv" ]; then
  echo "Creating Python venv..."
  python3 -m venv .venv
  source .venv/bin/activate
  python3 -m pip install -q --upgrade pip
else
  source .venv/bin/activate
fi
python3 -m pip install -q --disable-pip-version-check -r requirements.txt

echo ""
echo "  Backend  →  http://localhost:8000"
echo "  Frontend →  http://localhost:5173"
echo "  Tunnel   →  localhost:8765 → VPS:8765 (nt8 agent)"
echo "  Tunnel   →  localhost:8766 → VPS:8766 (mt5 agent)"
echo ""

uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# --- Frontend ---
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

npm run dev &
FRONTEND_PID=$!

# Trap ctrl-c and kill everything
trap "kill $BACKEND_PID $FRONTEND_PID $TUNNEL_PID 2>/dev/null; exit" INT TERM

wait $BACKEND_PID $FRONTEND_PID
kill $TUNNEL_PID 2>/dev/null

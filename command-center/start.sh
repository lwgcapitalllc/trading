#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LWG Capital Command Center"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Clear any leftover processes on our ports
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

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

# Trap ctrl-c and kill both
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait $BACKEND_PID $FRONTEND_PID

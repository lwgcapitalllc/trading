# LWG Capital Command Center

Local operations interface for LWG Capital trading activity.

## Running the app

```bash
./start.sh
```

Starts both processes — creates the Python venv and runs `npm install` on first launch.

- **Backend** — FastAPI on `http://localhost:8000` (API docs at `/docs`)
- **Frontend** — Vite on `http://localhost:5173`

## Manual start

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

## Config

`backend/config.json` holds machine-specific paths. Edit this when moving the repo or changing directory layout — nothing else needs to change.

## Theme

Electric cyan accent `#00e5ff`, gold secondary `#d9a441`, indigo-black surfaces. All tokens in `frontend/tailwind.config.js`.

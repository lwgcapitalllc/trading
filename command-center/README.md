# LWG Capital Command Center

Local operations interface for all LWG Capital trading activity.

## Running the app

```bash
./start.sh
```

This starts both processes:
- **Backend** — FastAPI on `http://localhost:8000`
- **Frontend** — Vite on `http://localhost:5173`

## Manual start (two terminals)

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

## Design reference

`../../ui/` contains the interactive prototype (`prototype.html`) and design tokens (`tokens.css`).
Open `prototype.html` in a browser to see the target UI for every screen.

## Config

`backend/config.json` holds all machine-specific paths. Edit this file when moving the monorepo
or renaming directories — nothing else needs to change.

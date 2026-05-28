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

`design/prototype.html` is the interactive visual spec — open in any browser, no build step.
`design/README.md` has the theme reference (electric cyan accent `#00e5ff`, gold secondary).

## Config

`backend/config.json` holds all machine-specific paths. Edit this file when moving the monorepo
or renaming directories — nothing else needs to change.

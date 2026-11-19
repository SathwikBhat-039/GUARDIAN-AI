# Guardian AI

Guardian AI is a video-monitoring prototype with a FastAPI backend and a React/Vite dashboard. The backend processes video with a trained model and can display nearby emergency services.

## Requirements

- Python and pip
- Node.js and npm
- A trained model checkpoint at `runs_ucf/best_model.pth`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

cd avtar-frontend
npm install
```

The model checkpoint and video/data files are not included in the repository. Place the checkpoint at `runs_ucf/best_model.pth` before starting the backend. Optional `PUSHBULLET_API_KEY` and `ABSTRACTAPI_KEY` values can be configured locally if those integrations are needed; do not commit credentials.

## Run

Start the backend from the repository root:

```powershell
python server.py
```

In another terminal opened at the repository root, start the frontend:

```powershell
cd avtar-frontend
npm run dev
```

The Vite frontend is normally available at `http://localhost:5173`, and the API at `http://localhost:8000`.

## Project layout

- `server.py` and `detect.py` - API and video-analysis service
- `avtar-frontend/` - web dashboard
- `runs_ucf/` - local model checkpoint directory (not tracked)

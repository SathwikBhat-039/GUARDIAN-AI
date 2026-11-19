# Guardian AI

Guardian AI is integrated into this repository as a separate surveillance companion service.

## Start

```powershell
cd guardian-ai
python -m pip install -r requirements.txt
cd avtar-frontend
npm install
npm run dev
```

In a second terminal:

```powershell
cd guardian-ai
python server.py
```

The frontend is available from Vite (normally at `http://localhost:5173`) and the API at `http://localhost:8000`.

Place the trained checkpoint at `runs_ucf/best_model.pth`. Set `PUSHBULLET_API_KEY` and `ABSTRACTAPI_KEY` only if those optional integrations are required.

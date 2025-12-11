# Image Search Project

Local image search app (frontend + backend) that returns square thumbnails and lets you download page results as ZIP.

Current status
- Backend: FastAPI (`backend/main.py`) - switched from Unsplash to Wikimedia Commons for free image search.
- Frontend: Vue 3 (Vite) - `frontend/src/components/ImageGrid.vue`, now creates ZIP client-side using JSZip to avoid robot restrictions.
- Search is triggered by the "Найти" button (no automatic search while typing).

Planned improvements
- Add Openverse + Flickr integration to improve search quality for Cyrillic and multi-word queries.

Local setup
1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

2. Frontend

```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

Environment variables
- (optional) `FLICKR_API_KEY` — API key for Flickr (if you choose to enable Flickr integration).
- Previously used `UNSPLASH_ACCESS_KEY` is no longer required; if present in `backend/.env`, remove it or rotate the key if it was committed publicly.

Notes
- The repo `.gitignore` ensures `backend/.env` is ignored. If `backend/.env` was committed earlier, do not push the repo to a remote until you've removed secrets from history.

Next steps
- Implement Openverse + Flickr search in the backend (I can do this next).
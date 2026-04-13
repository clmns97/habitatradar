# HabitatRadar

HabitatRadar is a map-based web app that shows nearby protected areas.

- Frontend: SvelteKit, Vite, Tailwind CSS, DaisyUI, MapLibre GL
- Backend: FastAPI with PostGIS-style spatial queries via PostgreSQL
- Hosting: GitHub Pages (frontend) + Google Cloud Run (backend)

## Live URLs

- Frontend: `https://clmns97.github.io/habitatradar/`
- Backend health: `https://habitatradar-backend-y52b3fsrya-ew.a.run.app/health`

## Project structure

- `src/`: SvelteKit frontend
- `static/`: static assets
- `backend/`: FastAPI app, Dockerfile, Python dependencies
- `.github/workflows/deploy-frontend.yml`: deploy frontend to GitHub Pages
- `.github/workflows/deploy-backend.yml`: deploy backend to Cloud Run

## Local development

### Prerequisites

- Bun
- Python 3.11+
- Docker (for backend containerized run)

### Frontend

```bash
bun install
cp .env.example .env
bun run dev
```

Set `VITE_API_URL` in `.env` to your backend URL, for example:

```bash
VITE_API_URL="http://localhost:8000"
```

### Backend

```bash
cp backend/.env.example backend/.env
docker-compose up --build
```

Backend runs on `http://localhost:8000`.

## Useful commands

```bash
bun run check
bun run build
python3 -m compileall backend
```

## API

- `GET /health`: health endpoint
- `POST /api/nearest-protected-areas`: returns nearby protected areas as GeoJSON

Example request:

```json
{
  "geojson": {
    "type": "Point",
    "coordinates": [13.405, 52.52]
  },
  "radius_km": 10
}
```

## Deployment

### Frontend (GitHub Pages)

The frontend workflow uses `VITE_API_URL` during build and publishes the `build/` output as a Pages artifact.

Required GitHub Actions secret:

- `VITE_API_URL`

### Backend (Google Cloud Run)

The backend workflow deploys from source using `gcloud run deploy --source backend`.

Required GitHub Actions secrets:

- `GCP_CREDENTIALS_JSON`
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `CLOUD_RUN_SERVICE`
- `FRONTEND_ORIGIN`
- `DATABASE_URL`

Service account typically needs these IAM roles on the project:

- `roles/run.admin`
- `roles/iam.serviceAccountUser`
- `roles/storage.admin`
- `roles/artifactregistry.admin`
- `roles/cloudbuild.builds.editor`

Required Google Cloud APIs:

- `run.googleapis.com`
- `artifactregistry.googleapis.com`
- `cloudbuild.googleapis.com`

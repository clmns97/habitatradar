# HabitatRadar

HabitatRadar is a map-based web app that shows nearby protected areas.

- Frontend: SvelteKit, Vite, Tailwind CSS, DaisyUI, MapLibre GL
- Backend: FastAPI with PostGIS-style spatial queries via PostgreSQL
- Hosting: GitHub Pages (frontend) + Google Cloud Run (backend)

## Live URLs

- Frontend: `https://REDACTED_ORIGIN/habitatradar/`
- Backend health: `https://REDACTED_HOST/health`

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

## Data refresh (ETL)

Protected-area tables are loaded from the [BfN WFS service](https://geodienste.bfn.de/ogc/wfs/schutzgebiet)
by `backend/etl/refresh_wfs.py` and refreshed automatically by
`.github/workflows/etl.yml`, which runs every Sunday at 03:00 UTC (and can be
triggered manually via *workflow_dispatch*).

For each of the nine layers the job loads the data into a staging table with
`ogr2ogr` (reprojected to EPSG:3035, geometry column `geom`, FID column `id`),
verifies it received rows, then atomically swaps it into the live table — so the
API keeps serving the previous data until the swap commits.

Required GitHub Actions secret:

- `IMPORT_DATABASE_URL` — Postgres connection URL for the write/ETL role. Use a
  **direct** (non-pooled) Neon endpoint; a `-pooler` host is stripped
  automatically.

Optional:

- `WFS_URL` — overrides the default BfN WFS endpoint.

Run it locally against your own database:

```bash
pip install -r backend/etl/requirements.txt   # plus system gdal-bin for ogr2ogr
IMPORT_DATABASE_URL="postgresql://user:pass@host/db" python backend/etl/refresh_wfs.py
```

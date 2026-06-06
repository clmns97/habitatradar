# HabitatRadar

HabitatRadar is a map-based web app that shows nearby protected areas.

- Frontend: SvelteKit, Vite, Tailwind CSS, DaisyUI, MapLibre GL
- Backend: FastAPI with PostGIS spatial queries via PostgreSQL/PostGIS
- Hosting: GitHub Pages (frontend) + a self-hosted server (backend + DB)

## Architecture

- The **frontend** is a static SvelteKit build published to GitHub Pages.
- The **backend** (FastAPI) runs on a self-hosted server behind Caddy (HTTPS),
  defined in `deploy/docker-compose.yml`. It talks to a shared PostGIS database
  over a private Docker network using a read-only role.
- A small **Cloudflare Worker** (`deploy/cloudflare-worker/`) reverse-proxies the
  public API URL to the backend, so the origin host is never referenced by the
  frontend. Its config lives in Worker secrets, not in this repo.
- The **ETL** (`backend/etl/refresh_wfs.py`) refreshes protected-area tables from
  the BfN WFS and runs in GitHub Actions, reaching the database over Tailscale.

## Project structure

- `src/`: SvelteKit frontend
- `static/`: static assets
- `backend/`: FastAPI app, Dockerfile, Python dependencies
- `backend/etl/`: WFS loader + its Docker image
- `deploy/`: server compose stack, Caddyfile, Cloudflare Worker
- `.github/workflows/deploy-frontend.yml`: deploy frontend to GitHub Pages
- `.github/workflows/etl.yml`: scheduled data refresh

## Local development

### Prerequisites

- Bun
- Python 3.11+
- Docker (for backend containerized run)

### Frontend

```bash
bun install
cp .env.example .env   # set VITE_API_URL to your backend/API URL
bun run dev
```

### Backend

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Backend runs on `http://localhost:8000`.

## Useful commands

```bash
bun run check
bun run build
bun run test
python3 -m compileall backend
```

## API

- `GET /health`: health endpoint
- `POST /api/nearest-protected-areas`: returns nearby protected areas as GeoJSON

Example request:

```json
{
  "geojson": { "type": "Point", "coordinates": [13.405, 52.52] },
  "radius_km": 10
}
```

## Deployment

### Frontend (GitHub Pages)

The frontend workflow uses `VITE_API_URL` during build and publishes `build/` as a
Pages artifact. Required secret: `VITE_API_URL`.

### Backend (self-hosted)

Copy `deploy/.env.example` to `deploy/.env` on the server, fill in the values, then:

```bash
cd deploy && docker compose up -d --build
```

### Cloudflare Worker (API proxy)

```bash
cd deploy/cloudflare-worker
npx wrangler secret put BACKEND          # origin base URL
npx wrangler secret put ALLOWED_ORIGIN   # frontend origin
npx wrangler deploy
```

## Data refresh (ETL)

Protected-area tables are loaded from the
[BfN WFS service](https://geodienste.bfn.de/ogc/wfs/schutzgebiet) by
`backend/etl/refresh_wfs.py`, refreshed by `.github/workflows/etl.yml` every
Sunday at 03:00 UTC (and on demand via *workflow_dispatch*). The runner joins the
tailnet to reach the database. For each layer the job loads into a staging table
with `ogr2ogr` (EPSG:3035, geometry column `geom`), verifies rows, then atomically
swaps it into the live table — so the API keeps serving the previous data until
the swap commits.

Secrets: `IMPORT_DATABASE_URL` (write-role DSN), `TS_OAUTH_CLIENT_ID` /
`TS_OAUTH_SECRET` (Tailscale), optional `WFS_URL`.

Run it locally against your own database:

```bash
pip install -r backend/etl/requirements.txt   # plus system gdal-bin for ogr2ogr
IMPORT_DATABASE_URL="postgresql://user:pass@host/db" python backend/etl/refresh_wfs.py
```

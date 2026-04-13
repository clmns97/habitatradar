# HabitatRadar

HabitatRadar is split into a static SvelteKit frontend and a FastAPI backend.

## Architecture

- Frontend: SvelteKit + Bun + Tailwind + DaisyUI + Vite
- Frontend hosting: GitHub Pages (static build)
- Backend: FastAPI (Python)
- Backend hosting: Google Cloud Run

React and Drizzle are not used in this repository.

## Local development

### Frontend

```bash
bun install
cp .env.example .env
bun run dev
```

`VITE_API_URL` in `.env` should point to your backend URL.

### Backend

```bash
cp backend/.env.example backend/.env
docker-compose up --build
```

Backend runs on `http://localhost:8000`.

## Build checks

```bash
bun run check
bun run build
python3 -m compileall backend
```

## Deployment workflows

- `deploy-frontend.yml`: builds and deploys static frontend to GitHub Pages
- `deploy-backend.yml`: deploys FastAPI backend to Google Cloud Run

## Required GitHub secrets

Frontend workflow:

- `VITE_API_URL`

Backend workflow:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `CLOUD_RUN_SERVICE`
- `FRONTEND_ORIGIN`

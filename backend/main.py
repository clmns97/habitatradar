import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import HealthResponse, ProtectedAreasRequest
from app.services import find_nearest_protected_areas, warm_table_cache


load_dotenv()

app = FastAPI(title="HabitatRadar Backend", version="0.1.0")


@app.on_event("startup")
async def startup_event() -> None:
    await warm_table_cache()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "https://clmns97.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="habitatradar-backend")


@app.post("/api/nearest-protected-areas")
async def nearest_protected_areas(payload: ProtectedAreasRequest):
    if "type" not in payload.geojson:
        raise HTTPException(status_code=400, detail="Invalid GeoJSON: missing 'type'")
    try:
        return await find_nearest_protected_areas(
            payload.geojson, payload.radius_km or 10.0
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

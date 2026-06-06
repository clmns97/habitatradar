from typing import Any, Dict, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class ProtectedAreasRequest(BaseModel):
    geojson: Dict[str, Any]
    radius_km: Optional[float] = 10.0


class TransformGeoJSONRequest(BaseModel):
    geojson: Dict[str, Any]
    source_crs: Optional[str] = None

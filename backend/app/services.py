import asyncio
import json
import logging
from typing import Any, Dict

from sqlalchemy import text

from app.db import AsyncSessionLocal


logger = logging.getLogger("habitatradar_backend")


PROTECTED_AREA_TYPES = [
    ("nationalparke", "National Parks"),
    ("naturparke", "Nature Parks"),
    ("naturschutzgebiete", "Nature Reserves"),
    ("landschaftsschutzgebiete", "Landscape Protection Areas"),
    ("biosphaerenreservate", "Biosphere Reserves"),
    ("vogelschutzgebiete", "Bird Protection Areas"),
    ("fauna_flora_habitat_gebiete", "Fauna-Flora-Habitat Areas"),
    ("nationale_naturmonumente", "National Natural Monuments"),
    ("biosphaerenreservate_zonierung", "Biosphere Reserve Zoning"),
]

# Tables confirmed to exist at startup — avoids per-request information_schema checks.
_existing_tables: set[str] = set()


async def warm_table_cache() -> None:
    """Check which tables exist once at startup using pg_catalog (fast)."""
    global _existing_tables
    table_names = [t for t, _ in PROTECTED_AREA_TYPES]
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public' AND tablename = ANY(:names)"
            ),
            {"names": table_names},
        )
        _existing_tables = {row[0] for row in result.fetchall()}
    logger.info("Table cache warmed: %s", _existing_tables)


def extract_geometry(geojson_data: Dict[str, Any]) -> Dict[str, Any]:
    if "type" not in geojson_data:
        raise ValueError("Invalid GeoJSON: missing 'type' field")

    if geojson_data["type"] == "FeatureCollection":
        features = geojson_data.get("features", [])
        if not features:
            raise ValueError("FeatureCollection has no features")
        return features[0]["geometry"]

    if geojson_data["type"] == "Feature":
        return geojson_data["geometry"]

    return geojson_data


async def query_single_table(
    table_name: str,
    display_name: str,
    geometry_json: str,
    radius_km: float,
) -> list[Dict[str, Any]]:
    if table_name not in _existing_tables:
        return []

    radius_m = max(radius_km, 0.1) * 1000.0

    try:
        async with AsyncSessionLocal() as session:
            # Single round trip: transform input geometry inline via CTE,
            # then filter + order + limit in one query.
            result = await session.execute(
                text(
                    f"""
                    WITH input AS (
                        SELECT ST_Transform(ST_GeomFromGeoJSON(:geom), 3035) AS geom
                    )
                    SELECT
                        id,
                        name,
                        ST_AsGeoJSON(
                            ST_Transform(
                                ST_SimplifyPreserveTopology(geom, 50),
                                4326
                            )
                        ) AS geometry,
                        ST_Distance(geom, (SELECT geom FROM input)) / 1000.0 AS distance_km,
                        :area_type AS area_type
                    FROM {table_name}
                    WHERE ST_DWithin(geom, (SELECT geom FROM input), :radius_m)
                    ORDER BY geom <-> (SELECT geom FROM input)
                    LIMIT 20
                    """
                ),
                {
                    "geom": geometry_json,
                    "area_type": display_name,
                    "radius_m": radius_m,
                },
            )

            features = []
            for area in result.fetchall():
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "id": area.id,
                            "name": area.name,
                            "distance_km": round(float(area.distance_km), 2),
                            "area_type": area.area_type,
                            "table_name": table_name,
                        },
                        "geometry": json.loads(area.geometry),
                    }
                )
            return features

    except Exception as exc:
        logger.warning("Query for %s failed: %s", table_name, exc)
        return []


async def find_nearest_protected_areas(
    geojson_data: Dict[str, Any], radius_km: float
) -> Dict[str, Any]:
    geometry = extract_geometry(geojson_data)
    geometry_json = json.dumps(geometry)

    tasks = [
        query_single_table(table_name, display_name, geometry_json, radius_km)
        for table_name, display_name in PROTECTED_AREA_TYPES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_features: list[Dict[str, Any]] = []
    for result in results:
        if isinstance(result, list):
            all_features.extend(result)

    all_features.sort(key=lambda f: f["properties"]["distance_km"])

    return {
        "type": "FeatureCollection",
        "features": all_features,
        "meta": {
            "radius_km": radius_km,
            "count": len(all_features),
            "input_type": geojson_data.get("type", "unknown"),
        },
    }

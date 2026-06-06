import json
from typing import Any, Dict, Optional

from pyproj import Transformer


def detect_crs_from_geojson(geojson_data: Dict[str, Any]) -> Optional[str]:
    """Read an explicit CRS member (legacy GeoJSON / OGC urn form)."""
    crs_info = geojson_data.get("crs")
    if isinstance(crs_info, dict):
        crs_name = crs_info.get("properties", {}).get("name")
        if isinstance(crs_name, str):
            if crs_name.startswith("urn:ogc:def:crs:EPSG::"):
                epsg_code = crs_name.split("::")[-1]
                return f"EPSG:{epsg_code}"
            if "EPSG:" in crs_name:
                return crs_name
    return None


def flatten_coordinates(coord_array: Any) -> list:
    result = []
    if isinstance(coord_array, list) and len(coord_array) > 0:
        if isinstance(coord_array[0], (int, float)):
            if len(coord_array) >= 2:
                result.append((coord_array[0], coord_array[1]))
        else:
            for item in coord_array:
                result.extend(flatten_coordinates(item))
    return result


def guess_source_crs_from_coordinates(geojson_data: Dict[str, Any]) -> Optional[str]:
    """Guess the CRS from coordinate magnitudes when no CRS member is present."""
    coords: list = []

    def extract_coords(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "FeatureCollection":
                for feature in obj.get("features", []):
                    extract_coords(feature)
            elif obj.get("type") == "Feature":
                extract_coords(obj.get("geometry", {}))
            elif "coordinates" in obj:
                coords.extend(flatten_coordinates(obj["coordinates"]))

    extract_coords(geojson_data)

    if not coords:
        return None

    sample = coords[:10]
    x_coords = [c[0] for c in sample]
    y_coords = [c[1] for c in sample]

    # EPSG:3035 (ETRS89-LAEA, metres) — the CRS our data is stored in.
    if (
        min(x_coords) > 1_000_000
        and max(x_coords) < 8_000_000
        and min(y_coords) > 1_000_000
        and max(y_coords) < 6_000_000
    ):
        return "EPSG:3035"

    # WGS84 degrees.
    if (
        min(x_coords) >= -180
        and max(x_coords) <= 180
        and min(y_coords) >= -90
        and max(y_coords) <= 90
    ):
        return "EPSG:4326"

    return None


def transform_geojson_coordinates(
    geojson_data: Dict[str, Any], source_crs: str, target_crs: str = "EPSG:4326"
) -> Dict[str, Any]:
    """Reproject every coordinate of a GeoJSON object from source to target CRS."""
    if source_crs == target_crs:
        return geojson_data

    try:
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

        def transform_coordinates(coords: Any) -> Any:
            if not coords:
                return coords
            if isinstance(coords[0], (int, float)):
                if len(coords) >= 2:
                    x, y = transformer.transform(coords[0], coords[1])
                    return [x, y] + list(coords[2:])
                return coords
            return [transform_coordinates(coord) for coord in coords]

        def transform_geometry(geometry: Any) -> Any:
            if not geometry or "coordinates" not in geometry:
                return geometry
            transformed = dict(geometry)
            transformed["coordinates"] = transform_coordinates(geometry["coordinates"])
            return transformed

        result = json.loads(json.dumps(geojson_data))

        if result.get("type") == "FeatureCollection":
            for feature in result.get("features", []):
                if feature.get("geometry"):
                    feature["geometry"] = transform_geometry(feature["geometry"])
        elif result.get("type") == "Feature":
            if result.get("geometry"):
                result["geometry"] = transform_geometry(result["geometry"])
        else:
            result = transform_geometry(result)

        result["crs"] = {"type": "name", "properties": {"name": target_crs}}
        return result

    except Exception as exc:
        raise ValueError(
            f"Failed to transform coordinates from {source_crs} to {target_crs}: {exc}"
        ) from exc


def transform_to_wgs84(
    geojson_data: Dict[str, Any], source_crs: Optional[str] = None
) -> Dict[str, Any]:
    """Detect (or accept) the source CRS and return the GeoJSON reprojected to WGS84.

    Returns a dict with the transformed GeoJSON plus metadata describing what was done.
    """
    if "type" not in geojson_data:
        raise ValueError("Invalid GeoJSON: missing 'type' field")

    if not source_crs:
        source_crs = detect_crs_from_geojson(geojson_data)

    if not source_crs:
        source_crs = guess_source_crs_from_coordinates(geojson_data)

    if not source_crs:
        raise ValueError(
            "Could not detect CRS. Please specify source_crs (e.g. 'EPSG:3035')."
        )

    if source_crs == "EPSG:4326":
        return {
            "transformed_geojson": geojson_data,
            "source_crs": "EPSG:4326",
            "target_crs": "EPSG:4326",
            "transformed": False,
        }

    transformed = transform_geojson_coordinates(geojson_data, source_crs, "EPSG:4326")
    return {
        "transformed_geojson": transformed,
        "source_crs": source_crs,
        "target_crs": "EPSG:4326",
        "transformed": True,
    }

"""Tests for the pure CRS-detection and coordinate-transform helpers."""

import pytest
from pyproj import Transformer

from app.geojson_service import (
    detect_crs_from_geojson,
    flatten_coordinates,
    guess_source_crs_from_coordinates,
    transform_geojson_coordinates,
    transform_to_wgs84,
)


class TestDetectCrsFromGeojson:
    def test_ogc_urn_form(self):
        data = {"crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::3035"}}}
        assert detect_crs_from_geojson(data) == "EPSG:3035"

    def test_plain_epsg_name(self):
        data = {"crs": {"properties": {"name": "EPSG:4326"}}}
        assert detect_crs_from_geojson(data) == "EPSG:4326"

    def test_missing_or_malformed_crs_returns_none(self):
        assert detect_crs_from_geojson({}) is None
        assert detect_crs_from_geojson({"crs": "nonsense"}) is None
        assert detect_crs_from_geojson({"crs": {"properties": {}}}) is None


class TestFlattenCoordinates:
    def test_single_position(self):
        assert flatten_coordinates([1.0, 2.0]) == [(1.0, 2.0)]

    def test_nested_polygon_ring(self):
        ring = [[[0, 0], [1, 0], [1, 1]]]
        assert flatten_coordinates(ring) == [(0, 0), (1, 0), (1, 1)]

    def test_ignores_too_short_and_empty(self):
        assert flatten_coordinates([]) == []
        assert flatten_coordinates([5]) == []


class TestGuessSourceCrsFromCoordinates:
    def test_wgs84_degrees(self):
        data = {"type": "Point", "coordinates": [10.0, 51.0]}
        assert guess_source_crs_from_coordinates(data) == "EPSG:4326"

    def test_etrs89_laea_metres(self):
        data = {"type": "Point", "coordinates": [4_321_000.0, 3_210_000.0]}
        assert guess_source_crs_from_coordinates(data) == "EPSG:3035"

    def test_no_coordinates_returns_none(self):
        assert guess_source_crs_from_coordinates({"type": "FeatureCollection", "features": []}) is None

    def test_walks_feature_collection(self):
        data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [9.0, 50.0]}}
            ],
        }
        assert guess_source_crs_from_coordinates(data) == "EPSG:4326"


class TestTransformGeojsonCoordinates:
    def test_same_crs_is_a_noop(self):
        data = {"type": "Point", "coordinates": [1, 2]}
        assert transform_geojson_coordinates(data, "EPSG:4326", "EPSG:4326") is data

    def test_round_trip_preserves_position(self):
        # Build a real EPSG:3035 coordinate from a known WGS84 point, then ask the
        # function to send it back to WGS84 — it should land where we started.
        fwd = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
        x, y = fwd.transform(10.0, 51.0)
        data = {"type": "Point", "coordinates": [x, y]}

        result = transform_geojson_coordinates(data, "EPSG:3035", "EPSG:4326")

        lon, lat = result["coordinates"]
        assert lon == pytest.approx(10.0, abs=1e-6)
        assert lat == pytest.approx(51.0, abs=1e-6)
        assert result["crs"]["properties"]["name"] == "EPSG:4326"

    def test_preserves_feature_collection_structure(self):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"keep": "me"},
                    "geometry": {"type": "Point", "coordinates": [4_321_000.0, 3_210_000.0]},
                }
            ],
        }
        result = transform_geojson_coordinates(data, "EPSG:3035", "EPSG:4326")
        assert result["type"] == "FeatureCollection"
        assert result["features"][0]["properties"] == {"keep": "me"}

    def test_does_not_mutate_input(self):
        data = {"type": "Point", "coordinates": [4_321_000.0, 3_210_000.0]}
        transform_geojson_coordinates(data, "EPSG:3035", "EPSG:4326")
        assert data["coordinates"] == [4_321_000.0, 3_210_000.0]

    def test_invalid_crs_raises_value_error(self):
        data = {"type": "Point", "coordinates": [1, 2]}
        with pytest.raises(ValueError):
            transform_geojson_coordinates(data, "EPSG:NOPE", "EPSG:4326")


class TestTransformToWgs84:
    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing 'type'"):
            transform_to_wgs84({"coordinates": [1, 2]})

    def test_wgs84_input_is_passed_through_untransformed(self):
        data = {"type": "Point", "coordinates": [10.0, 51.0]}
        result = transform_to_wgs84(data)
        assert result["transformed"] is False
        assert result["source_crs"] == "EPSG:4326"
        assert result["transformed_geojson"] is data

    def test_detects_crs_member_and_transforms(self):
        data = {
            "type": "Point",
            "coordinates": [4_321_000.0, 3_210_000.0],
            "crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::3035"}},
        }
        result = transform_to_wgs84(data)
        assert result["transformed"] is True
        assert result["source_crs"] == "EPSG:3035"

    def test_explicit_source_crs_wins(self):
        data = {"type": "Point", "coordinates": [4_321_000.0, 3_210_000.0]}
        result = transform_to_wgs84(data, source_crs="EPSG:3035")
        assert result["source_crs"] == "EPSG:3035"
        assert result["transformed"] is True

    def test_undetectable_crs_raises(self):
        # Coordinates that fit neither the WGS84 nor the EPSG:3035 envelope.
        data = {"type": "Point", "coordinates": [500.0, 500.0]}
        with pytest.raises(ValueError, match="Could not detect CRS"):
            transform_to_wgs84(data)

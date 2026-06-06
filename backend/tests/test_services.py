"""Tests for the pure helpers in app.services (no DB access)."""

import pytest

from app.services import extract_geometry

POINT = {"type": "Point", "coordinates": [10.0, 51.0]}


class TestExtractGeometry:
    def test_feature_collection_returns_first_geometry(self):
        data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": POINT},
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}},
            ],
        }
        assert extract_geometry(data) == POINT

    def test_empty_feature_collection_raises(self):
        with pytest.raises(ValueError, match="no features"):
            extract_geometry({"type": "FeatureCollection", "features": []})

    def test_feature_returns_its_geometry(self):
        assert extract_geometry({"type": "Feature", "geometry": POINT}) == POINT

    def test_bare_geometry_returned_as_is(self):
        assert extract_geometry(POINT) == POINT

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing 'type'"):
            extract_geometry({"coordinates": [1, 2]})

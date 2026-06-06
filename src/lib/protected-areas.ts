import type { Feature, FeatureCollection, GeoJsonProperties, Geometry } from 'geojson';

export type ProtectedAreaFeature = Feature<Geometry, GeoJsonProperties>;

export type ProtectedAreaResponse = FeatureCollection<Geometry, GeoJsonProperties> & {
	meta?: {
		radius_km?: number;
		count?: number;
		input_type?: string;
	};
};

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function fetchNearestProtectedAreas(
	lng: number,
	lat: number,
	radiusKm: number
): Promise<ProtectedAreaResponse> {
	return fetchNearestProtectedAreasByGeoJSON(
		{
			type: 'Point',
			coordinates: [lng, lat]
		},
		radiusKm
	);
}

export async function fetchNearestProtectedAreasByGeoJSON(
	geojson: FeatureCollection<Geometry, GeoJsonProperties> | Feature<Geometry, GeoJsonProperties> | Geometry,
	radiusKm: number
): Promise<ProtectedAreaResponse> {
	const response = await fetch(`${API_URL}/api/nearest-protected-areas`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			geojson,
			radius_km: radiusKm
		})
	});

	if (!response.ok) {
		throw new Error(`API request failed with status ${response.status}`);
	}

	return (await response.json()) as ProtectedAreaResponse;
}

export type TransformGeoJSONResult = {
	transformed_geojson: FeatureCollection<Geometry, GeoJsonProperties> | Feature<Geometry, GeoJsonProperties> | Geometry;
	source_crs: string;
	target_crs: string;
	transformed: boolean;
};

/**
 * Ask the backend to detect the CRS of an uploaded GeoJSON and reproject it to
 * WGS84 (EPSG:4326). Returns the original geometry unchanged if it is already
 * WGS84 or if the CRS can't be determined (the upload is then assumed to be WGS84).
 */
export async function transformGeoJSONToWGS84(geojson: unknown): Promise<TransformGeoJSONResult> {
	const response = await fetch(`${API_URL}/api/transform-geojson`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ geojson })
	});

	if (!response.ok) {
		throw new Error(`Transform request failed with status ${response.status}`);
	}

	return (await response.json()) as TransformGeoJSONResult;
}

export function groupByAreaType(features: ProtectedAreaFeature[]) {
	return features.reduce<Record<string, ProtectedAreaFeature[]>>((acc, feature) => {
		const areaType = String(feature.properties?.area_type || 'Other');
		if (!acc[areaType]) {
			acc[areaType] = [];
		}
		acc[areaType].push(feature);
		return acc;
	}, {});
}

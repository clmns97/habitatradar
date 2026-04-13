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
	const response = await fetch(`${API_URL}/api/nearest-protected-areas`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			geojson: {
				type: 'Point',
				coordinates: [lng, lat]
			},
			radius_km: radiusKm
		})
	});

	if (!response.ok) {
		throw new Error(`API request failed with status ${response.status}`);
	}

	return (await response.json()) as ProtectedAreaResponse;
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

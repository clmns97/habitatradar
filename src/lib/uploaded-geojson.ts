import type { Feature, FeatureCollection, GeoJsonProperties, Geometry, Position } from 'geojson';

export type UploadedFeature = {
	id: string;
	name: string;
	feature: Feature<Geometry, GeoJsonProperties>;
};

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null;
}

function getFeatureName(feature: Feature<Geometry, GeoJsonProperties>, index: number): string {
	const props = (feature.properties ?? {}) as Record<string, unknown>;
	const fallbackId = typeof feature.id === 'string' || typeof feature.id === 'number' ? String(feature.id) : null;
	return String(props.name ?? props.title ?? props.site_name ?? props.id ?? fallbackId ?? `Feature ${index + 1}`);
}

export function parseUploadedGeoJSON(input: unknown): {
	uploadedFeatures: UploadedFeature[];
	displayGeoJSON: FeatureCollection<Geometry, GeoJsonProperties>;
} {
	if (!isObject(input) || typeof input.type !== 'string') {
		throw new Error('Invalid JSON: expected a GeoJSON object with a type');
	}

	let featureList: Feature<Geometry, GeoJsonProperties>[] = [];
	const geojson = input as Record<string, unknown>;

	if (geojson.type === 'FeatureCollection' && Array.isArray(geojson.features)) {
		featureList = geojson.features as Feature<Geometry, GeoJsonProperties>[];
	} else if (geojson.type === 'Feature') {
		featureList = [geojson as unknown as Feature<Geometry, GeoJsonProperties>];
	} else if ('coordinates' in geojson) {
		featureList = [
			{ type: 'Feature', properties: {}, geometry: geojson as unknown as Geometry }
		];
	} else {
		throw new Error('File must be a GeoJSON FeatureCollection, Feature, or Geometry');
	}

	const normalized = featureList
		.filter((feature) => feature && feature.geometry)
		.map((feature, index) => {
			const id = String(feature.id ?? `upload-${index + 1}`);
			const name = getFeatureName(feature, index);
			return { id, name, feature };
		});

	if (normalized.length === 0) {
		throw new Error('No valid GeoJSON features with geometry found');
	}

	const displayGeoJSON: FeatureCollection<Geometry, GeoJsonProperties> = {
		type: 'FeatureCollection',
		features: normalized.map(({ id, name, feature }) => ({
			type: 'Feature',
			id: feature.id,
			properties: { ...(feature.properties ?? {}), __upload_id: id, __upload_name: name },
			geometry: feature.geometry
		}))
	};

	return { uploadedFeatures: normalized, displayGeoJSON };
}

export function forEachPosition(geometry: Geometry, callback: (position: Position) => void): void {
	if (geometry.type === 'Point') {
		callback(geometry.coordinates);
		return;
	}

	if (geometry.type === 'MultiPoint' || geometry.type === 'LineString') {
		for (const position of geometry.coordinates) callback(position);
		return;
	}

	if (geometry.type === 'MultiLineString' || geometry.type === 'Polygon') {
		for (const line of geometry.coordinates) {
			for (const position of line) callback(position);
		}
		return;
	}

	if (geometry.type === 'MultiPolygon') {
		for (const polygon of geometry.coordinates) {
			for (const ring of polygon) {
				for (const position of ring) callback(position);
			}
		}
	}
}

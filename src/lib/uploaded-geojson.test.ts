import type { Geometry } from 'geojson';
import { describe, expect, it } from 'vitest';
import { forEachPosition, parseUploadedGeoJSON } from './uploaded-geojson';

const point = (lng: number, lat: number): Geometry => ({ type: 'Point', coordinates: [lng, lat] });

describe('parseUploadedGeoJSON — input shapes', () => {
	it('parses a FeatureCollection', () => {
		const { uploadedFeatures, displayGeoJSON } = parseUploadedGeoJSON({
			type: 'FeatureCollection',
			features: [{ type: 'Feature', properties: { name: 'A' }, geometry: point(8, 48) }]
		});
		expect(uploadedFeatures).toHaveLength(1);
		expect(uploadedFeatures[0].name).toBe('A');
		expect(displayGeoJSON.type).toBe('FeatureCollection');
		expect(displayGeoJSON.features).toHaveLength(1);
	});

	it('parses a bare Feature', () => {
		const { uploadedFeatures } = parseUploadedGeoJSON({
			type: 'Feature',
			properties: { name: 'Solo' },
			geometry: point(8, 48)
		});
		expect(uploadedFeatures).toHaveLength(1);
		expect(uploadedFeatures[0].name).toBe('Solo');
	});

	it('wraps a bare Geometry into a feature', () => {
		const { uploadedFeatures } = parseUploadedGeoJSON(point(8, 48));
		expect(uploadedFeatures).toHaveLength(1);
		expect(uploadedFeatures[0].feature.geometry.type).toBe('Point');
	});
});

describe('parseUploadedGeoJSON — naming & ids', () => {
	it('resolves names by priority: name > title > site_name > id > feature.id > fallback', () => {
		const mk = (properties: Record<string, unknown>, id?: string | number) =>
			parseUploadedGeoJSON({ type: 'Feature', id, properties, geometry: point(0, 0) })
				.uploadedFeatures[0].name;

		expect(mk({ name: 'n', title: 't' })).toBe('n');
		expect(mk({ title: 't', site_name: 's' })).toBe('t');
		expect(mk({ site_name: 's', id: 'pid' })).toBe('s');
		expect(mk({ id: 'pid' })).toBe('pid');
		expect(mk({}, 'fid-7')).toBe('fid-7');
		expect(mk({})).toBe('Feature 1');
	});

	it('uses feature.id for the upload id, falling back to an index', () => {
		const { uploadedFeatures } = parseUploadedGeoJSON({
			type: 'FeatureCollection',
			features: [
				{ type: 'Feature', id: 'has-id', properties: {}, geometry: point(0, 0) },
				{ type: 'Feature', properties: {}, geometry: point(1, 1) }
			]
		});
		expect(uploadedFeatures[0].id).toBe('has-id');
		expect(uploadedFeatures[1].id).toBe('upload-2');
	});

	it('stamps __upload_id and __upload_name into displayGeoJSON properties', () => {
		const { displayGeoJSON } = parseUploadedGeoJSON({
			type: 'Feature',
			id: 'x1',
			properties: { name: 'Park' },
			geometry: point(0, 0)
		});
		const props = displayGeoJSON.features[0].properties!;
		expect(props.__upload_id).toBe('x1');
		expect(props.__upload_name).toBe('Park');
		expect(props.name).toBe('Park');
	});
});

describe('parseUploadedGeoJSON — invalid input', () => {
	it('rejects non-objects and objects without a type', () => {
		expect(() => parseUploadedGeoJSON(null)).toThrow(/GeoJSON/);
		expect(() => parseUploadedGeoJSON('nope')).toThrow(/GeoJSON/);
		expect(() => parseUploadedGeoJSON({})).toThrow(/type/);
	});

	it('rejects an unknown type with no coordinates', () => {
		expect(() => parseUploadedGeoJSON({ type: 'Banana' })).toThrow(/FeatureCollection, Feature, or Geometry/);
	});

	it('throws when no feature has a geometry', () => {
		expect(() =>
			parseUploadedGeoJSON({
				type: 'FeatureCollection',
				features: [{ type: 'Feature', properties: {}, geometry: null }]
			})
		).toThrow(/No valid GeoJSON features/);
	});

	it('drops geometry-less features but keeps the valid ones', () => {
		const { uploadedFeatures } = parseUploadedGeoJSON({
			type: 'FeatureCollection',
			features: [
				{ type: 'Feature', properties: { name: 'bad' }, geometry: null },
				{ type: 'Feature', properties: { name: 'good' }, geometry: point(0, 0) }
			]
		});
		expect(uploadedFeatures).toHaveLength(1);
		expect(uploadedFeatures[0].name).toBe('good');
	});
});

describe('forEachPosition', () => {
	const collect = (geometry: Geometry): number[][] => {
		const out: number[][] = [];
		forEachPosition(geometry, (p) => out.push(p));
		return out;
	};

	it('Point yields one position', () => {
		expect(collect({ type: 'Point', coordinates: [1, 2] })).toEqual([[1, 2]]);
	});

	it('MultiPoint and LineString yield each position', () => {
		expect(collect({ type: 'LineString', coordinates: [[0, 0], [1, 1]] })).toEqual([[0, 0], [1, 1]]);
		expect(collect({ type: 'MultiPoint', coordinates: [[2, 2], [3, 3]] })).toEqual([[2, 2], [3, 3]]);
	});

	it('Polygon and MultiLineString walk one level of nesting', () => {
		expect(collect({ type: 'Polygon', coordinates: [[[0, 0], [1, 0], [0, 1]]] })).toEqual([
			[0, 0], [1, 0], [0, 1]
		]);
	});

	it('MultiPolygon walks two levels of nesting', () => {
		const positions = collect({
			type: 'MultiPolygon',
			coordinates: [[[[0, 0], [1, 0]]], [[[5, 5], [6, 6]]]]
		});
		expect(positions).toEqual([[0, 0], [1, 0], [5, 5], [6, 6]]);
	});
});

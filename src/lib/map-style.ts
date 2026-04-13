import type { StyleSpecification } from 'maplibre-gl';

export const cartoLightStyle: StyleSpecification = {
	version: 8,
	sources: {
		'carto-light': {
			type: 'raster',
			tiles: [
				'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
				'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
				'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
				'https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png'
			],
			tileSize: 256,
			attribution:
				'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
		}
	},
	layers: [
		{
			id: 'carto-light-layer',
			type: 'raster',
			source: 'carto-light',
			minzoom: 0,
			maxzoom: 22
		}
	]
};

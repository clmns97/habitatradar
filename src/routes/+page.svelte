<script lang="ts">
	import { onMount } from 'svelte';
	import maplibregl, {
		type DataDrivenPropertyValueSpecification,
		type GeoJSONSource,
		type Map
	} from 'maplibre-gl';
	import { cartoLightStyle } from '$lib/map-style';
	import {
		fetchNearestProtectedAreas,
		fetchNearestProtectedAreasByGeoJSON,
		groupByAreaType,
		type ProtectedAreaFeature
	} from '$lib/protected-areas';
	import { forEachPosition, parseUploadedGeoJSON, type UploadedFeature } from '$lib/uploaded-geojson';

	let mapContainer: HTMLDivElement;
	let map: Map | null = null;
	let radarMarker: maplibregl.Marker | null = null;
	let clickMarker: maplibregl.Marker | null = null;
	let radarParams: { lng: number; lat: number; radiusKm: number } | null = null;
	let activePopup: maplibregl.Popup | null = null;

	let loading = $state(false);
	let error = $state<string | null>(null);
	let clickInfo = $state<{ lng: number; lat: number } | null>(null);
	let radiusKm = $state(50);
	let features = $state<ProtectedAreaFeature[]>([]);
	let sidebarOpen = $state(true);
	let draggingOver = $state(false);
	let uploadedFeatures = $state<UploadedFeature[]>([]);
	let activeUploadedFeatureId = $state<string | null>(null);
	let hoveredUploadedFeatureId = $state<string | null>(null);
	let selectedFeature = $state<ProtectedAreaFeature | null>(null);
	let expandedGroups = $state<Record<string, boolean>>({});

	// Filter state: which area types are visible
	let visibleAreaTypes = $state<Record<string, boolean>>({});

	const areaTypeColors: Record<string, string> = {
		'National Parks': '#2ecc71',
		'Nature Parks': '#3498db',
		'Nature Reserves': '#e67e22',
		'Landscape Protection Areas': '#f39c12',
		'Biosphere Reserves': '#16a085',
		'Bird Protection Areas': '#e74c3c',
		'Fauna-Flora-Habitat Areas': '#1abc9c',
		'National Natural Monuments': '#34495e',
		'Biosphere Reserve Zoning': '#9b59b6'
	};

	const groupedAreas = $derived(groupByAreaType(features));

	// Derive the set of area types present in current results
	const currentAreaTypes = $derived(Object.keys(groupedAreas));

	// When new area types appear in results, default them to visible
	$effect(() => {
		for (const t of currentAreaTypes) {
			if (!(t in visibleAreaTypes)) {
				visibleAreaTypes[t] = true;
			}
		}
	});

	// Apply filter to map layer imperatively (map is not reactive)
	function applyFilter() {
		if (!map || !map.getLayer('protected-areas-fill')) return;

		const hiddenTypes = Object.entries(visibleAreaTypes)
			.filter(([, v]) => !v)
			.map(([k]) => k);

		if (hiddenTypes.length === 0) {
			map.setFilter('protected-areas-fill', null);
		} else {
			const filter: any = ['all'];
			for (const t of hiddenTypes) {
				filter.push(['!=', ['get', 'area_type'], t]);
			}
			map.setFilter('protected-areas-fill', filter);
		}
	}

	function buildFillColorExpression(): DataDrivenPropertyValueSpecification<string> {
		const expression: unknown[] = ['case'];
		for (const [areaType, color] of Object.entries(areaTypeColors)) {
			expression.push(['==', ['get', 'area_type'], areaType], color);
		}
		expression.push('#64748b');
		return expression as DataDrivenPropertyValueSpecification<string>;
	}

	function setMapData(featureList: ProtectedAreaFeature[]) {
		if (!map) return;
		const source = map.getSource('protected-areas') as GeoJSONSource | undefined;
		source?.setData({ type: 'FeatureCollection', features: featureList });
	}

	function setUploadedGeometryData(data: any) {
		if (!map) return;
		const source = map.getSource('uploaded-geometry') as GeoJSONSource | undefined;
		source?.setData(data);
	}

	function updateUploadedGeometryStyles() {
		if (!map) return;
		const activeId = activeUploadedFeatureId ?? '';
		const hoverId = hoveredUploadedFeatureId ?? '';

		if (map.getLayer('uploaded-geometry-fill')) {
			map.setPaintProperty('uploaded-geometry-fill', 'fill-color', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				'#dc2626',
				['==', ['get', '__upload_id'], hoverId],
				'#2563eb',
				'#2563eb'
			]);
			map.setPaintProperty('uploaded-geometry-fill', 'fill-opacity', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				0.28,
				['==', ['get', '__upload_id'], hoverId],
				0.22,
				0.12
			]);
		}

		if (map.getLayer('uploaded-geometry-line')) {
			map.setPaintProperty('uploaded-geometry-line', 'line-color', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				'#dc2626',
				['==', ['get', '__upload_id'], hoverId],
				'#2563eb',
				'#1d4ed8'
			]);
			map.setPaintProperty('uploaded-geometry-line', 'line-width', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				4,
				['==', ['get', '__upload_id'], hoverId],
				3,
				2
			]);
		}

		if (map.getLayer('uploaded-geometry-point')) {
			map.setPaintProperty('uploaded-geometry-point', 'circle-color', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				'#dc2626',
				['==', ['get', '__upload_id'], hoverId],
				'#2563eb',
				'#1d4ed8'
			]);
			map.setPaintProperty('uploaded-geometry-point', 'circle-radius', [
				'case',
				['==', ['get', '__upload_id'], activeId],
				8,
				['==', ['get', '__upload_id'], hoverId],
				7,
				6
			]);
		}
	}

	function extendBoundsFromGeometry(bounds: maplibregl.LngLatBounds, geometry: any) {
		if (!geometry) return;
		forEachPosition(geometry, (position) => bounds.extend(position as [number, number]));
	}

	function zoomToUploadedFeature(uploadedFeature: { feature: any }) {
		if (!map || !uploadedFeature?.feature?.geometry) return;
		const bounds = new maplibregl.LngLatBounds();
		extendBoundsFromGeometry(bounds, uploadedFeature.feature.geometry);
		if (!bounds.isEmpty()) {
			const sidebarWidth = sidebarOpen ? 340 : 0;
			map.fitBounds(bounds, {
				padding: { top: 80, bottom: 80, left: sidebarWidth + 40, right: 80 },
				maxZoom: 14,
				duration: 600
			});
		}
	}

	// --- Persistent click marker ---
	function placeClickMarker(lng: number, lat: number) {
		clickMarker?.remove();
		const el = document.createElement('div');
		el.style.cssText = 'width:0;height:0;position:relative;pointer-events:none;';
		el.innerHTML = `
			<div class="click-marker">
				<div class="click-marker-pulse"></div>
				<div class="click-marker-dot"></div>
			</div>
		`;
		clickMarker = new maplibregl.Marker({ element: el, anchor: 'center' })
			.setLngLat([lng, lat])
			.addTo(map!);
	}

	// --- Radar animation ---

	/** Convert a km radius at a given lat/lng to screen pixels at current zoom. */
	function kmToPixels(lng: number, lat: number, km: number): number {
		if (!map) return 100;
		const center = map.project([lng, lat]);
		// Move ~km north using lat offset (1 deg lat ≈ 111.32 km)
		const north = map.project([lng, lat + km / 111.32]);
		const dx = center.x - north.x;
		const dy = center.y - north.y;
		return Math.sqrt(dx * dx + dy * dy);
	}

	function applyRadarSize(px: number) {
		if (!radarMarker) return;
		const el = radarMarker.getElement();
		const container = el.querySelector<HTMLElement>('.radar-container');
		if (!container) return;
		const d = px * 2;
		container.style.width = `${d}px`;
		container.style.height = `${d}px`;

		// Scale the three rings relative to full radius
		const r1 = el.querySelector<HTMLElement>('.radar-ring-1');
		const r2 = el.querySelector<HTMLElement>('.radar-ring-2');
		const r3 = el.querySelector<HTMLElement>('.radar-ring-3');
		const sweep = el.querySelector<HTMLElement>('.radar-sweep');

		if (r1) { r1.style.width = `${d * 0.33}px`; r1.style.height = `${d * 0.33}px`; r1.style.margin = `${-d * 0.165}px 0 0 ${-d * 0.165}px`; }
		if (r2) { r2.style.width = `${d * 0.66}px`; r2.style.height = `${d * 0.66}px`; r2.style.margin = `${-d * 0.33}px 0 0 ${-d * 0.33}px`; }
		if (r3) { r3.style.width = `${d}px`;        r3.style.height = `${d}px`;        r3.style.margin = `${-px}px 0 0 ${-px}px`; }
		if (sweep) { sweep.style.width = `${px}px`; }
	}

	function showRadar(lng: number, lat: number, radiusKm: number) {
		removeRadar();
		radarParams = { lng, lat, radiusKm };

		const el = document.createElement('div');
		el.style.cssText = 'width:0;height:0;position:relative;pointer-events:none;';
		el.innerHTML = `
			<div class="radar-container">
				<div class="radar-ring radar-ring-1"></div>
				<div class="radar-ring radar-ring-2"></div>
				<div class="radar-ring radar-ring-3"></div>
				<div class="radar-sweep"></div>
				<div class="radar-center"></div>
			</div>
		`;
		radarMarker = new maplibregl.Marker({ element: el, anchor: 'center' })
			.setLngLat([lng, lat])
			.addTo(map!);

		applyRadarSize(kmToPixels(lng, lat, radiusKm));
	}

	function removeRadar() {
		radarMarker?.remove();
		radarMarker = null;
		radarParams = null;
	}

	async function searchAtPoint(lng: number, lat: number) {
		loading = true;
		error = null;
		activeUploadedFeatureId = null;
		hoveredUploadedFeatureId = null;
		updateUploadedGeometryStyles();
		clickInfo = { lng, lat };
		showRadar(lng, lat, radiusKm);

		try {
			const data = await fetchNearestProtectedAreas(lng, lat, radiusKm);
			features = data.features;
			expandedGroups = {};
			setMapData(data.features);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unknown error while querying backend';
			features = [];
			setMapData([]);
		} finally {
			loading = false;
			removeRadar();
			placeClickMarker(lng, lat);
		}
	}

	function buildPopupHTML(feature: ProtectedAreaFeature): string {
		const props = feature.properties ?? {};
		const color = areaTypeColors[props.area_type as string] ?? '#64748b';
		const rows = Object.entries(props)
			.filter(([k]) => !['id', 'fid', 'geom', 'geometry'].includes(k))
			.map(([k, v]) => {
				const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
				const value = typeof v === 'number' && k.includes('km')
					? `${(v as number).toFixed(2)} km`
					: String(v ?? '—');
				return `<tr>
					<td style="padding:3px 10px 3px 0;color:#6b7280;white-space:nowrap;font-size:11px;text-transform:uppercase;letter-spacing:0.04em">${label}</td>
					<td style="padding:3px 0;font-size:12px;font-weight:500;color:#111827">${value}</td>
				</tr>`;
			}).join('');
		return `
			<div style="font-family:system-ui,sans-serif;padding:2px 0;color:#111827">
				<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
					<span style="width:10px;height:10px;border-radius:50%;background:${color};flex-shrink:0;display:inline-block"></span>
					<span style="font-size:13px;font-weight:700;line-height:1.3;color:#111827">${props.name ?? 'Unnamed area'}</span>
				</div>
				<table style="border-collapse:collapse;width:100%">${rows}</table>
			</div>`;
	}

	function buildUploadedPopupHTML(feature: any): string {
		const props = feature?.properties ?? {};
		const rows = Object.entries(props)
			.filter(([k]) => !k.startsWith('__'))
			.map(([k, v]) => {
				const label = k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
				const value = String(v ?? '—');
				return `<tr>
					<td style="padding:3px 10px 3px 0;color:#6b7280;white-space:nowrap;font-size:11px;text-transform:uppercase;letter-spacing:0.04em">${label}</td>
					<td style="padding:3px 0;font-size:12px;font-weight:500;color:#111827">${value}</td>
				</tr>`;
			})
			.join('');

		const title = props.__upload_name ?? props.name ?? 'Uploaded feature';
		return `
			<div style="font-family:system-ui,sans-serif;padding:2px 0;color:#111827">
				<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
					<span style="width:10px;height:10px;border-radius:50%;background:#1d4ed8;flex-shrink:0;display:inline-block"></span>
					<span style="font-size:13px;font-weight:700;line-height:1.3;color:#111827">${title}</span>
				</div>
				<table style="border-collapse:collapse;width:100%">${rows || '<tr><td style="font-size:12px;color:#6b7280">No properties</td></tr>'}</table>
			</div>`;
	}

	function featureCentroid(feature: ProtectedAreaFeature): [number, number] {
		const geom = feature.geometry;
		const bounds = new maplibregl.LngLatBounds();
		if (geom.type === 'Polygon') geom.coordinates.flat().forEach(c => bounds.extend(c as [number, number]));
		else if (geom.type === 'MultiPolygon') geom.coordinates.flat(2).forEach(c => bounds.extend(c as [number, number]));
		else if (geom.type === 'Point') return geom.coordinates as [number, number];
		const c = bounds.getCenter();
		return [c.lng, c.lat];
	}

	function showFeaturePopup(feature: ProtectedAreaFeature) {
		if (!map) return;
		activePopup?.remove();
		const [lng, lat] = featureCentroid(feature);
		activePopup = new maplibregl.Popup({ closeButton: true, maxWidth: '300px', className: 'habitat-popup' })
			.setLngLat([lng, lat])
			.setHTML(buildPopupHTML(feature))
			.addTo(map);
		activePopup.on('close', () => { activePopup = null; });
	}

	function selectFeature(feature: ProtectedAreaFeature) {
		selectedFeature = feature;

		// Highlight on map
		const src = map?.getSource('highlight-area') as GeoJSONSource | undefined;
		src?.setData({ type: 'FeatureCollection', features: [feature] });

		// Dim everything except the selected feature using a data-driven expression
		const name = feature.properties?.name;
		const areaType = feature.properties?.area_type;
		map?.setPaintProperty('protected-areas-fill', 'fill-opacity', [
			'case',
			['all', ['==', ['get', 'name'], name], ['==', ['get', 'area_type'], areaType]],
			0.6,
			0.15
		]);

		// Show popup
		showFeaturePopup(feature);

		// Zoom to bounds
		if (!map) return;
		const geom = feature.geometry;
		const bounds = new maplibregl.LngLatBounds();
		const addCoords = (coords: number[]) => bounds.extend(coords as [number, number]);
		if (geom.type === 'Polygon') geom.coordinates.flat().forEach(addCoords);
		else if (geom.type === 'MultiPolygon') geom.coordinates.flat(2).forEach(addCoords);
		else if (geom.type === 'Point') addCoords(geom.coordinates);

		if (!bounds.isEmpty()) {
			const sidebarWidth = sidebarOpen ? 340 : 0;
			map.fitBounds(bounds, {
				padding: { top: 80, bottom: 80, left: sidebarWidth + 40, right: 80 },
				maxZoom: 13,
				duration: 600
			});
		}
	}

	function clearSelection() {
		selectedFeature = null;
		activePopup?.remove();
		activePopup = null;
		const src = map?.getSource('highlight-area') as GeoJSONSource | undefined;
		src?.setData({ type: 'FeatureCollection', features: [] });
		map?.setPaintProperty('protected-areas-fill', 'fill-opacity', 0.6);
	}

	function resetAll() {
		error = null;
		clickInfo = null;
		features = [];
		uploadedFeatures = [];
		activeUploadedFeatureId = null;
		hoveredUploadedFeatureId = null;
		visibleAreaTypes = {};
		clearSelection();
		removeRadar();
		clickMarker?.remove();
		clickMarker = null;
		setMapData([]);
		setUploadedGeometryData({ type: 'FeatureCollection', features: [] });
		updateUploadedGeometryStyles();
	}

	async function searchUploadedFeature(uploadedFeature: UploadedFeature) {
		if (!uploadedFeature) {
			error = 'Upload a GeoJSON feature first';
			return;
		}

		loading = true;
		error = null;
		activeUploadedFeatureId = uploadedFeature.id;
		updateUploadedGeometryStyles();
		zoomToUploadedFeature(uploadedFeature);
		removeRadar();
		clickInfo = null;

		try {
			const data = await fetchNearestProtectedAreasByGeoJSON(uploadedFeature.feature, radiusKm);
			features = data.features;
			expandedGroups = {};
			setMapData(data.features);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unknown error while querying backend';
			features = [];
			setMapData([]);
		} finally {
			loading = false;
		}
	}

	function setHoveredUploadedFeature(featureId: string | null) {
		hoveredUploadedFeatureId = featureId;
		updateUploadedGeometryStyles();
	}

	function handleUploadedGeometryClick(event: any) {
		event.preventDefault();
		const feature = event.features?.[0];
		if (!feature || !map) return;

		const featureId = feature.properties?.__upload_id;
		if (featureId) {
			activeUploadedFeatureId = String(featureId);
			updateUploadedGeometryStyles();
		}

		activePopup?.remove();
		activePopup = new maplibregl.Popup({ closeButton: true, maxWidth: '300px', className: 'habitat-popup' })
			.setLngLat(event.lngLat)
			.setHTML(buildUploadedPopupHTML(feature))
			.addTo(map);
		activePopup.on('close', () => {
			activePopup = null;
		});
	}

	function toggleAreaType(areaType: string) {
		visibleAreaTypes = { ...visibleAreaTypes, [areaType]: !visibleAreaTypes[areaType] };
		applyFilter();
	}

	function showAll() {
		const updated = { ...visibleAreaTypes };
		for (const k of Object.keys(updated)) updated[k] = true;
		visibleAreaTypes = updated;
		applyFilter();
	}

	function hideAll() {
		const updated = { ...visibleAreaTypes };
		for (const k of Object.keys(updated)) updated[k] = false;
		visibleAreaTypes = updated;
		applyFilter();
	}

	// --- Drag & Drop GeoJSON ---
	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		draggingOver = true;
	}

	function handleDragLeave() {
		draggingOver = false;
	}

	async function handleDrop(e: DragEvent) {
		e.preventDefault();
		draggingOver = false;
		const file = e.dataTransfer?.files[0];
		if (!file) return;
		await loadGeoJSONFile(file);
	}

	async function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		await loadGeoJSONFile(file);
		input.value = '';
	}

	async function loadGeoJSONFile(file: File) {
		try {
			const text = await file.text();
			const geojson = JSON.parse(text) as unknown;
			const { uploadedFeatures: parsedFeatures, displayGeoJSON } = parseUploadedGeoJSON(geojson);

			uploadedFeatures = parsedFeatures;
			activeUploadedFeatureId = null;
			hoveredUploadedFeatureId = null;
			setUploadedGeometryData(displayGeoJSON);
			updateUploadedGeometryStyles();
			error = null;

			if (map && displayGeoJSON.features.length > 0) {
				const bounds = new maplibregl.LngLatBounds();
				for (const f of displayGeoJSON.features) {
					extendBoundsFromGeometry(bounds, f.geometry);
				}
				if (!bounds.isEmpty()) {
					map.fitBounds(bounds, { padding: 60, maxZoom: 12 });
				}
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to parse GeoJSON file';
			uploadedFeatures = [];
			activeUploadedFeatureId = null;
			hoveredUploadedFeatureId = null;
			setUploadedGeometryData({ type: 'FeatureCollection', features: [] });
			updateUploadedGeometryStyles();
		}
	}

	onMount(() => {
		map = new maplibregl.Map({
			container: mapContainer,
			style: cartoLightStyle,
			center: [9.5, 51.2],
			zoom: 6
		});

		map.addControl(new maplibregl.NavigationControl(), 'top-right');

		map.on('load', () => {
			if (!map) return;

			map.addSource('uploaded-geometry', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] }
			});

			map.addLayer({
				id: 'uploaded-geometry-fill',
				type: 'fill',
				source: 'uploaded-geometry',
				filter: ['==', ['geometry-type'], 'Polygon'],
				paint: {
					'fill-color': '#2563eb',
					'fill-opacity': 0.18
				}
			});

			map.addLayer({
				id: 'uploaded-geometry-line',
				type: 'line',
				source: 'uploaded-geometry',
				filter: [
					'any',
					['==', ['geometry-type'], 'Polygon'],
					['==', ['geometry-type'], 'LineString']
				],
				paint: {
					'line-color': '#1d4ed8',
					'line-width': 2,
					'line-opacity': 0.9
				}
			});

			map.addLayer({
				id: 'uploaded-geometry-point',
				type: 'circle',
				source: 'uploaded-geometry',
				filter: ['==', ['geometry-type'], 'Point'],
				paint: {
					'circle-radius': 6,
					'circle-color': '#1d4ed8',
					'circle-stroke-color': '#ffffff',
					'circle-stroke-width': 1.5
				}
			});

			map.on('click', 'uploaded-geometry-fill', handleUploadedGeometryClick);
			map.on('click', 'uploaded-geometry-line', handleUploadedGeometryClick);
			map.on('click', 'uploaded-geometry-point', handleUploadedGeometryClick);

			map.on('mouseenter', 'uploaded-geometry-fill', () => {
				map!.getCanvas().style.cursor = 'pointer';
			});
			map.on('mouseleave', 'uploaded-geometry-fill', () => {
				map!.getCanvas().style.cursor = '';
			});
			map.on('mouseenter', 'uploaded-geometry-line', () => {
				map!.getCanvas().style.cursor = 'pointer';
			});
			map.on('mouseleave', 'uploaded-geometry-line', () => {
				map!.getCanvas().style.cursor = '';
			});
			map.on('mouseenter', 'uploaded-geometry-point', () => {
				map!.getCanvas().style.cursor = 'pointer';
			});
			map.on('mouseleave', 'uploaded-geometry-point', () => {
				map!.getCanvas().style.cursor = '';
			});

			map.addSource('protected-areas', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] }
			});

			map.addLayer({
				id: 'protected-areas-fill',
				type: 'fill',
				source: 'protected-areas',
				paint: {
					'fill-color': buildFillColorExpression(),
					'fill-opacity': 0.6,
					'fill-outline-color': '#1f2937'
				}
			});

			// Highlight source & layers
			map.addSource('highlight-area', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] }
			});
			map.addLayer({
				id: 'highlight-fill',
				type: 'fill',
				source: 'highlight-area',
				paint: { 'fill-color': '#fff', 'fill-opacity': 0.25 }
			});
			map.addLayer({
				id: 'highlight-outline',
				type: 'line',
				source: 'highlight-area',
				paint: { 'line-color': '#fff', 'line-width': 2.5, 'line-opacity': 0.9 }
			});

			// Click on a feature → highlight + zoom + popup, don't trigger new search
			map.on('click', 'protected-areas-fill', (event) => {
				event.preventDefault();
				const feature = event.features?.[0];
				if (!feature) return;

				// Match back to our full feature (MapLibre strips geometry from event.features)
				const matched = features.find(
					f => f.properties?.name === feature.properties?.name &&
					     f.properties?.area_type === feature.properties?.area_type
				);
				// selectFeature handles highlight, dim, popup, and zoom
				if (matched) {
					selectFeature(matched);
				} else {
					// Fallback: show popup at click location using raw properties
					new maplibregl.Popup({ closeButton: true, maxWidth: '300px', className: 'habitat-popup' })
						.setLngLat(event.lngLat)
						.setHTML(buildPopupHTML({ type: 'Feature', properties: feature.properties, geometry: { type: 'Point', coordinates: [event.lngLat.lng, event.lngLat.lat] } }))
						.addTo(map!);
				}
			});

			// Pointer cursor on hover
			map.on('mouseenter', 'protected-areas-fill', () => {
				map!.getCanvas().style.cursor = 'pointer';
			});
			map.on('mouseleave', 'protected-areas-fill', () => {
				map!.getCanvas().style.cursor = '';
			});

			// Click on empty map → new search (only if not consumed by layer click)
			map.on('click', (event) => {
				if ((event as any).defaultPrevented) return;
				void searchAtPoint(event.lngLat.lng, event.lngLat.lat);
			});

			map.on('zoom', () => {
				if (radarParams) {
					applyRadarSize(kmToPixels(radarParams.lng, radarParams.lat, radarParams.radiusKm));
				}
			});
		});

		return () => {
			removeRadar();
			clickMarker?.remove();
			map?.remove();
			map = null;
		};
	});

	const visibleCount = $derived(
		Object.values(visibleAreaTypes).filter(Boolean).length
	);
	const totalTypeCount = $derived(Object.keys(visibleAreaTypes).length);
</script>

<div class="relative overflow-hidden" style="height: 100vh; width: 100vw;">
	<div bind:this={mapContainer} class="absolute inset-0" style="height: 100%; width: 100%;"></div>

	<!-- Sidebar toggle -->
	{#if !sidebarOpen}
		<button
			class="absolute left-3 top-3 z-20 btn btn-sm btn-neutral shadow-lg"
			onclick={() => (sidebarOpen = true)}
			aria-label="Open sidebar"
		>
			<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
			</svg>
		</button>
	{/if}

	<!-- Sidebar panel -->
	<aside
		class="absolute left-0 top-0 z-10 flex h-full w-85 max-w-[85vw] flex-col bg-base-100/95 shadow-2xl backdrop-blur-sm transition-transform duration-200 {sidebarOpen ? 'translate-x-0' : '-translate-x-full'}"
	>
		<!-- Header -->
		<div class="flex items-center justify-between border-b border-base-300 px-4 py-3">
			<div>
				<h1 class="text-xl font-bold tracking-tight">Habitat Radar</h1>
				<p class="text-xs text-base-content/60">Click map or drop GeoJSON</p>
			</div>
			<button
				class="btn btn-ghost btn-sm btn-square"
				onclick={() => (sidebarOpen = false)}
				aria-label="Close sidebar"
			>
				<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
				</svg>
			</button>
		</div>

		<!-- Scrollable content -->
		<div class="flex-1 overflow-y-auto">
			<!-- Search controls -->
			<div class="border-b border-base-300 px-4 py-3">
				<label class="form-control">
					<div class="label py-0.5">
						<span class="label-text text-xs font-medium">Search radius</span>
						<span class="label-text-alt text-xs font-semibold">{radiusKm} km</span>
					</div>
					<input
						type="range"
						min="5"
						max="100"
						step="5"
						class="range range-primary range-xs"
						bind:value={radiusKm}
					/>
				</label>

				{#if clickInfo}
					<div class="mt-2 flex items-center gap-2 text-xs text-base-content/60">
						<span>{clickInfo.lat.toFixed(4)}, {clickInfo.lng.toFixed(4)}</span>
					</div>
				{/if}

				{#if features.length > 0 || uploadedFeatures.length > 0}
					<div class="mt-2 flex gap-1.5">
						<button class="btn btn-xs btn-outline" onclick={resetAll}>Clear all</button>
					</div>
				{/if}
			</div>

			<!-- GeoJSON Drop Zone -->
			<div class="border-b border-base-300 px-4 py-3">
				<div
					class="relative flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-3 py-4 transition-colors
						{draggingOver ? 'border-primary bg-primary/10' : 'border-base-300 hover:border-primary/50 hover:bg-base-200/50'}"
					role="button"
					tabindex="0"
					ondragover={handleDragOver}
					ondragleave={handleDragLeave}
					ondrop={handleDrop}
					onclick={() => document.getElementById('geojson-input')?.click()}
					onkeydown={(e) => { if (e.key === 'Enter') document.getElementById('geojson-input')?.click(); }}
				>
					<svg xmlns="http://www.w3.org/2000/svg" class="mb-1 h-6 w-6 text-base-content/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
					</svg>
					{#if uploadedFeatures.length === 0}
						<span class="text-xs font-medium text-base-content/70">Drop .geojson file here</span>
						<span class="text-[10px] text-base-content/50">or click to browse</span>
					{:else}
						<span class="text-xs font-medium text-primary">{uploadedFeatures.length} uploaded feature{uploadedFeatures.length > 1 ? 's' : ''}</span>
						<span class="text-[10px] text-base-content/50">Drop another file to replace</span>
					{/if}
				</div>
				<input
					id="geojson-input"
					type="file"
					accept=".geojson,.json"
					class="hidden"
					onchange={handleFileInput}
				/>
				{#if uploadedFeatures.length > 0}
					<div class="mt-2 space-y-1.5">
						{#each uploadedFeatures as uf}
							<button
								type="button"
								class="flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors
									{activeUploadedFeatureId === uf.id ? 'border-error/60 bg-error/10' : 'border-base-300 hover:border-primary/60 hover:bg-base-200/60'}"
								onmouseenter={() => setHoveredUploadedFeature(uf.id)}
								onmouseleave={() => setHoveredUploadedFeature(null)}
								onclick={() => void searchUploadedFeature(uf)}
								disabled={loading}
							>
								<span class="truncate font-medium">{uf.name}</span>
								<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" />
								</svg>
							</button>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Status messages -->
			{#if loading}
				<div class="flex items-center gap-2 border-b border-base-300 px-4 py-2 text-xs text-info">
					<span class="loading loading-spinner loading-xs"></span>
					<span>Scanning area...</span>
				</div>
			{/if}
			{#if error}
				<div class="border-b border-base-300 bg-error/10 px-4 py-2 text-xs text-error">{error}</div>
			{/if}

			<!-- Filter & Results -->
			{#if features.length > 0}
				<!-- Area type filters -->
				<div class="border-b border-base-300 px-4 py-3">
					<div class="mb-2 flex items-center justify-between">
						<span class="text-xs font-semibold uppercase tracking-wider text-base-content/50">
							Filter ({visibleCount}/{totalTypeCount})
						</span>
						<div class="flex gap-1">
							<button class="btn btn-ghost btn-xs px-1.5 text-[10px]" onclick={showAll}>All</button>
							<button class="btn btn-ghost btn-xs px-1.5 text-[10px]" onclick={hideAll}>None</button>
						</div>
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each Object.entries(groupedAreas) as [areaType, areaFeatures]}
							{@const color = areaTypeColors[areaType] || '#64748b'}
							{@const visible = visibleAreaTypes[areaType] !== false}
							<button
								class="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all
									{visible ? 'border-transparent text-white' : 'border-base-300 bg-base-200/50 text-base-content/40'}"
								style={visible ? `background-color: ${color}` : ''}
								onclick={() => toggleAreaType(areaType)}
							>
								<span>{areaType}</span>
								<span class="rounded-full {visible ? 'bg-white/30' : 'bg-base-300'} px-1.5 text-[10px]">{areaFeatures.length}</span>
							</button>
						{/each}
					</div>
				</div>

				<!-- Results list -->
				<div class="px-4 py-3">
					<div class="mb-2 text-xs font-semibold uppercase tracking-wider text-base-content/50">
						Results ({features.length})
					</div>
					<div class="space-y-1.5">
						{#each Object.entries(groupedAreas) as [areaType, areaFeatures]}
							{#if visibleAreaTypes[areaType] !== false}
								{@const color = areaTypeColors[areaType] || '#64748b'}
								{@const expanded = expandedGroups[areaType] === true}
								{@const visibleFeatures = expanded ? areaFeatures : areaFeatures.slice(0, 5)}
								{@const hiddenCount = areaFeatures.length - 5}
								{#each visibleFeatures as feature}
									{@const isSelected = selectedFeature === feature}
									<button
										class="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors
											{isSelected ? 'bg-base-300 ring-1 ring-base-content/20' : 'hover:bg-base-200/60'}"
										onclick={() => selectFeature(feature)}
									>
										<span
											class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full"
											style="background-color: {color}"
										></span>
										<div class="min-w-0 flex-1">
											<div class="truncate text-sm font-medium leading-tight">
												{String(feature.properties?.name || 'Unnamed area')}
											</div>
											<div class="text-[11px] text-base-content/50">
												{#if typeof feature.properties?.distance_km === 'number'}
													{feature.properties.distance_km.toFixed(1)} km
												{/if}
											</div>
										</div>
										{#if isSelected}
											<svg xmlns="http://www.w3.org/2000/svg" class="mt-1 h-3 w-3 shrink-0 text-base-content/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
											</svg>
										{/if}
									</button>
								{/each}
								{#if hiddenCount > 0}
									<button
										class="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left transition-colors hover:bg-base-200/60"
										onclick={() => { expandedGroups = { ...expandedGroups, [areaType]: !expanded }; }}
									>
										<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 shrink-0 text-base-content/30 transition-transform {expanded ? 'rotate-180' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
										</svg>
										<span class="text-[11px] text-base-content/40">
											{expanded ? 'Show less' : `+${hiddenCount} more`}
										</span>
									</button>
								{/if}
							{/if}
						{/each}
					</div>
				</div>
			{:else if !loading}
				<div class="px-4 py-8 text-center text-sm text-base-content/40">
					Click the map to search for<br />protected areas nearby
				</div>
			{/if}
		</div>

		<!-- Footer -->
		<div class="border-t border-base-300 px-4 py-2 text-[10px] text-base-content/40">
			Basemap: Carto Light
		</div>
	</aside>
</div>

<style>
	/* Feature popup */
	:global(.habitat-popup .maplibregl-popup-content) {
		border-radius: 10px;
		padding: 14px 16px;
		box-shadow: 0 4px 24px rgba(0,0,0,0.15);
		border: 1px solid rgba(0,0,0,0.08);
		min-width: 200px;
	}

	:global(.habitat-popup .maplibregl-popup-close-button) {
		font-size: 18px;
		padding: 4px 8px;
		color: #6b7280;
		line-height: 1;
	}

	:global(.habitat-popup .maplibregl-popup-close-button:hover) {
		color: #111;
		background: transparent;
	}

	:global(.habitat-popup .maplibregl-popup-tip) {
		border-top-color: white;
	}

	/* Persistent click marker */
	:global(.click-marker) {
		width: 20px;
		height: 20px;
		position: absolute;
		transform: translate(-50%, -50%);
		pointer-events: none;
	}

	:global(.click-marker-dot) {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 8px;
		height: 8px;
		margin: -4px 0 0 -4px;
		background: #fff;
		border: 2px solid #22d3ee;
		border-radius: 50%;
		box-shadow: 0 0 0 1px rgba(0,0,0,0.2);
	}

	:global(.click-marker-pulse) {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 20px;
		height: 20px;
		margin: -10px 0 0 -10px;
		border-radius: 50%;
		background: rgba(34, 211, 238, 0.25);
		animation: click-marker-breathe 2s ease-in-out infinite;
	}

	@keyframes -global-click-marker-breathe {
		0%, 100% { transform: scale(1); opacity: 0.6; }
		50% { transform: scale(1.5); opacity: 0.2; }
	}

	/* Radar animation — :global because elements are created via JS, not Svelte template */
	:global(.radar-container) {
		width: 160px;
		height: 160px;
		position: absolute;
		transform: translate(-50%, -50%);
		pointer-events: none;
	}

	:global(.radar-center) {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 8px;
		height: 8px;
		margin: -4px 0 0 -4px;
		background: #22d3ee;
		border-radius: 50%;
		box-shadow: 0 0 8px 2px rgba(34, 211, 238, 0.6);
	}

	:global(.radar-ring) {
		position: absolute;
		top: 50%;
		left: 50%;
		border-radius: 50%;
		border: 1.5px solid transparent;
		opacity: 0;
		animation: radar-pulse 2.4s ease-out infinite;
		animation-fill-mode: backwards;
	}

	:global(.radar-ring-1) { animation-delay: 0s; }
	:global(.radar-ring-2) { animation-delay: 0.5s; }
	:global(.radar-ring-3) { animation-delay: 1s; }

	:global(.radar-sweep) {
		position: absolute;
		top: 50%;
		left: 50%;
		height: 2px;
		transform-origin: 0% 50%;
		background: linear-gradient(90deg, rgba(34, 211, 238, 0.8), transparent);
		animation: radar-spin 1.8s linear infinite;
	}

	@keyframes -global-radar-spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	@keyframes -global-radar-pulse {
		0% {
			opacity: 0;
			border-color: rgba(34, 211, 238, 0.7);
			transform: scale(0.1);
		}
		15% {
			opacity: 0.8;
		}
		100% {
			opacity: 0;
			border-color: rgba(34, 211, 238, 0);
			transform: scale(1);
		}
	}
</style>

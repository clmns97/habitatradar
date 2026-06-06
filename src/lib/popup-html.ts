/**
 * HTML builders for MapLibre popups.
 *
 * These produce raw HTML strings that are handed to `popup.setHTML()`, so every
 * value derived from feature properties (which, for uploaded GeoJSON, is fully
 * user-controlled) MUST go through {@link escapeHtml} to prevent XSS.
 */

/** Escape a value for safe interpolation into an HTML string (XSS guard). */
export function escapeHtml(value: unknown): string {
	return String(value ?? '—').replace(
		/[&<>"']/g,
		(c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c
	);
}

function propRows(props: Record<string, unknown>, skip: (key: string) => boolean): string {
	return Object.entries(props)
		.filter(([k]) => !skip(k))
		.map(([k, v]) => {
			const label = k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
			const value = String(v ?? '—');
			return `<tr>
					<td style="padding:3px 10px 3px 0;color:#6b7280;white-space:nowrap;font-size:11px;text-transform:uppercase;letter-spacing:0.04em">${escapeHtml(label)}</td>
					<td style="padding:3px 0;font-size:12px;font-weight:500;color:#111827">${escapeHtml(value)}</td>
				</tr>`;
		})
		.join('');
}

/** Build the popup body for a user-uploaded GeoJSON feature. */
export function buildUploadedPopupHTML(feature: { properties?: Record<string, unknown> | null }): string {
	const props = feature?.properties ?? {};
	const rows = propRows(props, (k) => k.startsWith('__'));
	const title = props.__upload_name ?? props.name ?? 'Uploaded feature';
	return `
			<div style="font-family:system-ui,sans-serif;padding:2px 0;color:#111827">
				<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
					<span style="width:10px;height:10px;border-radius:50%;background:#1d4ed8;flex-shrink:0;display:inline-block"></span>
					<span style="font-size:13px;font-weight:700;line-height:1.3;color:#111827">${escapeHtml(title)}</span>
				</div>
				<table style="border-collapse:collapse;width:100%">${rows || '<tr><td style="font-size:12px;color:#6b7280">No properties</td></tr>'}</table>
			</div>`;
}

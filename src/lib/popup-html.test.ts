import { describe, expect, it } from 'vitest';
import { buildUploadedPopupHTML, escapeHtml } from './popup-html';

describe('escapeHtml', () => {
	it('escapes the five HTML-significant characters', () => {
		expect(escapeHtml(`<>&"'`)).toBe('&lt;&gt;&amp;&quot;&#39;');
	});

	it('neutralises a script-injection payload', () => {
		expect(escapeHtml('<img src=x onerror=alert(1)>')).toBe(
			'&lt;img src=x onerror=alert(1)&gt;'
		);
	});

	it('renders nullish values as an em dash', () => {
		expect(escapeHtml(null)).toBe('—');
		expect(escapeHtml(undefined)).toBe('—');
	});

	it('stringifies non-string values', () => {
		expect(escapeHtml(42)).toBe('42');
		expect(escapeHtml(false)).toBe('false');
	});

	it('leaves safe text untouched', () => {
		expect(escapeHtml('Naturpark Schwarzwald')).toBe('Naturpark Schwarzwald');
	});
});

describe('buildUploadedPopupHTML — XSS regression', () => {
	it('escapes a malicious property VALUE so no live tag survives', () => {
		const html = buildUploadedPopupHTML({
			properties: { note: '<img src=x onerror=alert(document.cookie)>' }
		});
		// The dangerous part is a live tag; the angle brackets must be neutralised.
		expect(html).not.toContain('<img');
		expect(html).toContain('&lt;img');
	});

	it('escapes a malicious property KEY', () => {
		const html = buildUploadedPopupHTML({
			properties: { '<script>evil</script>': 'x' }
		});
		// (the label formatter title-cases words, hence &lt;Script&gt;)
		expect(html).not.toContain('<script');
		expect(html).toContain('&lt;Script&gt;');
	});

	it('escapes the title (__upload_name)', () => {
		const html = buildUploadedPopupHTML({
			properties: { __upload_name: '"><svg onload=alert(1)>' }
		});
		expect(html).not.toContain('<svg');
		expect(html).toContain('&lt;svg');
	});

	it('prefers __upload_name, then name, then a default title', () => {
		expect(buildUploadedPopupHTML({ properties: { __upload_name: 'A', name: 'B' } })).toContain('A');
		expect(buildUploadedPopupHTML({ properties: { name: 'B' } })).toContain('B');
		expect(buildUploadedPopupHTML({ properties: {} })).toContain('Uploaded feature');
	});

	it('hides internal __-prefixed properties from the table', () => {
		const html = buildUploadedPopupHTML({
			properties: { __upload_id: 'secret-id', visible: 'yes' }
		});
		expect(html).not.toContain('secret-id');
		expect(html).toContain('Visible');
	});

	it('shows a placeholder row when there are no displayable properties', () => {
		const html = buildUploadedPopupHTML({ properties: {} });
		expect(html).toContain('No properties');
	});

	it('handles a missing properties object', () => {
		expect(() => buildUploadedPopupHTML({})).not.toThrow();
	});
});

// Cloudflare Worker: reverse-proxy for the HabitatRadar API.
//
// The browser talks only to this Worker (https://<name>.<sub>.workers.dev),
// which forwards to the VPS backend server-side — so the origin IP never
// appears in the frontend. CORS is handled here for the GitHub Pages origin.
//
// Deploy: paste into the Cloudflare dashboard worker editor, or
//   cd deploy/cloudflare-worker && npx wrangler deploy

const BACKEND = "https://REDACTED_HOST";
const ALLOWED_ORIGIN = "https://REDACTED_ORIGIN";

const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
  "Vary": "Origin",
};

export default {
  async fetch(request) {
    // CORS preflight — answer directly, don't bother the backend.
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    const url = new URL(request.url);
    const target = BACKEND + url.pathname + url.search;

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("origin");

    const isBodyless = request.method === "GET" || request.method === "HEAD";
    const resp = await fetch(target, {
      method: request.method,
      headers,
      body: isBodyless ? undefined : await request.text(),
    });

    // Pass the backend response through, but with our CORS headers.
    const out = new Headers(resp.headers);
    for (const [k, v] of Object.entries(CORS)) out.set(k, v);
    return new Response(resp.body, { status: resp.status, headers: out });
  },
};

// Cloudflare Worker: reverse-proxy for the HabitatRadar API.
//
// The browser talks only to this Worker, which forwards to the backend
// server-side — so the origin host never appears in the frontend. Config comes
// from Worker secrets (set with `wrangler secret put`), so no hosts/origins
// live in the repo:
//   BACKEND         the origin base URL, e.g. https://<origin-host>
//   ALLOWED_ORIGIN  the frontend origin allowed via CORS
//
// Deploy: cd deploy/cloudflare-worker && npx wrangler deploy

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

export default {
  async fetch(request, env) {
    const cors = corsHeaders(env.ALLOWED_ORIGIN);

    // CORS preflight — answer directly, don't bother the backend.
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    const url = new URL(request.url);
    const target = env.BACKEND + url.pathname + url.search;

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
    for (const [k, v] of Object.entries(cors)) out.set(k, v);
    return new Response(resp.body, { status: resp.status, headers: out });
  },
};

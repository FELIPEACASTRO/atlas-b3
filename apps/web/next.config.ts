import type { NextConfig } from "next";

// Proxy /api/* to the local FastAPI backend so the whole app is served from ONE
// origin. This lets a single tunnel (cloudflared) expose the frontend while the
// browser's API calls are forwarded server-side to the backend on the same
// machine — no CORS, no second public URL, keys never leave the host.
const nextConfig: NextConfig = {
  // Safety net if the app is ever served through a tunnel in dev mode: allow the
  // quick-tunnel host so Next doesn't block its own dev resources (HMR/chunks).
  // Production (`next start`) ignores this and serves any origin anyway.
  allowedDevOrigins: ["*.trycloudflare.com"],
  async rewrites() {
    const api = process.env.ATLAS_API_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;

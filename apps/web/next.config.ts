import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

/**
 * Production routes `/api/*` in nginx (chart/templates/nginx-configmap.yaml).
 * `next dev` alone has no backend, so for a local run against the services
 * set WINGMAN_DEV_DAY1_URL and WINGMAN_DEV_DAY2_URL (see README.md): the dev
 * server then proxies the same paths nginx does. The rewrites exist only in
 * the development server; a production build never has them.
 */
function devApiRewrites() {
  const day1 = process.env.WINGMAN_DEV_DAY1_URL;
  const day2 = process.env.WINGMAN_DEV_DAY2_URL;
  return [
    ...(day1
      ? ["auth", "day1", "webhooks"].map((prefix) => ({
          source: `/api/${prefix}/:path*`,
          destination: `${day1}/api/${prefix}/:path*`,
        }))
      : []),
    ...(day2 ? [{ source: "/api/day2/:path*", destination: `${day2}/api/day2/:path*` }] : []),
  ];
}

export default function config(phase: string): NextConfig {
  const nextConfig: NextConfig = { output: "standalone" };
  if (phase !== PHASE_DEVELOPMENT_SERVER) return nextConfig;
  const rewrites = devApiRewrites();
  return rewrites.length > 0 ? { ...nextConfig, rewrites: async () => rewrites } : nextConfig;
}

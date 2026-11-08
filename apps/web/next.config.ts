import path from "node:path";
import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// The repository root: the npm workspace and its one lockfile (ADR-0003).
// Set explicitly because Next.js 16.4 refuses to infer a root that contains
// the home directory, and in the UBI build image the home directory is the
// checkout (/opt/app-root/src), so `next build` could not find `next` there.
const workspaceRoot = path.join(__dirname, "../..");

/**
 * Production routes `/api/*` in nginx (deploy/helm/wingman/templates/nginx-configmap.yaml).
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

/**
 * Stamps each build (or dev server start). The persisted query cache is
 * keyed on it, so data cached in an older build's shapes never reaches the
 * pages of a newer one.
 */
const WINGMAN_WEB_BUILD = new Date().toISOString();

export default function config(phase: string): NextConfig {
  const nextConfig: NextConfig = {
    output: "standalone",
    outputFileTracingRoot: workspaceRoot,
    turbopack: { root: workspaceRoot },
    env: { WINGMAN_WEB_BUILD },
  };
  if (phase !== PHASE_DEVELOPMENT_SERVER) return nextConfig;
  const rewrites = devApiRewrites();
  return rewrites.length > 0 ? { ...nextConfig, rewrites: async () => rewrites } : nextConfig;
}

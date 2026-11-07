import path from "node:path";
import type { NextConfig } from "next";

// The repository root: the npm workspace and its one lockfile (ADR-0003).
// Set explicitly because Next.js 16.4 refuses to infer a root that contains
// the home directory, and in the UBI build image the home directory is the
// checkout (/opt/app-root/src), so `next build` could not find `next` there.
const workspaceRoot = path.join(__dirname, "../..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: workspaceRoot,
  turbopack: { root: workspaceRoot },
};

export default nextConfig;

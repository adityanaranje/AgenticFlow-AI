import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output lets the Docker image run `node server.js`
  // without shipping node_modules (see frontend/Dockerfile).
  output: "standalone",
};

export default nextConfig;

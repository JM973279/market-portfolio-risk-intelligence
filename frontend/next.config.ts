import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Use the compiler API: this environment returns empty captured CLI config output.
  // Type checking remains enabled; standalone tsc is also part of validation.
  experimental: { useTypeScriptCli: false },
  async rewrites() {
    const api = process.env.PORTFOLIO_API_INTERNAL_URL ?? (process.env.PORTFOLIO_API_INTERNAL_HOSTPORT ? `http://${process.env.PORTFOLIO_API_INTERNAL_HOSTPORT}` : "http://127.0.0.1:8000");
    return [{ source: "/api/portfolio/:path*", destination: `${api}/api/portfolio/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;

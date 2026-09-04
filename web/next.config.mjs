/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enables instrumentation.ts (register()), which fails the server startup
  // loudly if LEDGERPROOF_API_BASE_URL is unset -- stable by default from
  // Next.js 15 on, but still opt-in on the 14.x line this app is pinned to.
  experimental: {
    instrumentationHook: true,
  },
};

export default nextConfig;

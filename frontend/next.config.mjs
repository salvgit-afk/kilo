/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Il browser chiama /api/*, Next inoltra al backend FastAPI: così non
    // servono CORS né URL assoluti sparsi nei componenti.
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/:path*`,
      },
    ];
  },
};
export default nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    DEEPL_API_KEY: process.env.DEEPL_API_KEY,
  },
};

export default nextConfig;

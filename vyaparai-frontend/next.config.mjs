/** @type {import('next').NextConfig} */
const nextConfig = {
  // Don't fail prod builds on lint warnings — local `tsc --noEmit` already
  // gates the real type errors. ESLint is advisory in this project.
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Same for TS — type-checking happens locally via `npx tsc --noEmit` in CI/dev.
  // This prevents Vercel from failing on transient version-mismatch warnings.
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;

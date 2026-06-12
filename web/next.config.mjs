/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";
const basePath = process.env.ASTA_BASE_PATH ?? (isProd ? "/AstaNews" : "");

const nextConfig = {
  output: "export",              // 静态导出 → 每路由一份 HTML（真 MPA），GitHub Pages 友好
  basePath,
  assetPrefix: basePath || undefined,
  images: { unoptimized: true }, // Pages 无图片优化服务
  trailingSlash: true,           // /edition/2026-06-12/ → index.html，Pages 直出
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};
export default nextConfig;

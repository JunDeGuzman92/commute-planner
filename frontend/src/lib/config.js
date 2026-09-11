// API base URL: env var in production, localhost in development
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8101";

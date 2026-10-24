import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": { target: backend, changeOrigin: true },
      "/flows": { target: backend, changeOrigin: true },
      "/tasks": { target: backend, changeOrigin: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.js"],
  },
});

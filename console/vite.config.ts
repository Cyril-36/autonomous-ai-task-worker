/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { mockApi } from "./mock/plugin.ts";

const useMock = process.env.VITE_MOCK === "1";

export default defineConfig({
  plugins: [react(), ...(useMock ? [mockApi()] : [])],
  server: useMock
    ? { port: 5173 }
    : { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8100", changeOrigin: false } } },
  test: { environment: "node", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});

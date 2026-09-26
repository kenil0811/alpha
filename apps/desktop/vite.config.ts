import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig(({ command }) => ({
  plugins: [react()],
  clearScreen: false,
  // public/ holds only development qualification pages (the kit compositions); a release build
  // leaves them out.
  publicDir: command === "build" && !process.env.TAURI_ENV_DEBUG ? false : "public",
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
  },
  envPrefix: ["VITE_", "TAURI_ENV_*"],
  build: {
    target: process.env.TAURI_ENV_PLATFORM === "windows" ? "chrome105" : "safari13",
    minify: !process.env.TAURI_ENV_DEBUG,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: false,
  },
}));

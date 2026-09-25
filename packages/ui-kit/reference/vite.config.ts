import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Development-only reference sheet for the kit (not part of the packed package).
export default defineConfig({
  root: new URL(".", import.meta.url).pathname,
  plugins: [react()],
  server: { port: 1430, strictPort: true },
});

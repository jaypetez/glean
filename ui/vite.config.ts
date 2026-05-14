import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Dev mode: proxy API calls to the running glean daemon
      "/api": "http://localhost:9090",
      "/healthz": "http://localhost:9090",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
  },
});

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

const backend = process.env.WILDJOKER_BACKEND ?? "http://127.0.0.1:8101";

export default defineConfig({
  plugins: [svelte()],
  base: "/",
  build: { outDir: "dist", assetsDir: "assets" },
  server: {
    port: 5181,
    strictPort: true,
    proxy: { "/ws": { target: backend, ws: true } },
  },
  test: {
    include: ["src/**/*.test.ts"],
    // One forked worker keeps memory low on the shared dev VM.
    pool: "forks",
    maxWorkers: 1,
  },
});

import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The voice module lives in ../src/lib/voice, outside this package, so point
// its `svelte/store` import at this package's copy of Svelte.
const store = (file: string) =>
  fileURLToPath(new URL(`./node_modules/svelte/src/store/${file}`, import.meta.url));

export default defineConfig({
  resolve: { alias: { "svelte/store": store("index-client.js") } },
  server: { port: 5183, strictPort: true, fs: { allow: [".."] } },
  test: { root: "..", include: ["src/lib/voice/**/*.test.ts"] },
});

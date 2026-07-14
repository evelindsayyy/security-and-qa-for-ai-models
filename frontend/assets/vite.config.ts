import { resolve } from "node:path";
import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [preact()],
  root: resolve(__dirname),
  base: "/static/dist/",
  build: {
    outDir: resolve(__dirname, "../static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/main.ts"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});

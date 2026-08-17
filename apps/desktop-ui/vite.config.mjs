import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const configDirectory = dirname(fileURLToPath(import.meta.url));
const speechWorkletDirectory = resolve(
  configDirectory,
  "../../third_party/speech-to-speech/demo/worklets",
);
const speechWorklets = ["mic-capture.js", "audio-playback.js"];

function speechWorkletsPlugin() {
  return {
    name: "xinyu-speech-worklets",
    apply: "build",
    buildStart() {
      for (const fileName of speechWorklets) {
        this.emitFile({
          type: "asset",
          fileName: `worklets/${fileName}`,
          source: readFileSync(resolve(speechWorkletDirectory, fileName)),
        });
      }
    },
  };
}

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    port: 4173,
    strictPort: true,
    allowedHosts: ["terminal.local"],
    proxy: {
      "/core": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/core/, ""),
        ws: true,
      },
    },
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react(), speechWorkletsPlugin()],
});

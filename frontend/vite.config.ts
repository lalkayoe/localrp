import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend runs on 8420 by default; proxy /api in dev so the browser
// (and the phone-on-LAN use case) never needs CORS gymnastics.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8420",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
  },
});

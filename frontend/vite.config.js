import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend dev server on 38081, API proxied to 38080.
// VITE_DEMO=1 builds the static GitHub Pages preview: served from a project
// subpath, so assets need the matching base. The live app stays at root "/".
export default defineConfig({
  base: process.env.VITE_DEMO ? "/game-and-what/" : "/",
  plugins: [react()],
  server: {
    port: 38081,
    host: true,            // listen on 0.0.0.0 — reachable via Tailscale IP
    allowedHosts: true,    // allow Tailscale hostname/IP Host headers
    proxy: {
      "/api": {
        target: "http://127.0.0.1:38080",
        changeOrigin: true,
      },
    },
  },
});

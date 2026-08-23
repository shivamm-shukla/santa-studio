import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base is "/room/" so the production build can be mounted straight onto the
// FastAPI app at /room without rewriting asset URLs.
export default defineConfig({
  base: "/room/",
  plugins: [react()],
  server: {
    port: 5273,
    // The pipeline API still lives on the FastAPI app. Proxying it here means
    // the same fetch()/WebSocket URLs work in dev and in the built bundle.
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});

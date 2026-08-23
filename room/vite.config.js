import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = process.env.SANTA_API || "http://127.0.0.1:8000";

// base is "/room/" so the production build can be mounted straight onto the
// FastAPI app at /room without rewriting asset URLs.
export default defineConfig({
  base: "/room/",
  plugins: [react()],
  server: {
    port: 5273,
    // The pipeline API still lives on the FastAPI app. Proxying it here means
    // the same fetch()/EventSource URLs work in dev and in the built bundle.
    // SANTA_API points the proxy at an app on another port, which is what
    // running two of them at once needs.
    proxy: {
      "/api": {
        target: API,
        // SSE must not be buffered or the room receives a run in one lump
        // when it finishes, rather than as it happens.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if ((proxyRes.headers["content-type"] || "").includes("text/event-stream")) {
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
      "/media": API,
    },
  },
});

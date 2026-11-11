import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API's project-unique alias on the compose network (see docker-compose.yml). Plain "api"
// would also match other projects' APIs on the shared Caddy network.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    // Vite rejects requests for hostnames it was not told about; Caddy forwards APP_DOMAIN.
    allowedHosts: [process.env.APP_DOMAIN].filter(Boolean),
    proxy: { "/api": { target: "http://knowledge-farm-api:8000", changeOrigin: true } },
  },
  test: { environment: "jsdom", globals: true },
});

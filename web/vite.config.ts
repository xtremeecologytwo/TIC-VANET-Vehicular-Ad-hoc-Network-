import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, el SPA (5173) proxya las llamadas /api al backend FastAPI (8000),
// así se evita CORS y el cliente usa rutas relativas.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const commerceApiProxyTarget =
    env.VITE_COMMERCE_API_PROXY_TARGET || "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/commerce-api": {
          target: commerceApiProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/commerce-api/, "/api"),
        },
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

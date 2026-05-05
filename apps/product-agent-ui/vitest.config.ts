import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["src/test/setupTests.ts"],
    restoreMocks: true,
    clearMocks: true,
    unstubEnvs: true,
  },
});

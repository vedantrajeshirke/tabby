import { defineConfig } from "@playwright/test";

// Runs against its own throwaway stack, started by e2e/run.sh, so your local data is never touched.
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: { baseURL: process.env.E2E_URL ?? "http://127.0.0.1:5183" },
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 5184 --strictPort",
    url: "http://127.0.0.1:5184/",
    env: {
      VITE_SUPABASE_URL: "http://127.0.0.1:5184/fake-supabase",
      VITE_SUPABASE_PUBLISHABLE_KEY: "made-up-public-key",
    },
  },
  projects: [
    { name: "desktop", use: { browserName: "chromium", viewport: { width: 1280, height: 800 } } },
    { name: "phone", use: { browserName: "chromium", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});

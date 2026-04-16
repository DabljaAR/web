import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
    test: {
        globals: true,
        environment: "jsdom",
        setupFiles: "./src/test/setup.js",
        css: true,
        coverage: {
            provider: "v8",
            reporter: ["text", "json", "html"],
            reportsDirectory: "./coverage",
            // Keep coverage opt-in to avoid flaky V8 temp-file errors on normal test runs.
            // Use `npm run test:coverage` (or `vitest --coverage`) when you actually need reports.
            enabled: false,
            exclude: [
                "node_modules/",
                "dist/",
                "coverage/",
                "scripts/",

                // Tooling/config files
                "eslint.config.js",
                "postcss.config.js",
                "tailwind.config.js",
                "vite.config.ts",

                // Test utilities and test files
                "src/test/",
                "**/*.test.{js,jsx,ts,tsx}",
                "**/*.spec.{js,jsx,ts,tsx}",

                // Entry points / barrel files that don't contain runtime logic
                "src/main.{js,jsx,ts,tsx}",
                "src/**/index.{js,jsx,ts,tsx}",

                // Pure data/types
                "src/data/",
                "src/types/",
            ],
        },
        deps: {
          inline: ["@vitejs/plugin-react"],
        }
    },
});

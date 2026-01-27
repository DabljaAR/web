import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    test: {
        globals: true,
        environment: "jsdom",
        setupFiles: "./src/test/setup.js",
        css: true,
        coverage: {
            provider: "v8",
            reporter: ["text", "json", "html"],
            reportsDirectory: "./coverage",
            enabled: true,
            exclude: [
                "node_modules/",
                "src/test/",
                "**/*.test.{js,jsx}",
                "**/*.spec.{js,jsx}",
            ],
        },
        deps: {
          inline: ["@vitejs/plugin-react"],
        }
    },
});

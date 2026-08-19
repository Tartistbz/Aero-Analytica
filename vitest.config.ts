import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["repopilot/tests/**/*.test.ts"],
    environment: "node",
    reporters: ["default"],
  },
});

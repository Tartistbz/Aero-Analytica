import { describe, expect, it } from "vitest";
import { parseTask } from "../src/task/schema.js";

describe("task schema", () => {
  it("accepts a reproducible task and maps snake_case fields", () => {
    const task = parseTask({
      id: "demo-task",
      base_ref: "HEAD",
      prompt: "fix the parser",
      acceptance: { test_commands: ["node --version"], diff_policy: { allowed_paths: ["src/**"] } },
    });
    expect(task.baseRef).toBe("HEAD");
    expect(task.acceptance.testCommands).toEqual(["node --version"]);
    expect(task.acceptance.diffPolicy.maxFilesChanged).toBe(20);
  });

  it("rejects tasks without an acceptance gate", () => {
    expect(() => parseTask({ id: "invalid-task", base_ref: "HEAD", prompt: "do something" })).toThrow(/acceptance/i);
  });
});

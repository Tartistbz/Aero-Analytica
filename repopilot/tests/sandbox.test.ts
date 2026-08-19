import { describe, expect, it } from "vitest";
import { assertInside } from "../src/utils/fs.js";
import { assertSafeCommand } from "../src/sandbox/limits.js";

describe("sandbox limits", () => {
  it("rejects paths outside a worktree", () => {
    expect(() => assertInside("C:/repo", "../secrets.txt")).toThrow(/escapes/i);
  });

  it("rejects destructive shell commands", () => {
    expect(() => assertSafeCommand("git reset --hard HEAD")).toThrow(/safety/i);
  });
});

import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildRepoMap } from "../src/context/repo-map.js";
import { selectContext } from "../src/context/selector.js";
import { parseTask } from "../src/task/schema.js";

describe("context engine", () => {
  it("selects relevant files within the token budget", async () => {
    const root = await mkdtemp(join(tmpdir(), "repopilot-context-"));
    await mkdir(join(root, "src"));
    await mkdir(join(root, "test"));
    await writeFile(join(root, "src", "parser.ts"), "export function parserFix() { return true; }\n".repeat(20));
    await writeFile(join(root, "README.md"), "unrelated documentation\n".repeat(20));
    await writeFile(join(root, "test", "parser.test.ts"), "test parser regression\n".repeat(20));
    const task = parseTask({ id: "parser-context", base_ref: "HEAD", prompt: "fix parser regression", context: { strategy: "focused", budget_tokens: 90 }, acceptance: { assertions: [{ file_exists: "src/parser.ts" }] } });
    const context = await selectContext(root, task, await buildRepoMap(root));
    expect(context.selectedFiles).toContain("src/parser.ts");
    expect(context.estimatedTokens).toBeLessThanOrEqual(90);
    expect(context.droppedFiles.length).toBeGreaterThan(0);
  });

  it("clips compressed history instead of exceeding the budget", async () => {
    const root = await mkdtemp(join(tmpdir(), "repopilot-history-"));
    await writeFile(join(root, "src.ts"), "export const value = 1;\n");
    const task = parseTask({ id: "history-budget", base_ref: "HEAD", prompt: "inspect value", context: { strategy: "focused+history", budget_tokens: 120 }, acceptance: { assertions: [{ file_exists: "src.ts" }] } });
    const context = await selectContext(root, task, await buildRepoMap(root), "event: ".repeat(500));
    expect(context.estimatedTokens).toBeLessThanOrEqual(120);
    expect(context.history).toBeDefined();
  });
});

import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { promisify } from "node:util";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { FakeRuntime } from "../src/runtime/fake-runtime.js";
import { runTask } from "../src/runner/runner.js";
import { resumeTask } from "../src/runner/runner.js";
import { parseTask } from "../src/task/schema.js";
import { replayRun } from "../src/trace/replay.js";

const exec = promisify(execFile);

async function git(cwd: string, ...args: string[]): Promise<void> {
  await exec("git", args, { cwd, windowsHide: true });
}

describe("RepoPilot execution", () => {
  it("runs fake actions in an isolated worktree and verifies the diff", async () => {
    const root = await mkdtemp(join(tmpdir(), "repopilot-run-"));
    await mkdir(join(root, "src"));
    await writeFile(join(root, "src", "value.txt"), "old\n");
    await git(root, "init");
    await git(root, "config", "user.email", "repopilot@example.invalid");
    await git(root, "config", "user.name", "RepoPilot Test");
    await git(root, "add", ".");
    await git(root, "commit", "-m", "fixture");
    const task = parseTask({
      id: "isolated-edit",
      base_ref: "HEAD",
      prompt: "replace old with fixed",
      fake_actions: [{ tool: "patch", patch: "--- a/src/value.txt\n+++ b/src/value.txt\n@@ -1 +1 @@\n-old\n+fixed\n" }],
      acceptance: {
        test_commands: ["node -e \"const fs=require('fs'); if(fs.readFileSync('src/value.txt','utf8').trim()!=='fixed') process.exit(1)\""],
        diff_policy: { allowed_paths: ["src/**"], max_files_changed: 2, max_added_lines: 2, max_deleted_lines: 2 },
      },
    });
    const result = await runTask({ repoRoot: root, task, runtime: new FakeRuntime(), keepWorktree: true });
    expect(result.status).toBe("succeeded");
    expect(result.diff).toContain("fixed");
    const replay = await replayRun(result.runDir);
    expect(replay.toolCalls).toBe(1);
    expect(replay.finalStatus).toBe("succeeded");
    expect((await readFile(join(result.worktree, "src", "value.txt"), "utf8")).trim()).toBe("fixed");
  });

  it("retries an injected retryable tool failure", async () => {
    const root = await mkdtemp(join(tmpdir(), "repopilot-retry-"));
    await writeFile(join(root, "value.txt"), "old\n");
    await git(root, "init");
    await git(root, "config", "user.email", "repopilot@example.invalid");
    await git(root, "config", "user.name", "RepoPilot Test");
    await git(root, "add", ".");
    await git(root, "commit", "-m", "fixture");
    const task = parseTask({
      id: "retry-edit",
      base_ref: "HEAD",
      prompt: "replace old",
      fake_actions: [{ tool: "patch", patch: "--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-old\n+new\n" }],
      fault_injection: { enabled: true, fail_tool: "patch", fail_count: 1 },
      limits: { max_retries: 1 },
      acceptance: { assertions: [{ contains: { file: "value.txt", text: "new" } }], diff_policy: { allowed_paths: ["value.txt"] } },
    });
    const result = await runTask({ repoRoot: root, task, runtime: new FakeRuntime(), keepWorktree: true });
    expect(result.status).toBe("succeeded");
    const trace = await readFile(join(result.runDir, "events.jsonl"), "utf8");
    expect(trace).toContain("tool_retry");
  });

  it("resumes from a persisted checkpoint after an injected tool failure", async () => {
    const root = await mkdtemp(join(tmpdir(), "repopilot-resume-"));
    await writeFile(join(root, "value.txt"), "old\n");
    await git(root, "init");
    await git(root, "config", "user.email", "repopilot@example.invalid");
    await git(root, "config", "user.name", "RepoPilot Test");
    await git(root, "add", ".");
    await git(root, "commit", "-m", "fixture");
    const task = parseTask({
      id: "resume-edit",
      base_ref: "HEAD",
      prompt: "replace old",
      fake_actions: [{ tool: "patch", patch: "--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-old\n+resumed\n" }],
      fault_injection: { enabled: true, fail_tool: "patch", fail_count: 1 },
      limits: { max_retries: 0 },
      acceptance: { assertions: [{ contains: { file: "value.txt", text: "resumed" } }], diff_policy: { allowed_paths: ["value.txt"] } },
    });
    const first = await runTask({ repoRoot: root, task, runtime: new FakeRuntime(), keepWorktree: true });
    expect(first.status).toBe("failed");
    const checkpoint = JSON.parse(await readFile(join(first.runDir, "checkpoint.json"), "utf8"));
    const resumed = await resumeTask({ repoRoot: root, task, runtime: new FakeRuntime(), runDir: first.runDir, worktree: first.worktree, checkpoint, runId: first.runId, keepWorktree: true });
    expect(resumed.status).toBe("succeeded");
    expect((await readFile(join(resumed.worktree, "value.txt"), "utf8")).trim()).toBe("resumed");
  });
});

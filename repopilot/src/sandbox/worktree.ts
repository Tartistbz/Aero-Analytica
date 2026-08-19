import { mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { runProcess, runProcessFile } from "../utils/process.js";
import { exists } from "../utils/fs.js";

export type WorktreeHandle = {
  repoRoot: string;
  path: string;
  baseRef: string;
  remove: () => Promise<void>;
};

export async function createWorktree(repoRoot: string, baseRef: string, runId: string): Promise<WorktreeHandle> {
  const root = resolve(repoRoot);
  const worktree = resolve(root, ".repopilot", "worktrees", runId);
  await mkdir(dirname(worktree), { recursive: true });
  if (await exists(worktree)) throw new Error(`Worktree path already exists: ${worktree}`);
  const result = await runProcessFile("git", ["worktree", "add", "--detach", worktree, baseRef], {
    cwd: root,
    timeoutMs: 60_000,
    maxOutputBytes: 20_000,
  });
  if (!result.ok) throw new Error(`Unable to create worktree: ${result.output || `exit ${result.exitCode}`}`);
  return {
    repoRoot: root,
    path: worktree,
    baseRef,
    remove: async () => {
      const removal = await runProcessFile("git", ["worktree", "remove", "--force", worktree], {
        cwd: root,
        timeoutMs: 60_000,
        maxOutputBytes: 20_000,
      });
      if (!removal.ok && await exists(worktree)) await rm(worktree, { recursive: true, force: true });
    },
  };
}

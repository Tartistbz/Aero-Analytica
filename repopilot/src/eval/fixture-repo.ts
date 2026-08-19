import { cp, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { runProcess } from "../utils/process.js";

async function git(cwd: string, command: string): Promise<void> {
  const result = await runProcess(command, { cwd, timeoutMs: 60_000, maxOutputBytes: 50_000 });
  if (!result.ok) throw new Error(`Fixture Git setup failed: ${result.output || command}`);
}

/** Materializes a tracked fixture into a disposable repo with a fixed HEAD. */
export async function materializeFixture(source: string): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "repopilot-fixture-"));
  await cp(resolve(source), root, { recursive: true, force: true, filter: (path) => !path.includes(".git") && !path.includes(".repopilot") });
  await git(root, "git init -b main");
  await git(root, "git config user.email repopilot-fixture@example.invalid");
  await git(root, "git config user.name RepoPilot Fixture");
  await git(root, "git add -- .");
  await git(root, "git commit -m fixture-base");
  return root;
}

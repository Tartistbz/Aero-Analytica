import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { Assertion, TaskDefinition, VerificationResult } from "../types.js";
import { assertInside, matchesAny } from "../utils/fs.js";
import { runProcess } from "../utils/process.js";
import { assertSafeCommand, buildCommandEnv } from "../sandbox/limits.js";

type Check = { name: string; ok: boolean; output: string; durationMs: number };

async function commandCheck(worktree: string, command: string, timeoutMs: number, maxOutputBytes: number, name: string): Promise<Check> {
  assertSafeCommand(command);
  const result = await runProcess(command, { cwd: worktree, timeoutMs, maxOutputBytes, env: buildCommandEnv("disabled") });
  return { name, ok: result.ok, output: result.output || (result.ok ? "passed" : `exit ${result.exitCode}`), durationMs: result.durationMs };
}

async function assertionCheck(worktree: string, assertion: Assertion, timeoutMs: number, maxOutputBytes: number): Promise<Check> {
  const started = Date.now();
  if ("file_exists" in assertion) {
    try {
      await readFile(assertInside(worktree, assertion.file_exists));
      return { name: `file_exists:${assertion.file_exists}`, ok: true, output: "file exists", durationMs: Date.now() - started };
    } catch (error) {
      return { name: `file_exists:${assertion.file_exists}`, ok: false, output: error instanceof Error ? error.message : String(error), durationMs: Date.now() - started };
    }
  }
  if ("contains" in assertion) {
    try {
      const content = await readFile(assertInside(worktree, assertion.contains.file), "utf8");
      const ok = content.includes(assertion.contains.text);
      return { name: `contains:${assertion.contains.file}`, ok, output: ok ? "text found" : `missing text: ${assertion.contains.text}`, durationMs: Date.now() - started };
    } catch (error) {
      return { name: `contains:${assertion.contains.file}`, ok: false, output: error instanceof Error ? error.message : String(error), durationMs: Date.now() - started };
    }
  }
  assertSafeCommand(assertion.command);
  return commandCheck(worktree, assertion.command, timeoutMs, maxOutputBytes, `command:${assertion.command}`);
}

async function diffChecks(worktree: string, task: TaskDefinition): Promise<Check[]> {
  const started = Date.now();
  await runProcess("git add -N -- .", { cwd: worktree, timeoutMs: 30_000, maxOutputBytes: 20_000, env: buildCommandEnv("disabled") });
  const result = await runProcess("git diff --name-only", { cwd: worktree, timeoutMs: 30_000, maxOutputBytes: 100_000, env: buildCommandEnv("disabled") });
  if (!result.ok) return [{ name: "diff:read", ok: false, output: result.output, durationMs: result.durationMs }];
  const paths = result.output.split(/\r?\n/).map((path) => path.trim()).filter(Boolean);
  const policy = task.acceptance.diffPolicy;
  const denied = paths.filter((path) => matchesAny(path, policy.deniedPaths));
  const outside = paths.filter((path) => !matchesAny(path, policy.allowedPaths));
  const numstat = await runProcess("git diff --numstat", { cwd: worktree, timeoutMs: 30_000, maxOutputBytes: 100_000, env: buildCommandEnv("disabled") });
  let added = 0; let deleted = 0;
  for (const line of numstat.output.split(/\r?\n/)) {
    const match = line.match(/^(\d+)\s+(\d+)\s+/);
    if (match) { added += Number(match[1]); deleted += Number(match[2]); }
  }
  const ok = paths.length <= policy.maxFilesChanged && added <= policy.maxAddedLines && deleted <= policy.maxDeletedLines && denied.length === 0 && outside.length === 0;
  const detail = [`files=${paths.length}/${policy.maxFilesChanged}`, `added=${added}/${policy.maxAddedLines}`, `deleted=${deleted}/${policy.maxDeletedLines}`, denied.length ? `denied=${denied.join(",")}` : "denied=none", outside.length ? `outside=${outside.join(",")}` : "outside=none"].join(" ");
  return [{ name: "diff:policy", ok, output: detail, durationMs: Date.now() - started }];
}

export async function verifyWorktree(worktree: string, task: TaskDefinition): Promise<VerificationResult> {
  const checks: Check[] = [];
  for (const command of task.acceptance.testCommands) checks.push(await commandCheck(worktree, command, task.limits.timeoutSeconds * 1000, task.limits.maxOutputBytes, `test:${command}`));
  if (checks.some((check) => !check.ok)) return { ok: false, checks, failureCategory: "test" };
  for (const command of task.acceptance.lintCommands) checks.push(await commandCheck(worktree, command, task.limits.timeoutSeconds * 1000, task.limits.maxOutputBytes, `lint:${command}`));
  if (checks.some((check) => !check.ok)) return { ok: false, checks, failureCategory: "lint" };
  for (const assertion of task.acceptance.assertions) checks.push(await assertionCheck(worktree, assertion, task.limits.timeoutSeconds * 1000, task.limits.maxOutputBytes));
  if (checks.some((check) => !check.ok)) return { ok: false, checks, failureCategory: "assertion" };
  checks.push(...await diffChecks(worktree, task));
  if (checks.some((check) => !check.ok)) return { ok: false, checks, failureCategory: "diff" };
  return { ok: true, checks };
}

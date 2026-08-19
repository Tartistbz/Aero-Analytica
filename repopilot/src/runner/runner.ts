import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { randomUUID } from "node:crypto";
import type { AgentRuntime, Checkpoint, ContextPackage, RunResult, RuntimeOutput, TaskDefinition, ToolRegistry, ToolResult } from "../types.js";
import { buildRepoMap } from "../context/repo-map.js";
import { compressHistory } from "../context/history.js";
import { selectContext } from "../context/selector.js";
import { saveCheckpoint } from "../recovery/checkpoint.js";
import { withRetry } from "../recovery/retry.js";
import { createWorktree } from "../sandbox/worktree.js";
import { createToolRegistry, toolNames } from "../tools/registry.js";
import { TraceWriter } from "../trace/writer.js";
import { writeRunMetadata, writeRunReport } from "../trace/report.js";
import { runProcess } from "../utils/process.js";
import { assertSafeCommand, buildCommandEnv } from "../sandbox/limits.js";
import { verifyWorktree } from "../verify/verifier.js";

export type RunOptions = {
  repoRoot: string;
  task: TaskDefinition;
  runsDir?: string;
  runtime: AgentRuntime;
  runId?: string;
  existingWorktree?: string;
  resumeCheckpoint?: Checkpoint;
  keepWorktree?: boolean;
};

function initialCheckpoint(runId: string, taskId: string): Checkpoint {
  return { runId, taskId, savedAt: new Date().toISOString(), step: 0, completedActions: 0, state: "running" };
}

async function runSetup(worktree: string, task: TaskDefinition, trace: TraceWriter): Promise<boolean> {
  for (const command of task.setupCommands) {
    try { assertSafeCommand(command); } catch (error) {
      await trace.append("setup", { command, ok: false, error: error instanceof Error ? error.message : String(error) });
      return false;
    }
    const result = await runProcess(command, { cwd: worktree, timeoutMs: task.limits.timeoutSeconds * 1000, maxOutputBytes: task.limits.maxOutputBytes, env: buildCommandEnv(task.limits.network) });
    await trace.append("setup", { command, ...result });
    if (!result.ok) return false;
  }
  return true;
}

function instrumentTools(raw: ToolRegistry, trace: TraceWriter, checkpoint: Checkpoint, task: TaskDefinition, runDir: string): ToolRegistry {
  return Object.fromEntries(toolNames().map((name) => [name, async (input: unknown): Promise<ToolResult> => {
    await trace.append("tool_call", { tool: name, input });
    const result = await withRetry(
      () => raw[name](input),
      task.limits.maxRetries,
      async (attempt, retryResult) => { await trace.append("tool_retry", { tool: name, attempt, result: retryResult }); },
    );
    await trace.append("tool_result", { tool: name, result });
    checkpoint.step += 1;
    checkpoint.completedActions += result.ok ? 1 : 0;
    checkpoint.savedAt = new Date().toISOString();
    checkpoint.lastTool = name;
    checkpoint.lastResult = result;
    await saveCheckpoint(runDir, checkpoint);
    await trace.append("checkpoint_saved", { step: checkpoint.step, tool: name, ok: result.ok });
    return result;
  }])) as ToolRegistry;
}

async function getDiff(worktree: string, task: TaskDefinition): Promise<string> {
  const raw = createToolRegistry({ worktree, task });
  const result = await raw.git_diff({ mode: "full" });
  return result.output;
}

async function runInternal(options: RunOptions, trace: TraceWriter, runDir: string, worktree: string, checkpoint: Checkpoint, isResume: boolean): Promise<RunResult> {
  await trace.append(isResume ? "run_resumed" : "run_started", { runId: trace.runId, taskId: options.task.id, repoRoot: options.repoRoot, worktree, baseRef: options.task.baseRef });
  await writeRunMetadata(runDir, { runId: trace.runId, taskId: options.task.id, repoRoot: options.repoRoot, worktree, baseRef: options.task.baseRef, task: options.task, startedAt: new Date().toISOString() });
  if (!isResume && !(await runSetup(worktree, options.task, trace))) {
    checkpoint.state = "failed";
    await saveCheckpoint(runDir, checkpoint);
    const verification = { ok: false, checks: [{ name: "setup", ok: false, output: "Setup command failed", durationMs: 0 }], failureCategory: "runtime" as const };
    const result: RunResult = { runId: trace.runId, taskId: options.task.id, status: "failed", runDir, worktree, verification, diff: await getDiff(worktree, options.task), failureCategory: "runtime" };
    await trace.append("run_finished", { status: result.status, failureCategory: result.failureCategory });
    await writeRunReport(runDir, result);
    return result;
  }
  const repoMap = await buildRepoMap(worktree);
  const context = await selectContext(worktree, options.task, repoMap, compressHistory(trace.getEvents().map((event) => ({ type: event.type, payload: event.payload }))));
  await writeFile(join(runDir, "context.json"), JSON.stringify(context, null, 2), "utf8");
  await trace.append("context_selected", { strategy: context.strategy, selectedFiles: context.selectedFiles, droppedFiles: context.droppedFiles, estimatedTokens: context.estimatedTokens, budgetTokens: context.budgetTokens });
  checkpoint.injectedFailures ??= {};
  const rawTools = createToolRegistry({ worktree, task: options.task, faultState: checkpoint.injectedFailures });
  const tools = instrumentTools(rawTools, trace, checkpoint, options.task, runDir);
  let runtime: RuntimeOutput | undefined;
  try {
    runtime = isResume ? await options.runtime.resume({ task: options.task, context, tools, trace, checkpoint }) : await options.runtime.start({ task: options.task, context, tools, trace, checkpoint });
  } catch (error) {
    checkpoint.state = "failed";
    await saveCheckpoint(runDir, checkpoint);
    await trace.append("runtime_error", { error: error instanceof Error ? error.message : String(error) });
  }
  checkpoint.state = "verifying";
  await saveCheckpoint(runDir, checkpoint);
  const verification = await verifyWorktree(worktree, options.task);
  if (!runtime?.completed) {
    verification.ok = false;
    verification.failureCategory = "runtime";
    verification.checks.push({ name: "runtime:agent", ok: false, output: runtime?.summary ?? "Agent runtime did not complete", durationMs: 0 });
  }
  await trace.append("verification", verification);
  const diff = await getDiff(worktree, options.task);
  await writeFile(join(runDir, "final.diff"), diff, "utf8");
  checkpoint.state = verification.ok ? "succeeded" : "failed";
  await saveCheckpoint(runDir, checkpoint);
  const status = verification.ok ? "succeeded" : "failed";
  const result: RunResult = { runId: trace.runId, taskId: options.task.id, status, runDir, worktree, verification, diff, runtime, context, failureCategory: verification.failureCategory };
  await trace.append("run_finished", { status, failureCategory: verification.failureCategory, toolCalls: runtime?.toolCalls ?? 0 });
  await writeRunReport(runDir, result);
  await writeRunMetadata(runDir, { runId: trace.runId, taskId: options.task.id, repoRoot: options.repoRoot, worktree, baseRef: options.task.baseRef, task: options.task, status, verification, finishedAt: new Date().toISOString() });
  if (status === "succeeded" && !options.keepWorktree && !options.existingWorktree) {
    const worktreeHandle = { path: worktree };
    await trace.append("worktree_cleanup", worktreeHandle);
  }
  return result;
}

export async function runTask(options: RunOptions): Promise<RunResult> {
  const repoRoot = resolve(options.repoRoot);
  const runId = options.runId ?? randomUUID();
  const runsDir = resolve(options.runsDir ?? join(repoRoot, ".repopilot", "runs"));
  await mkdir(runsDir, { recursive: true });
  const trace = await TraceWriter.create(runsDir, runId);
  const checkpoint = options.resumeCheckpoint ?? initialCheckpoint(runId, options.task.id);
  let worktree = options.existingWorktree;
  let handle: Awaited<ReturnType<typeof createWorktree>> | undefined;
  if (!worktree) {
    handle = await createWorktree(repoRoot, options.task.baseRef, runId);
    worktree = handle.path;
  }
  const result = await runInternal(options, trace, trace.runDir, worktree, checkpoint, Boolean(options.resumeCheckpoint));
  if (result.status === "succeeded" && handle && !options.keepWorktree) await handle.remove();
  return result;
}

export async function resumeTask(options: Omit<RunOptions, "runId" | "existingWorktree" | "resumeCheckpoint"> & { runDir: string; worktree: string; checkpoint: Checkpoint; runId: string }): Promise<RunResult> {
  const trace = await TraceWriter.create(resolve(options.runDir, ".."), options.runId);
  return runInternal({ ...options, existingWorktree: options.worktree, resumeCheckpoint: options.checkpoint }, trace, options.runDir, options.worktree, options.checkpoint, true);
}

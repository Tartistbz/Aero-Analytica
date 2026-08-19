#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { Command } from "commander";
import { parse } from "yaml";
import { FakeRuntime } from "./runtime/fake-runtime.js";
import { PiAgentRuntime } from "./runtime/pi-adapter.js";
import { loadTask, parseTask } from "./task/schema.js";
import { runTask, resumeTask } from "./runner/runner.js";
import { replayRun } from "./trace/replay.js";
import { writeRunReport } from "./trace/report.js";
import type { AgentRuntime, Checkpoint, TaskDefinition } from "./types.js";
import { materializeFixture } from "./eval/fixture-repo.js";
import { writeEvalReport, type EvalTaskRow } from "./eval/report.js";

function runtimeFor(name: string): AgentRuntime {
  if (name === "fake") return new FakeRuntime();
  if (name === "pi") return new PiAgentRuntime();
  throw new Error(`Unknown runtime: ${name}`);
}

function printResult(result: { runId: string; status: string; runDir: string; worktree: string; failureCategory?: string }): void {
  console.log(JSON.stringify({ runId: result.runId, status: result.status, failureCategory: result.failureCategory, runDir: result.runDir, worktree: result.worktree }, null, 2));
}

async function loadSuite(path: string): Promise<string[]> {
  const content = await readFile(resolve(path), "utf8");
  const raw = parse(content) as { tasks?: unknown };
  if (!Array.isArray(raw.tasks)) throw new Error("Eval suite must contain tasks: []");
  return raw.tasks.map((item) => typeof item === "string" ? item : (item as { task?: string }).task).filter((item): item is string => Boolean(item));
}

const program = new Command();
program.name("repopilot").description("Repository execution, verification and evaluation harness").version("0.1.0");

program.command("run")
  .requiredOption("--repo <path>", "repository root")
  .requiredOption("--task <path>", "task YAML")
  .option("--runtime <name>", "pi or fake", "pi")
  .option("--runs-dir <path>", "run artifact directory")
  .option("--keep-worktree", "keep worktree after success")
  .action(async (options: { repo: string; task: string; runtime: string; runsDir?: string; keepWorktree?: boolean }) => {
    const task = await loadTask(options.task);
    const result = await runTask({ repoRoot: options.repo, task, runtime: runtimeFor(options.runtime), runsDir: options.runsDir, keepWorktree: options.keepWorktree });
    printResult(result);
    if (result.status !== "succeeded") process.exitCode = 1;
  });

program.command("resume")
  .requiredOption("--run <path>", "run directory")
  .option("--runtime <name>", "pi or fake", "pi")
  .action(async (options: { run: string; runtime: string }) => {
    const runDir = resolve(options.run);
    const metadata = JSON.parse(await readFile(resolve(runDir, "metadata.json"), "utf8")) as { task: TaskDefinition; repoRoot: string; worktree: string; runId: string };
    const checkpoint = JSON.parse(await readFile(resolve(runDir, "checkpoint.json"), "utf8")) as Checkpoint;
    const result = await resumeTask({ runDir, repoRoot: metadata.repoRoot, task: metadata.task, worktree: metadata.worktree, checkpoint, runId: metadata.runId, runtime: runtimeFor(options.runtime) });
    printResult(result);
    if (result.status !== "succeeded") process.exitCode = 1;
  });

program.command("replay")
  .requiredOption("--run <path>", "run directory")
  .action(async (options: { run: string }) => {
    console.log(JSON.stringify(await replayRun(resolve(options.run)), null, 2));
  });

program.command("report")
  .requiredOption("--run <path>", "run directory")
  .option("--format <format>", "html", "html")
  .action(async (options: { run: string; format: string }) => {
    if (options.format !== "html") throw new Error("Only html reports are currently supported");
    const runDir = resolve(options.run);
    const metadata = JSON.parse(await readFile(resolve(runDir, "metadata.json"), "utf8")) as { taskId: string; runId: string; status: "succeeded" | "failed"; worktree: string; verification: TaskDefinition["acceptance"] | undefined };
    const finalDiff = await readFile(resolve(runDir, "final.diff"), "utf8").catch(() => "");
    const result = { runId: metadata.runId, taskId: metadata.taskId, status: metadata.status, runDir, worktree: metadata.worktree, diff: finalDiff, verification: (metadata.verification ?? { ok: false, checks: [] }) as never };
    console.log(await writeRunReport(runDir, result));
  });

program.command("eval")
  .requiredOption("--suite <path>", "suite YAML")
  .option("--repo <path>", "override repository for all tasks")
  .option("--runtime <name>", "pi or fake", "fake")
  .option("--strategy <name>", "context strategy override")
  .option("--report <path>", "write a static HTML evaluation report")
  .action(async (options: { suite: string; repo?: string; runtime: string; strategy?: "map-only" | "focused" | "focused+history"; report?: string }) => {
    const suite = resolve(options.suite);
    const taskPaths = await loadSuite(suite);
    const rows: EvalTaskRow[] = [];
    for (const taskPath of taskPaths) {
      const absoluteTask = resolve(dirname(suite), taskPath);
      const loaded = await loadTask(absoluteTask);
      const task = options.strategy ? { ...loaded, context: { ...loaded.context, strategy: options.strategy } } : loaded;
      const repoRoot = options.repo ?? task.repo ?? (task.fixture ? await materializeFixture(task.fixture) : process.cwd());
      const started = Date.now();
      const result = await runTask({ repoRoot, task, runtime: runtimeFor(options.runtime), keepWorktree: false });
      const replay = await replayRun(result.runDir);
      const testChecks = result.verification.checks.filter((check) => check.name.startsWith("test:"));
      rows.push({ id: task.id, status: result.status, failureCategory: result.failureCategory, runId: result.runId, runDir: result.runDir, toolCalls: result.runtime?.toolCalls ?? 0, contextTokens: result.context?.estimatedTokens ?? 0, selectedFiles: result.context?.selectedFiles.length ?? 0, durationMs: Date.now() - started, testPassed: testChecks.length > 0 && testChecks.every((check) => check.ok), recoveryCount: replay.timeline.filter((line) => line.endsWith("tool_retry") || line.endsWith("run_resumed")).length });
    }
    const succeeded = rows.filter((row) => row.status === "succeeded").length;
    const strategy = options.strategy ?? "task-defined";
    if (options.report) await writeEvalReport(resolve(options.report), suite, strategy, rows);
    console.log(JSON.stringify({ suite, strategy, total: rows.length, succeeded, successRate: rows.length ? succeeded / rows.length : 0, report: options.report ? resolve(options.report) : undefined, tasks: rows }, null, 2));
    if (succeeded !== rows.length) process.exitCode = 1;
  });

try {
  await program.parseAsync(process.argv);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}

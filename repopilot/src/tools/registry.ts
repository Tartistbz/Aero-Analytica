import { readFile } from "node:fs/promises";
import { relative } from "node:path";
import type { TaskDefinition, ToolName, ToolRegistry, ToolResult } from "../types.js";
import { assertInside, isRegularFile, matchesAny, walkFiles } from "../utils/fs.js";
import { runProcess } from "../utils/process.js";
import { assertSafeCommand, buildCommandEnv } from "../sandbox/limits.js";

type RegistryOptions = {
  worktree: string;
  task: TaskDefinition;
  faultState?: Record<string, number>;
  onToolResult?: (tool: ToolName, result: ToolResult) => Promise<void>;
};

function success(output: string, started: number, exitCode?: number): ToolResult {
  return { ok: true, output, exitCode, durationMs: Date.now() - started };
}

function failure(code: string, message: string, started: number, retryable = false, output = ""): ToolResult {
  return { ok: false, output, durationMs: Date.now() - started, error: { code, message, retryable } };
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") throw new Error("Tool input must be an object");
  return value as Record<string, unknown>;
}

export function createToolRegistry(options: RegistryOptions): ToolRegistry {
  const faultCounts = new Map<string, number>(Object.entries(options.faultState ?? {}));
  const invoke = async (tool: ToolName, action: () => Promise<ToolResult>): Promise<ToolResult> => {
    const started = Date.now();
    const fault = options.task.faultInjection;
    if (fault?.enabled && fault.failTool === tool) {
      const count = faultCounts.get(tool) ?? 0;
      if (count < (fault.failCount ?? 1)) {
        faultCounts.set(tool, count + 1);
        if (options.faultState) options.faultState[tool] = count + 1;
        const result = failure("INJECTED_FAILURE", `Injected failure for ${tool}`, started, true);
        await options.onToolResult?.(tool, result);
        return result;
      }
    }
    try {
      const result = await action();
      await options.onToolResult?.(tool, result);
      return result;
    } catch (error) {
      const result = failure("TOOL_EXCEPTION", error instanceof Error ? error.message : String(error), started, false);
      await options.onToolResult?.(tool, result);
      return result;
    }
  };

  const registry: ToolRegistry = {
    search: (input) => invoke("search", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const query = typeof record.query === "string" ? record.query : "";
      if (!query) return failure("INVALID_INPUT", "search.query is required", started);
      const regex = record.regex === true ? new RegExp(query, "im") : undefined;
      const glob = typeof record.glob === "string" ? record.glob : "**/*";
      const maxResults = typeof record.maxResults === "number" ? Math.max(1, Math.min(record.maxResults, 500)) : 100;
      const files = await walkFiles(options.worktree, { exclude: [".git/**", "node_modules/**", ".repopilot/**", "data/**"] });
      const results: string[] = [];
      for (const path of files.filter((candidate) => matchesAny(candidate, [glob]))) {
        if (!(await isRegularFile(assertInside(options.worktree, path)))) continue;
        const content = await readFile(assertInside(options.worktree, path), "utf8").catch(() => "");
        const lines = content.split(/\r?\n/);
        lines.forEach((line, index) => {
          const matched = regex ? regex.test(line) : line.toLowerCase().includes(query.toLowerCase());
          if (matched && results.length < maxResults) results.push(`${path}:${index + 1}: ${line.slice(0, 500)}`);
        });
        if (results.length >= maxResults) break;
      }
      return success(results.join("\n") || "No matches.", started);
    }),

    read: (input) => invoke("read", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const path = typeof record.path === "string" ? record.path : "";
      if (!path) return failure("INVALID_INPUT", "read.path is required", started);
      const absolute = assertInside(options.worktree, path);
      if (!(await isRegularFile(absolute))) return failure("NOT_FOUND", `File not found: ${path}`, started, false);
      const content = await readFile(absolute, "utf8");
      const startLine = typeof record.startLine === "number" ? Math.max(1, record.startLine) : 1;
      const endLine = typeof record.endLine === "number" ? Math.max(startLine, record.endLine) : startLine + 400;
      const selected = content.split(/\r?\n/).slice(startLine - 1, endLine).join("\n");
      return success(selected.slice(0, options.task.limits.maxOutputBytes), started);
    }),

    patch: (input) => invoke("patch", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const patch = typeof record.patch === "string" ? record.patch : "";
      if (!patch) return failure("INVALID_INPUT", "patch.patch is required", started);
      const result = await runProcess("git apply --whitespace=nowarn -", {
        cwd: options.worktree,
        timeoutMs: options.task.limits.timeoutSeconds * 1000,
        maxOutputBytes: options.task.limits.maxOutputBytes,
        env: buildCommandEnv(options.task.limits.network),
        input: patch,
      });
      if (!result.ok) return failure(result.timedOut ? "TIMEOUT" : "PATCH_FAILED", result.output || "git apply failed", started, result.timedOut, result.output);
      await runProcess("git add -N -- .", { cwd: options.worktree, timeoutMs: 30_000, maxOutputBytes: 20_000, env: buildCommandEnv(options.task.limits.network) });
      return success(result.output || "Patch applied.", started, result.exitCode);
    }),

    shell: (input) => invoke("shell", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const command = typeof record.command === "string" ? record.command : "";
      if (!command) return failure("INVALID_INPUT", "shell.command is required", started);
      assertSafeCommand(command);
      const result = await runProcess(command, {
        cwd: options.worktree,
        timeoutMs: options.task.limits.timeoutSeconds * 1000,
        maxOutputBytes: options.task.limits.maxOutputBytes,
        env: buildCommandEnv(options.task.limits.network),
      });
      if (!result.ok) return failure(result.timedOut ? "TIMEOUT" : "COMMAND_FAILED", result.timedOut ? "Command timed out" : `Command exited with ${result.exitCode}`, started, result.timedOut, result.output);
      return success(result.output, started, result.exitCode);
    }),

    test: (input) => invoke("test", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const command = typeof record.command === "string" ? record.command : "";
      if (!command) return failure("INVALID_INPUT", "test.command is required", started);
      assertSafeCommand(command);
      const result = await runProcess(command, {
        cwd: options.worktree,
        timeoutMs: options.task.limits.timeoutSeconds * 1000,
        maxOutputBytes: options.task.limits.maxOutputBytes,
        env: buildCommandEnv(options.task.limits.network),
      });
      if (!result.ok) return failure(result.timedOut ? "TIMEOUT" : "TEST_FAILED", result.timedOut ? "Test timed out" : `Test exited with ${result.exitCode}`, started, result.timedOut, result.output);
      return success(result.output, started, result.exitCode);
    }),

    git_diff: (input) => invoke("git_diff", async () => {
      const started = Date.now();
      const record = asRecord(input);
      const mode = record.mode === "stat" ? "--stat" : "--no-ext-diff";
      await runProcess("git add -N -- .", { cwd: options.worktree, timeoutMs: 30_000, maxOutputBytes: 20_000, env: buildCommandEnv(options.task.limits.network) });
      const result = await runProcess(`git diff ${mode}`, {
        cwd: options.worktree,
        timeoutMs: 60_000,
        maxOutputBytes: Math.max(options.task.limits.maxOutputBytes, 200_000),
        env: buildCommandEnv(options.task.limits.network),
      });
      if (!result.ok) return failure("GIT_FAILED", result.output || "git diff failed", started, false, result.output);
      return success(result.output || "Working tree is clean.", started, result.exitCode);
    }),
  };
  return registry;
}

export function toolNames(): ToolName[] {
  return ["search", "read", "patch", "shell", "test", "git_diff"];
}

export function relativeToolPath(worktree: string, path: string): string {
  return relative(worktree, assertInside(worktree, path)).replaceAll("\\", "/");
}

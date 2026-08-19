import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { parse } from "yaml";
import { z } from "zod";
import type { TaskDefinition } from "../types.js";

const assertionSchema = z.union([
  z.object({ file_exists: z.string().min(1) }),
  z.object({ contains: z.object({ file: z.string().min(1), text: z.string() }) }),
  z.object({ command: z.string().min(1) }),
]);

const taskSchema = z.object({
  id: z.string().regex(/^[a-z0-9][a-z0-9._-]+$/),
  repo: z.string().optional(),
  fixture: z.string().optional(),
  base_ref: z.string().min(1),
  prompt: z.string().min(1),
  setup: z.object({ commands: z.array(z.string()).default([]) }).default({ commands: [] }),
  context: z.object({
    strategy: z.enum(["map-only", "focused", "focused+history"]).default("focused"),
    budget_tokens: z.number().int().positive().default(12000),
    include: z.array(z.string()).default(["**/*"]),
    exclude: z.array(z.string()).default([".git/**", "node_modules/**", "data/**", ".repopilot/**"]),
  }).default({ strategy: "focused", budget_tokens: 12000, include: ["**/*"], exclude: [".git/**", "node_modules/**", "data/**", ".repopilot/**"] }),
  acceptance: z.object({
    test_commands: z.array(z.string()).default([]),
    lint_commands: z.array(z.string()).default([]),
    assertions: z.array(assertionSchema).default([]),
    diff_policy: z.object({
      allowed_paths: z.array(z.string()).default(["**/*"]),
      denied_paths: z.array(z.string()).default([".git/**", ".env", "*.key", "*.pem", ".aero-analytica/**"]),
      max_files_changed: z.number().int().nonnegative().default(20),
      max_added_lines: z.number().int().nonnegative().default(1000),
      max_deleted_lines: z.number().int().nonnegative().default(500),
    }).default({ allowed_paths: ["**/*"], denied_paths: [".git/**", ".env", "*.key", "*.pem", ".aero-analytica/**"], max_files_changed: 20, max_added_lines: 1000, max_deleted_lines: 500 }),
  }).default({ test_commands: [], lint_commands: [], assertions: [], diff_policy: { allowed_paths: ["**/*"], denied_paths: [".git/**", ".env", "*.key", "*.pem", ".aero-analytica/**"], max_files_changed: 20, max_added_lines: 1000, max_deleted_lines: 500 } }),
  limits: z.object({
    timeout_seconds: z.number().int().positive().default(900),
    max_retries: z.number().int().nonnegative().default(2),
    max_output_bytes: z.number().int().positive().default(50000),
    network: z.enum(["disabled", "enabled"]).default("disabled"),
  }).default({ timeout_seconds: 900, max_retries: 2, max_output_bytes: 50000, network: "disabled" }),
  fault_injection: z.object({
    enabled: z.boolean().default(false),
    fail_tool: z.string().optional(),
    fail_count: z.number().int().positive().default(1),
  }).optional(),
  fake_actions: z.array(z.union([
    z.object({ tool: z.literal("shell"), command: z.string().min(1) }),
    z.object({ tool: z.literal("patch"), patch: z.string().min(1) }),
  ])).optional(),
}).superRefine((value, context) => {
  const acceptanceCount = value.acceptance.test_commands.length + value.acceptance.lint_commands.length + value.acceptance.assertions.length;
  if (acceptanceCount === 0) context.addIssue({ code: z.ZodIssueCode.custom, path: ["acceptance"], message: "At least one test, lint, or assertion is required" });
  if (value.acceptance.diff_policy.allowed_paths.length === 0) context.addIssue({ code: z.ZodIssueCode.custom, path: ["acceptance", "diff_policy", "allowed_paths"], message: "allowed_paths must not be empty" });
});

export function parseTask(raw: unknown): TaskDefinition {
  const parsed = taskSchema.parse(raw);
  return {
    id: parsed.id,
    repo: parsed.repo,
    fixture: parsed.fixture,
    baseRef: parsed.base_ref,
    prompt: parsed.prompt,
    setupCommands: parsed.setup.commands,
    context: {
      strategy: parsed.context.strategy,
      budgetTokens: parsed.context.budget_tokens,
      include: parsed.context.include,
      exclude: parsed.context.exclude,
    },
    acceptance: {
      testCommands: parsed.acceptance.test_commands,
      lintCommands: parsed.acceptance.lint_commands,
      assertions: parsed.acceptance.assertions,
      diffPolicy: {
        allowedPaths: parsed.acceptance.diff_policy.allowed_paths,
        deniedPaths: parsed.acceptance.diff_policy.denied_paths,
        maxFilesChanged: parsed.acceptance.diff_policy.max_files_changed,
        maxAddedLines: parsed.acceptance.diff_policy.max_added_lines,
        maxDeletedLines: parsed.acceptance.diff_policy.max_deleted_lines,
      },
    },
    limits: {
      timeoutSeconds: parsed.limits.timeout_seconds,
      maxRetries: parsed.limits.max_retries,
      maxOutputBytes: parsed.limits.max_output_bytes,
      network: parsed.limits.network,
    },
    faultInjection: parsed.fault_injection ? {
      enabled: parsed.fault_injection.enabled,
      failTool: parsed.fault_injection.fail_tool,
      failCount: parsed.fault_injection.fail_count,
    } : undefined,
    fakeActions: parsed.fake_actions,
  };
}

export async function loadTask(filePath: string): Promise<TaskDefinition> {
  const absolute = resolve(filePath);
  const content = await readFile(absolute, "utf8");
  try {
    const raw = parse(content) as Record<string, unknown>;
    if (typeof raw.fixture === "string") raw.fixture = resolve(dirname(absolute), raw.fixture);
    if (typeof raw.repo === "string" && raw.repo.startsWith(".")) raw.repo = resolve(dirname(absolute), raw.repo);
    return parseTask(raw);
  } catch (error) {
    throw new Error(`Invalid task YAML ${absolute}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export const taskSchemaForTests = taskSchema;

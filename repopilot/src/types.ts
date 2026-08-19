import type { TraceWriter } from "./trace/writer.js";

export type ContextStrategy = "map-only" | "focused" | "focused+history";

export type Assertion =
  | { file_exists: string }
  | { contains: { file: string; text: string } }
  | { command: string };

export type DiffPolicy = {
  allowedPaths: string[];
  deniedPaths: string[];
  maxFilesChanged: number;
  maxAddedLines: number;
  maxDeletedLines: number;
};

export type TaskDefinition = {
  id: string;
  repo?: string;
  fixture?: string;
  baseRef: string;
  prompt: string;
  setupCommands: string[];
  context: {
    strategy: ContextStrategy;
    budgetTokens: number;
    include: string[];
    exclude: string[];
  };
  acceptance: {
    testCommands: string[];
    lintCommands: string[];
    assertions: Assertion[];
    diffPolicy: DiffPolicy;
  };
  limits: {
    timeoutSeconds: number;
    maxRetries: number;
    maxOutputBytes: number;
    network: "disabled" | "enabled";
  };
  faultInjection?: {
    enabled: boolean;
    failTool?: string;
    failCount?: number;
  };
  fakeActions?: Array<
    | { tool: "shell"; command: string }
    | { tool: "patch"; patch: string }
  >;
};

export type ToolName = "search" | "read" | "patch" | "shell" | "test" | "git_diff";

export type ToolResult = {
  ok: boolean;
  output: string;
  exitCode?: number;
  durationMs: number;
  error?: { code: string; message: string; retryable: boolean };
};

export type ToolHandler = (input: unknown) => Promise<ToolResult>;

export type ToolRegistry = Record<ToolName, ToolHandler>;

export type ContextPackage = {
  strategy: ContextStrategy;
  repoMap: string;
  selectedFiles: string[];
  droppedFiles: string[];
  files: Array<{ path: string; content: string; estimatedTokens: number }>;
  estimatedTokens: number;
  budgetTokens: number;
  history?: string;
};

export type RuntimeInput = {
  task: TaskDefinition;
  context: ContextPackage;
  tools: ToolRegistry;
  trace: TraceWriter;
  checkpoint: Checkpoint;
};

export type RuntimeOutput = {
  completed: boolean;
  summary: string;
  toolCalls: number;
  tokenUsage?: { input?: number; output?: number; total?: number };
};

export interface AgentRuntime {
  start(input: RuntimeInput): Promise<RuntimeOutput>;
  resume(input: RuntimeInput): Promise<RuntimeOutput>;
}

export type Checkpoint = {
  runId: string;
  taskId: string;
  savedAt: string;
  step: number;
  completedActions: number;
  state: "running" | "verifying" | "failed" | "succeeded";
  lastTool?: ToolName;
  lastResult?: ToolResult;
  injectedFailures?: Record<string, number>;
};

export type VerificationResult = {
  ok: boolean;
  checks: Array<{ name: string; ok: boolean; output: string; durationMs: number }>;
  failureCategory?: "test" | "lint" | "assertion" | "diff" | "runtime";
};

export type RunResult = {
  runId: string;
  taskId: string;
  status: "succeeded" | "failed" | "blocked";
  runDir: string;
  worktree: string;
  verification: VerificationResult;
  diff: string;
  runtime?: RuntimeOutput;
  context?: ContextPackage;
  failureCategory?: string;
};

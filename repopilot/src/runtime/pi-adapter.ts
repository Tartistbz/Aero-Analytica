import {
  AuthStorage,
  createAgentSession,
  createExtensionRuntime,
  defineTool,
  ModelRegistry,
  SessionManager,
  SettingsManager,
  type ResourceLoader,
} from "@mariozechner/pi-coding-agent";
import { Type, type Api, type Model } from "@mariozechner/pi-ai";
import type { AgentRuntime, RuntimeInput, RuntimeOutput, ToolName, ToolResult } from "../types.js";
import { runProcess } from "../utils/process.js";
import { toolNames } from "../tools/registry.js";

type PiAction = { tool: ToolName; input: unknown };

const toolDescriptions: Record<ToolName, string> = {
  search: "Search text in files inside the isolated worktree. Use glob to narrow files.",
  read: "Read a UTF-8 file inside the isolated worktree. Paths must be relative to the worktree.",
  patch: "Apply a standard unified diff inside the isolated worktree. Never write outside it.",
  shell: "Run a non-destructive command inside the isolated worktree. Commands are time-limited and safety filtered.",
  test: "Run a test command inside the isolated worktree. Use this to validate a change.",
  git_diff: "Read the current Git diff or diff stat from the isolated worktree.",
};

function contentFor(result: ToolResult): string {
  const status = result.ok ? "OK" : `ERROR ${result.error?.code ?? "TOOL_FAILED"}`;
  return `${status}\n${result.output || result.error?.message || "(no output)"}`;
}

function createRepoPilotTools(input: RuntimeInput) {
  const execute = (tool: ToolName, params: unknown) => input.tools[tool](params).then((result) => ({
    content: [{ type: "text" as const, text: contentFor(result) }],
    details: { ok: result.ok, durationMs: result.durationMs, exitCode: result.exitCode, error: result.error },
  }));
  return [
    defineTool({ name: "search", label: "Search", description: toolDescriptions.search, promptSnippet: "search({ query, glob?, regex?, maxResults? })", executionMode: "sequential", parameters: Type.Object({ query: Type.String(), glob: Type.Optional(Type.String()), regex: Type.Optional(Type.Boolean()), maxResults: Type.Optional(Type.Number()) }), execute: (_id, params) => execute("search", params) }),
    defineTool({ name: "read", label: "Read", description: toolDescriptions.read, promptSnippet: "read({ path, startLine?, endLine? })", executionMode: "sequential", parameters: Type.Object({ path: Type.String(), startLine: Type.Optional(Type.Number()), endLine: Type.Optional(Type.Number()) }), execute: (_id, params) => execute("read", params) }),
    defineTool({ name: "patch", label: "Patch", description: toolDescriptions.patch, promptSnippet: "patch({ patch }) with a standard unified diff", executionMode: "sequential", parameters: Type.Object({ patch: Type.String() }), execute: (_id, params) => execute("patch", params) }),
    defineTool({ name: "shell", label: "Shell", description: toolDescriptions.shell, promptSnippet: "shell({ command })", executionMode: "sequential", parameters: Type.Object({ command: Type.String() }), execute: (_id, params) => execute("shell", params) }),
    defineTool({ name: "test", label: "Test", description: toolDescriptions.test, promptSnippet: "test({ command })", executionMode: "sequential", parameters: Type.Object({ command: Type.String() }), execute: (_id, params) => execute("test", params) }),
    defineTool({ name: "git_diff", label: "Git Diff", description: toolDescriptions.git_diff, promptSnippet: "git_diff({ mode: 'full' | 'stat' })", executionMode: "sequential", parameters: Type.Object({ mode: Type.Optional(Type.Union([Type.Literal("full"), Type.Literal("stat")])) }), execute: (_id, params) => execute("git_diff", params) }),
  ];
}

function promptFor(input: RuntimeInput): string {
  const contextFiles = input.context.files.map((file) => `--- ${file.path} ---\n${file.content}`).join("\n\n");
  return [
    "You are RepoPilot running a bounded engineering task in an isolated Git worktree.",
    "Use only the six RepoPilot tools. Do not claim success until you run the relevant test tool and inspect git_diff.",
    "Patch accepts standard unified diff only. Keep every modification within the task diff policy.",
    `Task: ${input.task.prompt}`,
    `Acceptance tests: ${input.task.acceptance.testCommands.join("; ") || "none declared"}`,
    `Lint commands: ${input.task.acceptance.lintCommands.join("; ") || "none declared"}`,
    `Context strategy: ${input.context.strategy}; estimated tokens: ${input.context.estimatedTokens}/${input.context.budgetTokens}`,
    "Repository map:",
    input.context.repoMap,
    input.context.history ? `Compressed history:\n${input.context.history}` : "",
    contextFiles ? `Selected files:\n${contextFiles}` : "No file contents were selected. Search before editing.",
  ].join("\n\n");
}

function resourceLoader(systemPrompt: string): ResourceLoader {
  return {
    getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
    getSkills: () => ({ skills: [], diagnostics: [] }),
    getPrompts: () => ({ prompts: [], diagnostics: [] }),
    getThemes: () => ({ themes: [], diagnostics: [] }),
    getAgentsFiles: () => ({ agentsFiles: [] }),
    getSystemPrompt: () => systemPrompt,
    getAppendSystemPrompt: () => [],
    extendResources: () => {},
    reload: async () => {},
  };
}

function configuredHeaders(): Record<string, string> | undefined {
  const raw = process.env.REPOPILOT_PI_HEADERS;
  if (!raw) return undefined;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { throw new Error("REPOPILOT_PI_HEADERS must be valid JSON."); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("REPOPILOT_PI_HEADERS must be a JSON object.");
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>)
      .filter(([key]) => key.trim())
      .map(([key, value]) => [key.trim(), String(value)]),
  );
}

function configuredModel(registry: ModelRegistry, authStorage: AuthStorage): Model<Api> | undefined {
  const provider = process.env.REPOPILOT_PI_PROVIDER;
  const modelId = process.env.REPOPILOT_PI_MODEL;
  const apiKey = process.env.REPOPILOT_PI_API_KEY;
  const baseUrl = process.env.REPOPILOT_PI_BASE_URL;
  const api = (process.env.REPOPILOT_PI_API ?? "openai-completions") as Api;
  if (provider && modelId && baseUrl) {
    const headers = configuredHeaders();
    if (apiKey) authStorage.setRuntimeApiKey(provider, apiKey);
    registry.registerProvider(provider, {
      name: provider,
      baseUrl,
      api,
      apiKey: apiKey ?? `REPOPILOT_PI_API_KEY_${provider.toUpperCase().replaceAll(/[^A-Z0-9]/g, "_")}`,
      headers,
      authHeader: api === "openai-completions",
      models: [{ id: modelId, name: modelId, reasoning: false, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 128000, maxTokens: 16384 }],
    });
    return registry.find(provider, modelId);
  }
  if (provider && modelId) return registry.find(provider, modelId);
  return registry.getAvailable()[0];
}

/**
 * Pi SDK runtime. Pi controls its agent loop; RepoPilot owns the worktree,
 * context package, tools, verification, recovery and trace artifacts.
 */
export class PiAgentRuntime implements AgentRuntime {
  private async executeWithSdk(input: RuntimeInput): Promise<RuntimeOutput> {
    const authStorage = AuthStorage.create();
    const modelRegistry = ModelRegistry.create(authStorage);
    const model = configuredModel(modelRegistry, authStorage);
    if (!model) throw new Error("No Pi model is configured. Configure Pi credentials, or set REPOPILOT_PI_PROVIDER, REPOPILOT_PI_MODEL, REPOPILOT_PI_BASE_URL and REPOPILOT_PI_API_KEY.");
    const tools = createRepoPilotTools(input);
    const prompt = promptFor(input);
    const cwd = input.context.repoMap.match(/^Repository root: (.+)$/m)?.[1] ?? process.cwd();
    const { session } = await createAgentSession({
      cwd,
      model,
      authStorage,
      modelRegistry,
      resourceLoader: resourceLoader("You are a controlled repository agent. Follow the user task and use RepoPilot tools only."),
      customTools: tools,
      noTools: "all",
      tools: toolNames(),
      sessionManager: SessionManager.inMemory(cwd),
      settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: true, maxRetries: input.task.limits.maxRetries } }),
    });
    let assistantText = "";
    session.subscribe((event) => {
      if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") assistantText += event.assistantMessageEvent.delta;
    });
    await input.trace.append("model_request", { provider: model.provider, model: model.id, promptChars: prompt.length, toolNames: toolNames() });
    await session.prompt(prompt, { source: "extension" });
    const stats = session.getSessionStats();
    const errored = session.agent.state.errorMessage;
    await input.trace.append("model_response", { provider: model.provider, model: model.id, outputChars: assistantText.length, tokenUsage: stats.tokens, toolCalls: stats.toolCalls, error: errored });
    session.dispose();
    return { completed: !errored, summary: assistantText || "Pi session completed.", toolCalls: stats.toolCalls, tokenUsage: { input: stats.tokens.input, output: stats.tokens.output, total: stats.tokens.total } };
  }

  private async executeBridge(input: RuntimeInput): Promise<RuntimeOutput> {
    const command = process.env.REPOPILOT_PI_BRIDGE_COMMAND;
    if (!command) return this.executeWithSdk(input);
    const payload = { task: input.task, context: input.context, checkpoint: input.checkpoint, tools: toolNames() };
    const result = await runProcess(command, { cwd: process.cwd(), timeoutMs: input.task.limits.timeoutSeconds * 1000, maxOutputBytes: input.task.limits.maxOutputBytes * 4, env: { ...process.env, REPOPILOT_TOOL_PROTOCOL: "json" }, input: JSON.stringify(payload) });
    if (!result.ok) throw new Error(`Pi bridge failed: ${result.output || result.exitCode}`);
    let parsed: { actions?: PiAction[]; summary?: string; tokenUsage?: RuntimeOutput["tokenUsage"] };
    try { parsed = JSON.parse(result.output) as typeof parsed; } catch { throw new Error("Pi bridge returned invalid JSON"); }
    let toolCalls = 0;
    for (const action of parsed.actions ?? []) {
      const handler = input.tools[action.tool];
      if (!handler) throw new Error(`Pi requested unknown tool: ${action.tool}`);
      const toolResult = await handler(action.input);
      toolCalls += 1;
      if (!toolResult.ok) return { completed: false, summary: toolResult.error?.message ?? toolResult.output, toolCalls, tokenUsage: parsed.tokenUsage };
    }
    return { completed: true, summary: parsed.summary ?? "Pi bridge completed.", toolCalls, tokenUsage: parsed.tokenUsage };
  }

  async start(input: RuntimeInput): Promise<RuntimeOutput> { return this.executeBridge(input); }
  async resume(input: RuntimeInput): Promise<RuntimeOutput> { return this.executeBridge(input); }
}

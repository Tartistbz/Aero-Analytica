import type { AgentRuntime, RuntimeInput, RuntimeOutput, ToolName } from "../types.js";

export class FakeRuntime implements AgentRuntime {
  async start(input: RuntimeInput): Promise<RuntimeOutput> {
    const actions = input.task.fakeActions ?? [];
    let toolCalls = 0;
    for (const action of actions.slice(input.checkpoint.completedActions)) {
      const tool: ToolName = action.tool;
      const result = action.tool === "shell"
        ? await input.tools.shell({ command: action.command })
        : await input.tools.patch({ patch: action.patch });
      toolCalls += 1;
      if (!result.ok) return { completed: false, summary: result.error?.message ?? result.output, toolCalls };
    }
    return { completed: true, summary: actions.length ? "Fake action script completed." : "Fake runtime had no actions.", toolCalls };
  }

  async resume(input: RuntimeInput): Promise<RuntimeOutput> {
    return this.start(input);
  }
}

import type { Checkpoint } from "../types.js";

export function compressHistory(events: Array<{ type: string; payload: unknown }>, maxChars = 12_000): string {
  const lines = events.slice(-80).map((event) => `${event.type}: ${JSON.stringify(event.payload)}`);
  const joined = lines.join("\n");
  return joined.length <= maxChars ? joined : `[history truncated]\n${joined.slice(-maxChars)}`;
}

export function checkpointSummary(checkpoint: Checkpoint): string {
  return `step=${checkpoint.step} completed_actions=${checkpoint.completedActions} state=${checkpoint.state} last_tool=${checkpoint.lastTool ?? "none"}`;
}

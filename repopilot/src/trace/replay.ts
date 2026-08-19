import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { TraceEvent } from "./writer.js";

export type ReplaySummary = {
  runId: string;
  eventCount: number;
  toolCalls: number;
  verificationEvents: number;
  finalStatus?: string;
  timeline: string[];
};

export async function loadTrace(runDir: string): Promise<TraceEvent[]> {
  const text = await readFile(join(runDir, "events.jsonl"), "utf8");
  return text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as TraceEvent);
}

export async function replayRun(runDir: string): Promise<ReplaySummary> {
  const events = await loadTrace(runDir);
  const finished = [...events].reverse().find((event) => event.type === "run_finished");
  return {
    runId: runDir.split(/[\\/]/).pop() ?? "unknown",
    eventCount: events.length,
    toolCalls: events.filter((event) => event.type === "tool_call").length,
    verificationEvents: events.filter((event) => event.type === "verification").length,
    finalStatus: finished && typeof finished.payload === "object" && finished.payload ? String((finished.payload as Record<string, unknown>).status ?? "") : undefined,
    timeline: events.map((event) => `${event.timestamp} ${event.type}`),
  };
}

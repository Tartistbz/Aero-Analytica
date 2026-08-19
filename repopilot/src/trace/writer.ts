import { access, appendFile, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export type TraceEvent = {
  eventId: string;
  timestamp: string;
  type: string;
  payload: unknown;
};

function redact(value: unknown): unknown {
  if (typeof value === "string") {
    return value
      .replace(/(api[_-]?key|authorization|token|secret|password)(\s*[=:]\s*)([^\s,;"']+)/gi, "$1$2[REDACTED]")
      .replace(/sk-[A-Za-z0-9_-]{10,}/g, "[REDACTED_TOKEN]")
      .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [REDACTED]");
  }
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    const sensitiveKey = /^(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization|cookie)$/i;
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, sensitiveKey.test(key) ? "[REDACTED]" : redact(item)]));
  }
  return value;
}

export class TraceWriter {
  public readonly runId: string;
  public readonly runDir: string;
  public readonly eventsPath: string;
  private readonly events: TraceEvent[] = [];

  private constructor(runId: string, runDir: string) {
    this.runId = runId;
    this.runDir = runDir;
    this.eventsPath = join(runDir, "events.jsonl");
  }

  static async create(baseDir: string, runId: string = randomUUID()): Promise<TraceWriter> {
    const runDir = join(baseDir, runId);
    await mkdir(join(runDir, "checkpoints"), { recursive: true });
    const writer = new TraceWriter(runId, runDir);
    try { await access(writer.eventsPath); } catch { await writeFile(writer.eventsPath, "", "utf8"); }
    return writer;
  }

  async append(type: string, payload: unknown): Promise<TraceEvent> {
    const event: TraceEvent = { eventId: randomUUID(), timestamp: new Date().toISOString(), type, payload: redact(payload) };
    this.events.push(event);
    await appendFile(this.eventsPath, `${JSON.stringify(event)}\n`, "utf8");
    return event;
  }

  getEvents(): TraceEvent[] { return [...this.events]; }
}

export { redact };

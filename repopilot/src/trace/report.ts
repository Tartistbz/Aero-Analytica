import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { replayRun } from "./replay.js";
import type { RunResult } from "../types.js";

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

export async function writeRunMetadata(runDir: string, metadata: Record<string, unknown>): Promise<void> {
  await writeFile(join(runDir, "metadata.json"), JSON.stringify(metadata, null, 2), "utf8");
}

export async function writeRunReport(runDir: string, result: RunResult): Promise<string> {
  const replay = await replayRun(runDir);
  const reportPath = join(runDir, "report.html");
  const checks = result.verification.checks.map((check) => `<tr><td>${escapeHtml(check.name)}</td><td class="${check.ok ? "ok" : "bad"}">${check.ok ? "PASS" : "FAIL"}</td><td><pre>${escapeHtml(check.output)}</pre></td></tr>`).join("");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>RepoPilot ${escapeHtml(result.taskId)}</title><style>body{font:14px system-ui;margin:2rem;max-width:1100px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:.5rem;vertical-align:top}.ok{color:#087f23}.bad{color:#b42318}pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#f6f8fa;padding:.5rem}.metric{display:inline-block;margin-right:2rem}</style></head><body><h1>RepoPilot run</h1><p><strong>Status:</strong> ${escapeHtml(result.status)}</p><p><span class="metric"><strong>Run:</strong> ${escapeHtml(result.runId)}</span><span class="metric"><strong>Tool calls:</strong> ${replay.toolCalls}</span><span class="metric"><strong>Events:</strong> ${replay.eventCount}</span></p><h2>Verification</h2><table><tr><th>Check</th><th>Result</th><th>Output</th></tr>${checks}</table><h2>Diff</h2><pre>${escapeHtml(result.diff || "Working tree is clean.")}</pre><h2>Timeline</h2><pre>${escapeHtml(replay.timeline.join("\n"))}</pre></body></html>`;
  await writeFile(reportPath, html, "utf8");
  return reportPath;
}

export async function readRunMetadata(runDir: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(join(runDir, "metadata.json"), "utf8")) as Record<string, unknown>;
}

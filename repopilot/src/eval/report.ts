import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export type EvalTaskRow = {
  id: string;
  status: string;
  failureCategory?: string;
  runId: string;
  runDir: string;
  toolCalls: number;
  contextTokens: number;
  selectedFiles: number;
  durationMs: number;
  testPassed: boolean;
  recoveryCount: number;
};

function escapeHtml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

export async function writeEvalReport(path: string, suite: string, strategy: string, tasks: EvalTaskRow[]): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const succeeded = tasks.filter((task) => task.status === "succeeded").length;
  const testPassed = tasks.filter((task) => task.testPassed).length;
  const totalTools = tasks.reduce((sum, task) => sum + task.toolCalls, 0);
  const totalDuration = tasks.reduce((sum, task) => sum + task.durationMs, 0);
  const totalRecovery = tasks.reduce((sum, task) => sum + task.recoveryCount, 0);
  const rows = tasks.map((task) => `<tr><td>${escapeHtml(task.id)}</td><td class="${task.status === "succeeded" ? "ok" : "bad"}">${escapeHtml(task.status)}</td><td>${escapeHtml(task.failureCategory ?? "-")}</td><td>${task.testPassed ? "PASS" : "FAIL"}</td><td>${task.toolCalls}</td><td>${task.contextTokens}</td><td>${task.selectedFiles}</td><td>${task.recoveryCount}</td><td>${task.durationMs}</td><td>${escapeHtml(task.runDir)}</td></tr>`).join("");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>RepoPilot Eval Report</title><style>body{font:14px system-ui;margin:2rem;max-width:1400px}.metrics{display:flex;gap:2rem;flex-wrap:wrap}.metric{padding:.75rem 1rem;border:1px solid #ddd}.ok{color:#087f23}.bad{color:#b42318}table{border-collapse:collapse;width:100%;margin-top:1.5rem}th,td{border:1px solid #ddd;padding:.45rem;vertical-align:top;text-align:left}td:last-child{font-family:ui-monospace;font-size:12px}</style></head><body><h1>RepoPilot evaluation</h1><p>Suite: ${escapeHtml(suite)}<br>Context strategy: ${escapeHtml(strategy)}</p><div class="metrics"><div class="metric">Tasks<br><strong>${tasks.length}</strong></div><div class="metric">Success rate<br><strong>${tasks.length ? ((succeeded / tasks.length) * 100).toFixed(1) : "0.0"}%</strong></div><div class="metric">Test pass rate<br><strong>${tasks.length ? ((testPassed / tasks.length) * 100).toFixed(1) : "0.0"}%</strong></div><div class="metric">Tool calls<br><strong>${totalTools}</strong></div><div class="metric">Wall time<br><strong>${totalDuration} ms</strong></div><div class="metric">Recoveries<br><strong>${totalRecovery}</strong></div></div><table><tr><th>Task</th><th>Status</th><th>Failure</th><th>Tests</th><th>Tools</th><th>Context tokens</th><th>Files</th><th>Recoveries</th><th>Duration ms</th><th>Run artifacts</th></tr>${rows}</table></body></html>`;
  await writeFile(path, html, "utf8");
}

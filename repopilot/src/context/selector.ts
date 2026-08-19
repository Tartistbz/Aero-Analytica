import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { ContextPackage, TaskDefinition } from "../types.js";
import { matchesAny } from "../utils/fs.js";
import type { RepoMap } from "./repo-map.js";

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function score(path: string, prompt: string, role: string): number {
  const lower = path.toLowerCase();
  const words = prompt.toLowerCase().split(/[^a-z0-9_]+/).filter((word) => word.length > 2);
  // Implementation files get a small priority over tests for fix tasks so a
  // constrained context still includes code the agent can change.
  let value = role === "source" ? 6 : role === "test" ? 3 : role === "entrypoint" ? 5 : 1;
  for (const word of words) if (lower.includes(word)) value += 8;
  if (/test|spec/.test(lower) && /test|bug|fix|regression/.test(prompt.toLowerCase())) value += 4;
  if (/src|source|lib/.test(lower)) value += 2;
  return value;
}

export async function selectContext(root: string, task: TaskDefinition, repoMap: RepoMap, history = ""): Promise<ContextPackage> {
  const allowed = repoMap.files.filter((file) => matchesAny(file.path, task.context.include) && !matchesAny(file.path, task.context.exclude));
  const ranked = [...allowed].sort((a, b) => score(b.path, task.prompt, b.role) - score(a.path, task.prompt, a.role) || a.path.localeCompare(b.path));
  const candidates = task.context.strategy === "map-only" ? [] : ranked;
  const budget = task.context.budgetTokens;
  const mapBudgetChars = Math.max(160, Math.floor(budget * 4 * 0.3));
  const compactMap = repoMap.summary.slice(0, mapBudgetChars);
  const selected: ContextPackage["files"] = [];
  let total = estimateTokens(compactMap);
  for (const file of candidates) {
    if (total >= budget) break;
    const content = await readFile(join(root, file.path), "utf8").catch(() => "");
    const remaining = Math.max(0, budget - total - 32);
    const maxChars = remaining * 4;
    const clipped = content.slice(0, maxChars);
    const tokens = estimateTokens(clipped);
    if (tokens === 0) continue;
    selected.push({ path: file.path, content: clipped, estimatedTokens: tokens });
    total += tokens;
  }
  let selectedHistory: string | undefined;
  if (task.context.strategy === "focused+history" && history && total < budget) {
    selectedHistory = history.slice(0, Math.max(0, (budget - total) * 4));
    total += estimateTokens(selectedHistory);
  }
  const selectedPaths = new Set(selected.map((file) => file.path));
  return {
    strategy: task.context.strategy,
    repoMap: compactMap,
    selectedFiles: selected.map((file) => file.path),
    droppedFiles: allowed.filter((file) => !selectedPaths.has(file.path)).map((file) => file.path),
    files: selected,
    estimatedTokens: total,
    budgetTokens: budget,
    history: selectedHistory,
  };
}

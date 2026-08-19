import { access, readdir, stat } from "node:fs/promises";
import { constants } from "node:fs";
import { relative, resolve, sep } from "node:path";

export async function exists(path: string): Promise<boolean> {
  try { await access(path, constants.F_OK); return true; } catch { return false; }
}

export function assertInside(root: string, candidate: string): string {
  const absoluteRoot = resolve(root);
  const absoluteCandidate = resolve(root, candidate);
  const rel = relative(absoluteRoot, absoluteCandidate);
  if (rel === ".." || rel.startsWith(`..${sep}`) || rel.includes(`..${sep}`)) {
    throw new Error(`Path escapes worktree: ${candidate}`);
  }
  return absoluteCandidate;
}

export function globToRegExp(pattern: string): RegExp {
  let expression = "";
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index];
    if (char === "*") {
      if (pattern[index + 1] === "*") {
        expression += ".*";
        index += 1;
      } else {
        expression += "[^/]*";
      }
    } else if (char === "?") {
      expression += "[^/]";
    } else {
      expression += char?.replace(/[\\^$+?.()|{}[\]]/g, "\\$&") ?? "";
    }
  }
  return new RegExp(`^${expression}$`, "i");
}

export function matchesAny(path: string, patterns: string[]): boolean {
  const normalized = path.replaceAll("\\", "/");
  return patterns.some((pattern) => globToRegExp(pattern).test(normalized));
}

export async function walkFiles(root: string, options: { exclude?: string[] } = {}): Promise<string[]> {
  const results: string[] = [];
  const excluded = options.exclude ?? [];
  async function visit(directory: string): Promise<void> {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const absolute = resolve(directory, entry.name);
      const relativePath = relative(root, absolute).replaceAll("\\", "/");
      if (matchesAny(relativePath, excluded) || matchesAny(`${relativePath}/`, excluded)) continue;
      if (entry.isDirectory()) await visit(absolute);
      else if (entry.isFile()) results.push(relativePath);
    }
  }
  await visit(resolve(root));
  return results.sort();
}

export async function isRegularFile(path: string): Promise<boolean> {
  try { return (await stat(path)).isFile(); } catch { return false; }
}

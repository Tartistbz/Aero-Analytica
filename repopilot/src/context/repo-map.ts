import { readFile } from "node:fs/promises";
import { extname } from "node:path";
import { matchesAny, walkFiles } from "../utils/fs.js";

const ignored = [".git/**", "node_modules/**", ".repopilot/**", "data/**", "dist/**", "build/**"];

export type RepoMap = {
  root: string;
  files: Array<{ path: string; bytes: number; language: string; role: string }>;
  summary: string;
};

function languageFor(path: string): string {
  const extension = extname(path).toLowerCase();
  const languages: Record<string, string> = {
    ".ts": "TypeScript", ".tsx": "TypeScript/React", ".js": "JavaScript", ".py": "Python",
    ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML", ".json": "JSON", ".toml": "TOML",
    ".cpp": "C++", ".h": "C/C++", ".hpp": "C++", ".rs": "Rust", ".go": "Go", ".sh": "Shell",
  };
  return languages[extension] ?? (extension ? extension.slice(1).toUpperCase() : "text");
}

function roleFor(path: string): string {
  const lower = path.toLowerCase();
  if (/readme|architecture|docs?/.test(lower)) return "documentation";
  if (/test|spec|fixture/.test(lower)) return "test";
  if (/package|requirements|config|\.json$|\.ya?ml$|\.toml$/.test(lower)) return "configuration";
  if (/main|app|index|cli|entry/.test(lower)) return "entrypoint";
  return "source";
}

export async function buildRepoMap(root: string): Promise<RepoMap> {
  const paths = (await walkFiles(root, { exclude: ignored })).filter((path) => !matchesAny(path, ["*.bin", "*.ulg", "*.tlog"]));
  const files: RepoMap["files"] = [];
  for (const path of paths) {
    let bytes = 0;
    try { bytes = (await readFile(`${root}/${path}`)).byteLength; } catch { bytes = 0; }
    files.push({ path, bytes, language: languageFor(path), role: roleFor(path) });
  }
  const byLanguage = new Map<string, number>();
  for (const file of files) byLanguage.set(file.language, (byLanguage.get(file.language) ?? 0) + 1);
  const languageSummary = [...byLanguage.entries()].sort((a, b) => b[1] - a[1]).map(([language, count]) => `${language}:${count}`).join(", ");
  const lines = [
    `Repository root: ${root}`,
    `Files: ${files.length}`,
    `Languages: ${languageSummary || "unknown"}`,
    "",
    ...files.map((file) => `${file.path} | ${file.language} | ${file.role} | ${file.bytes} bytes`),
  ];
  return { root, files, summary: lines.join("\n") };
}

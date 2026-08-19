import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { Checkpoint } from "../types.js";

export async function saveCheckpoint(runDir: string, checkpoint: Checkpoint): Promise<string> {
  const path = join(runDir, "checkpoints", `${String(checkpoint.step).padStart(5, "0")}.json`);
  await writeFile(path, JSON.stringify(checkpoint, null, 2), "utf8");
  await writeFile(join(runDir, "checkpoint.json"), JSON.stringify(checkpoint, null, 2), "utf8");
  return path;
}

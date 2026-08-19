import { spawn } from "node:child_process";

export type ProcessResult = {
  ok: boolean;
  output: string;
  exitCode: number;
  durationMs: number;
  timedOut: boolean;
};

export async function runProcess(command: string, options: {
  cwd: string;
  timeoutMs: number;
  maxOutputBytes: number;
  env?: NodeJS.ProcessEnv;
  input?: string;
}): Promise<ProcessResult> {
  return runSpawn(command, [], { ...options, shell: true });
}

export async function runProcessFile(file: string, args: string[], options: {
  cwd: string;
  timeoutMs: number;
  maxOutputBytes: number;
  env?: NodeJS.ProcessEnv;
  input?: string;
}): Promise<ProcessResult> {
  return runSpawn(file, args, { ...options, shell: false });
}

async function runSpawn(command: string, args: string[], options: {
  cwd: string;
  timeoutMs: number;
  maxOutputBytes: number;
  env?: NodeJS.ProcessEnv;
  input?: string;
  shell: boolean;
}): Promise<ProcessResult> {
  const started = Date.now();
  return await new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      shell: options.shell,
      env: options.env,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let output = "";
    let timedOut = false;
    const append = (chunk: Buffer): void => {
      if (output.length < options.maxOutputBytes) output += chunk.toString("utf8").slice(0, options.maxOutputBytes - output.length);
    };
    child.stdout.on("data", append);
    child.stderr.on("data", append);
    if (options.input) child.stdin.write(options.input);
    child.stdin.end();
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 250);
    }, options.timeoutMs);
    child.on("error", (error) => {
      clearTimeout(timer);
      resolve({ ok: false, output: `${output}${error.message}`, exitCode: -1, durationMs: Date.now() - started, timedOut });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const exitCode = typeof code === "number" ? code : -1;
      resolve({ ok: !timedOut && exitCode === 0, output, exitCode, durationMs: Date.now() - started, timedOut });
    });
  });
}

const dangerousCommands = [
  /(^|\s)git\s+reset\s+--hard/i,
  /(^|\s)git\s+clean\s+-[a-z]*f/i,
  /(^|\s)(rm|del|rmdir)\s+(-[a-z]+\s+)*["']?([A-Za-z]:[\\/]|\/|\.)/i,
  /(^|\s)format\s+[A-Za-z]:/i,
];

export function assertSafeCommand(command: string): void {
  if (dangerousCommands.some((pattern) => pattern.test(command))) {
    throw new Error("Command rejected by safety policy");
  }
}

export function buildCommandEnv(network: "disabled" | "enabled"): NodeJS.ProcessEnv {
  const env = { ...process.env };
  if (network === "disabled") {
    env.REPOPILOT_NETWORK = "disabled";
    env.NO_PROXY = "*";
    env.no_proxy = "*";
  }
  return env;
}

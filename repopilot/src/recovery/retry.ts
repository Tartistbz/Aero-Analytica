import type { ToolResult } from "../types.js";

export async function withRetry<T extends ToolResult>(action: () => Promise<T>, maxRetries: number, onRetry?: (attempt: number, result: T) => Promise<void>): Promise<T> {
  let attempt = 0;
  while (true) {
    const result = await action();
    if (result.ok || !result.error?.retryable || attempt >= maxRetries) return result;
    attempt += 1;
    await onRetry?.(attempt, result);
    await new Promise((resolve) => setTimeout(resolve, Math.min(250 * (2 ** (attempt - 1)), 2_000)));
  }
}

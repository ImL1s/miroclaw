// extensions/mirofish/src/tools.ts
import type { RunManager } from "./run-manager.js";

interface Logger {
  info: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

/** Shape of NDJSON events emitted by the CLI process. */
interface RunEvent {
  type?: string;
  event?: string;
  runId?: string;
  reportId?: string;
  simId?: string;
  error?: string;
  message?: string;
  [key: string]: unknown;
}

/**
 * Create MiroFish agent tools for OpenClaw.
 * The LLM invokes these as function calls (Path C).
 */
export function createMirofishTools(runManager: RunManager, log: Logger) {
  return [
    {
      name: "mirofish_predict",
      description:
        "Run a MiroFish multi-agent prediction simulation. " +
        "55 AI agents simulate social media discussions (Twitter/Reddit) about a given topic, " +
        "then generate a consensus prediction report. Takes 10-30 minutes.",
      parameters: {
        type: "object" as const,
        properties: {
          topic: {
            type: "string",
            description:
              "The prediction topic or scenario to simulate, e.g. '如果比特幣突破15萬美元'",
          },
          rounds: {
            type: "number",
            description:
              "Number of simulation rounds (default: 20, recommended: 10-20 for testing, 30-40 for production)",
          },
        },
        required: ["topic"],
      },
      async execute(
        _toolCallId: string,
        { topic, rounds }: { topic: string; rounds?: number },
      ): Promise<string> {
        log.info(
          `[mirofish_predict] topic="${topic}" rounds=${rounds ?? 20}`,
        );

        // Check idempotency cache
        const hash = runManager.questionHash(topic);
        const cached = runManager.getCachedResult(hash);
        if (cached) {
          return JSON.stringify({
            status: "cached",
            reportId: cached,
            message: `This topic was recently predicted. Report ID: ${cached}.`,
          });
        }

        // Check capacity
        if (!runManager.canSpawn()) {
          return JSON.stringify({
            status: "busy",
            message: "Maximum concurrent predictions reached. Try again later.",
            activeRuns: runManager.getActiveRuns().size,
          });
        }

        // Spawn prediction (non-blocking — return runId immediately)
        const result = runManager.spawn(topic, {
          onEvent(evt: unknown) {
            const event = evt as RunEvent;
            if (event.event === "run:done" && event.reportId) {
              runManager.cacheResult(hash, event.reportId);
              log.info(`[mirofish_predict] complete: reportId=${event.reportId}`);
            }
          },
        });

        if (!result) {
          return JSON.stringify({
            status: "error",
            message: "Failed to start prediction.",
          });
        }

        return JSON.stringify({
          status: "started",
          runId: result.runId,
          topic,
          message: `Prediction started (run ID: ${result.runId}). Use mirofish_status tool with this runId to check progress. Takes 10-30 minutes.`,
        });
      },
    },
    {
      name: "mirofish_status",
      description: "Check the status of an active MiroFish prediction run.",
      parameters: {
        type: "object" as const,
        properties: {
          runId: {
            type: "string",
            description: "The run ID returned by mirofish_predict",
          },
        },
        required: ["runId"],
      },
      async execute(_toolCallId: string, { runId }: { runId: string }): Promise<string> {
        const runs = runManager.getActiveRuns();
        const run = runs.get(runId);

        if (!run) {
          return JSON.stringify({
            status: "not_found",
            message: `No active run with ID "${runId}".`,
          });
        }

        const elapsed = Math.round((Date.now() - run.startedAt) / 1000);
        return JSON.stringify({
          status: "running",
          runId,
          topic: run.topic,
          elapsedSeconds: elapsed,
        });
      },
    },
  ];
}

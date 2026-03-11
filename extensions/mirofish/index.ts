/**
 * MiroFish x OpenClaw Extension
 *
 * Thin shell that:
 * 1. Registers agent tools (Path C)
 * 2. Registers message hooks (Path B)
 * 3. Registers gateway RPC methods (control plane)
 * 4. Serves Canvas HTML for report visualization
 *
 * All business logic delegated to mirofish-cli child process.
 */

// These imports will be created in subsequent tasks.
// For now, comment them out and create a minimal skeleton.

// Minimal type definitions (will be replaced by openclaw SDK types later)
interface PluginApi {
  id: string;
  logger: {
    info: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  };
  pluginConfig?: Record<string, unknown>;
  registerTool: (tool: unknown) => void;
  registerHook: (
    events: string | string[],
    handler: (...args: unknown[]) => unknown,
  ) => void;
  registerGatewayMethod: (
    method: string,
    handler: (opts: unknown) => Promise<void> | void,
  ) => void;
  registerHttpRoute: (params: unknown) => void;
  registerService: (service: {
    id: string;
    start: (ctx: unknown) => void | Promise<void>;
    stop?: (ctx: unknown) => void | Promise<void>;
  }) => void;
}

const plugin = {
  id: "mirofish",
  name: "MiroFish Prediction Engine",
  description:
    "55-agent social simulation prediction engine with P2P consensus",
  version: "0.1.0",

  register(api: PluginApi) {
    const log = api.logger;
    log.info("[MiroFish] Extension loading...");

    // TODO: Task 4 — RunManager
    // TODO: Task 5 — Agent tools (Path C)
    // TODO: Task 6 — Message hook (Path B)
    // TODO: Task 7 — Gateway RPC methods
    // TODO: Task 8 — Canvas route

    api.registerService({
      id: "mirofish-run-manager",
      start() {
        log.info("[MiroFish] Extension loaded (stub).");
      },
      stop() {
        log.info("[MiroFish] Extension stopped.");
      },
    });
  },
};

export default plugin;

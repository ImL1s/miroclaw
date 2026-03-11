# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

MiroFish OpenClaw Extension — a plugin that integrates the MiroFish 55-agent social simulation prediction engine into the OpenClaw AI agent framework. All heavy lifting is delegated to the `mirofish` CLI binary via child processes; this extension is a thin integration shell.

## Build & Test

```bash
npx tsc                                    # Build (outputs to dist/)
npx tsc --noEmit                           # Type-check only
npx tsc --watch                            # Dev mode
node --test dist/src/__tests__/*.test.js   # Run all tests
node --test dist/src/__tests__/run-manager.test.js  # Single test file
```

After building, deploy to OpenClaw:
```bash
cp -r dist/* ~/.openclaw/extensions/mirofish/dist/
```

## Architecture

The extension registers 5 integration points via `register(api)` in `index.ts`:

1. **Agent Tools** (`src/tools.ts`) — LLM-callable tools: `mirofish_predict` (non-blocking, returns runId immediately), `mirofish_status`
2. **Message Hook** (`src/hooks.ts`) — Auto-trigger predictions from chat when keywords match (disabled by default)
3. **Gateway RPC** (`src/gateway.ts`) — 4 methods: `mirofish.predict`, `mirofish.status`, `mirofish.cancel`, `mirofish.list`
4. **Canvas Route** (`src/canvas-route.ts`) — `GET /mirofish/canvas` serves report visualization HTML
5. **Service Lifecycle** — RunManager start/stop with orphan process cleanup

All paths funnel through **RunManager** (`src/run-manager.ts`), which manages CLI child processes with: concurrent limits, message deduplication, idempotency caching (TTL-based), timeout enforcement (SIGTERM → 5s → SIGKILL), and dual-key run tracking.

## Key Patterns

- **OpenClaw tool execute signature**: `execute(toolCallId: string, params: object)` — NOT `execute(params)`. The first arg is always the tool call ID.
- **OpenClaw hook registration**: Third arg required: `api.registerHook(events, handler, { name: "..." })`
- **OpenClaw HTTP route auth**: Must include `auth: "gateway"` or `auth: "plugin"` in route params.
- **NDJSON protocol**: CLI spawned with `--json-stream` flag. Events parsed from stdout line-by-line. Key events: `run:start`, `step:start/progress/done`, `run:done` (with `reportId`, `simId`), `run:error`, `run:cancelled`.
- **Dual-key RunManager**: Both temp `run-{timestamp}` and real UUID from CLI point to the same `ActiveRun` object in the Map. Deduplication in list endpoints uses `Set` with object identity.
- **Discord webhook**: Read from `MIROFISH_DISCORD_WEBHOOK` env var (not plugin config — OpenClaw validates config fields strictly).

## Environment

- **`MIROFISH_DISCORD_WEBHOOK`**: Discord webhook URL for start/complete/cancel/error notifications
- **Plugin config** (`openclaw.plugin.json`): `backendUrl`, `maxConcurrent`, `autoTrigger`
- **Default backend**: `http://localhost:5001`
- **Default CLI binary**: `mirofish` (from PATH)

## Testing Against OpenClaw Gateway

```bash
# Start gateway (needs Node 22+)
nvm use 22
MIROFISH_DISCORD_WEBHOOK="..." openclaw gateway

# RPC calls
openclaw gateway call mirofish.predict --params '{"topic": "..."}'
openclaw gateway call mirofish.status --params '{"runId": "run-xxx"}'
openclaw gateway call mirofish.cancel --params '{"runId": "run-xxx"}'
openclaw gateway call mirofish.list --params '{}'

# Agent tool test
openclaw agent --agent main -m "檢查 mirofish 推演狀態"
```

Gateway logs: `/private/tmp/openclaw-gateway.log`

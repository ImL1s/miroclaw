CLAUDE.md
AGENTS.md
GEMINI.md

This file provides guidance to AI coding agents (Claude Code, Gemini, etc.) when working with code in this repository.

## Project Overview

MiroClaw is an integration project combining [MiroFish](https://github.com/666ghj/MiroFish) (a multi-agent simulation engine featuring 55 AI Agents) and OpenClaw. It packages the swarm intelligence deduction engine into a Node.js CLI tool (`mirofish-cli`) and an OpenClaw skill.

### Vision: Decentralized Swarm Intelligence Prediction Protocol
1. **Deduction Layer**: MiroFish Engine (GraphRAG + OASIS multi-agent simulation + Report AI)
2. **Agent Layer**: OpenClaw Gateway Network (P2P communication, Task dispatch)
3. **Consensus Layer**: Cosmos SDK AppChain (Optional - for on-chain attestation & reputation)

## Architecture & Repository Structure

```
miro_claw/
├── cli/                  # mirofish-cli npm package (Node.js)
│   ├── bin/mirofish.js   # CLI entry point
│   ├── lib/              # Core logic: predict pipeline, docker/native daemon
│   ├── lib/p2p.js        # P2P broadast (seeds/results)
│   ├── lib/meta-report.js# Multi-node consensus analysis
│   └── test/             # CLI Unit & E2E Tests (Mocha/native)
├── skills/               # OpenClaw skill (e.g., mirofish-predict)
├── MiroFish/             # Core Engine (Submodule - Python/Vue)
│   ├── backend/          # Python Flask API (:5001)
│   │   ├── app/api/      # Blueprints: graph, simulation, report, p2p
│   │   └── run.py        # Entry point
│   └── frontend/         # Vue 3 + Vite SPA (:3000)
└── .env                  # Global configurations (ZEP_API_KEY, LLM_API_KEY)
```

### Core Prediction Pipeline (7-step Async Flow)
1. `POST /api/graph/ontology/generate` (LLM extracts ontology)
2. `POST /api/graph/build` (Build Zep GraphRAG)
3. `POST /api/simulation/prepare` (Generate Camel-OASIS agent profiles)
4. `POST /api/simulation/start` (Spawn OASIS simulation subprocess)
5. `GET /api/simulation/<id>/run-status` (Poll completion)
6. `POST /api/report/generate` (Autonomous Report Agent analyzes output)
7. CLI Launch Canvas (optional)

### P2P Distributed Simulation Architecture
* **Peers**: Configured locally via `mirofish peers add <url>`.
* **Seed Broadcast**: CLI sends to peer's `POST /api/p2p/predict`.
* **Auto-Predict**: If peer has `P2P_AUTO_PREDICT=true`, Flask backend (`p2p.py`) spawns a background `node mirofish.js predict ... --p2p-reply-only` process to natively run the engine.
* **Results Collection**: CLI queries `GET /api/p2p/results` from peers and uses `lib/meta-report.js` to merge JSON reports into a formatted consensus summary.

## Development Commands

**Full Stack (MiroFish Core)**
* Setup: `cd MiroFish && npm run setup:all` (Installs Node modules & uv venv)
* Dev Server (Frontend + Backend): `cd MiroFish && npm run dev`
* Backend Only: `cd MiroFish && npm run backend`
* Frontend Only: `cd MiroFish && npm run frontend`

**Testing**
* Python Backend (pytest): `cd MiroFish/backend && uv run pytest tests -v`
* CLI Unit Tests: `cd cli && node test/peer-config.test.js && node test/p2p.test.js && node test/meta-report.test.js`
* Full P2P E2E Integration: `bash cli/test/e2e-p2p.sh`

**Local CLI Testing**
* `node cli/bin/mirofish.js predict "Topic" --rounds=10`
* `node cli/bin/mirofish.js meta "Topic"` (P2P consensus)

## Technical Decisions & Conventions

* **Python Backend**: Uses Flask factory pattern, Blueprints, and `uv` for dependency management (`backend/pyproject.toml`). Use 4-space indent, `snake_case`.
* **JavaScript/Node**: Uses 2-space indent, single quotes, minimal semi-colons.
* **LLM & Memory**: Employs OpenAI SDK wrapper (configurable base URLs) to support any local/remote model (often local LM Studio running on `192.168.x.x`). Uses Zep Cloud for the GraphRAG layer.
* **Commits**: Follow Conventional Commits format (e.g., `feat(p2p): add auto-predict`, `fix(cli): fix timeout`).
* **Test Hygiene**: Ensure test isolation. Avoid modifying global state in tests without teardown (e.g., use mock files or reset fetch mocks via `try/finally`). E2E testing uses live port binding (e.g. 5091/5092) with rigorous cleanup traps.

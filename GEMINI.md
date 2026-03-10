# MiroClaw - Project Guidelines

This file provides context and instructions for AI agents working in this repository.

## Project Overview

MiroClaw is an integration project combining [MiroFish](https://github.com/666ghj/MiroFish) (a multi-agent simulation engine featuring 55 AI Agents) and OpenClaw. It packages the swarm intelligence deduction engine into a Node.js CLI tool (`mirofish-cli`) and an OpenClaw skill.

The core objective is to create a decentralized swarm intelligence prediction protocol. The architecture consists of three layers:
1. **Deduction Layer**: MiroFish Engine (Simulating a social platform like Twitter/Reddit)
2. **Agent Layer**: OpenClaw Gateway
3. **Consensus Layer**: Cosmos SDK (Optional)

The project structure is divided into:
- `MiroFish/`: The core application as a submodule (Python Flask Backend on port 5001, Vue 3 + Vite Frontend on port 3000).
- `cli/`: The Node.js CLI wrapper (`mirofish-cli`).
- `skills/`: OpenClaw skill definitions (e.g., `mirofish-predict`).
- `docs/`: Vision and planning documentation.

## Building and Running

### CLI Usage

*   **Global Install**: `npm install -g mirofish-cli`
*   **Start Daemon**: `mirofish serve start` (Initializes config, creates `~/.mirofish/.env` template, uses Docker by default or `uv run` natively as a fallback).
*   **Run Prediction**: `mirofish predict "If Bitcoin hits $150k, what happens to the crypto market?"`
*   **View Report**: `mirofish report <simulation_id>`
*   **Chat with Simulation**: `mirofish chat <simulation_id> "Which KOLs are most extreme?"`

### Development (MiroFish Core)

The core application lives in the `MiroFish` directory.

*   **Setup All Dependencies** (Node + Python): `cd MiroFish && npm run setup:all`
*   **Run Both Frontend and Backend** (Dev Mode): `cd MiroFish && npm run dev`
*   **Run Backend Only**: `cd MiroFish && npm run backend`
*   **Run Frontend Only**: `cd MiroFish && npm run frontend`
*   **Run Backend Tests**: `cd MiroFish/backend && uv run pytest`
*   **Test CLI Locally**: `node cli/bin/mirofish.js predict "Topic" --rounds=10`

### Docker

*   Start via Docker Compose: `cd MiroFish && docker compose up -d`
*   Build image from source: `docker build -t mirofish .`

## Development Conventions

*   **Python Dependency Management**: Use `uv` (not `pip`) for managing Python packages in `MiroFish/backend`. Virtual environments are located at `backend/.venv`.
*   **Backend Architecture**: The Python backend uses Flask with a factory pattern (`app/__init__.py -> create_app()`) and Blueprints (`graph`, `simulation`, `report`).
*   **Frontend Architecture**: The frontend is a Vue 3 SPA built with Vite. The dev server proxies `/api` requests to `localhost:5001`.
*   **Core Pipeline Workflow**: The prediction process is an asynchronous 6-step pipeline:
    1. Seed document upload & Ontology generation via LLM.
    2. Knowledge Graph construction (Zep GraphRAG).
    3. Simulation preparation (generating agent profiles via camel-oasis).
    4. Start OASIS multi-agent simulation (runs as a subprocess).
    5. Poll simulation status.
    6. Autonomous Report Agent generates the final analysis using Zep tools.
*   **APIs & External Services**: 
    - **LLM**: Follows OpenAI SDK format (configurable via `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`).
    - **Memory/Graph**: Uses Zep Cloud (`ZEP_API_KEY` required).
*   **OpenClaw Skill**: To install the prediction skill, run `clawhub install mirofish-predict` in OpenClaw.

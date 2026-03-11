# Distributed Agent Execution — NetworkChannel Fork Design

## Goal

Split 55 OASIS agents across multiple machines, keeping Platform (SQLite + RecSys) centralized on a Coordinator, with Workers running LLM calls remotely via gRPC.

## Design Decisions

| # | Decision | Choice | Rationale |
|:--|:---|:---|:---|
| 1 | Architecture | Fork OASIS, replace Channel | Smallest change surface (~300 LOC modified) |
| 2 | Network protocol | **gRPC** (bidirectional streaming) | Strong typing, mature Python ecosystem, fits request-response pattern |
| 3 | Platform concurrency | **Keep serial** | Bottleneck is LLM (~secs), not SQL (<1ms). Avoids SQLite race conditions |
| 4 | Agent distribution | **Static Round-Robin** | Simple, predictable, easy to debug |
| 5 | Profile delivery | **Coordinator pushes via gRPC** | Workers are pure compute nodes, no filesystem dependency |
| 6 | LLM configuration | **Per-Worker** (self-managed) | Aligns with P2P philosophy; enables model diversity |
| 7 | Code location | **`miro_claw/oasis-distributed/`** | Co-located with project for easy development |
| 8 | Node discovery | **libp2p DHT + IPFS bootstrap + mDNS + GitHub fallback** | Zero self-hosted infra required |

## Architecture

```
                 ┌──────────────────────────┐
                 │      Coordinator         │
                 │                          │
                 │  Platform (SQLite DB)    │
                 │  RecSys                  │
                 │  gRPC ChannelServer      │
                 │  libp2p DHT node         │
                 │  GossipSub publisher     │
                 └──────────┬───────────────┘
            ┌───────────────┼───────────────┐
       ┌────▼────┐     ┌───▼─────┐    ┌────▼────┐
       │Worker 1 │     │Worker 2 │    │Worker N │
       │Agt 0-17 │     │Agt 18-35│    │Agt 36-54│
       │LLM: X   │     │LLM: Y   │    │LLM: Z   │
       │gRPC cli │     │gRPC cli │    │gRPC cli │
       │libp2p   │     │libp2p   │    │libp2p   │
       └─────────┘     └─────────┘    └─────────┘
```

## Per-Round Data Flow

```
1. Coordinator: platform.update_rec_table()
2. Coordinator → all Workers: gRPC StartRound(round_num, active_agent_ids)
3. Workers: each agent calls LLM → decides action
4. Workers → Coordinator: gRPC SendAction(agent_id, action, message)
5. Coordinator: Platform processes action (SQL) → returns result
6. Coordinator → Worker: gRPC ActionResponse(result)
7. Workers → Coordinator: gRPC RoundComplete()
8. Coordinator: barrier sync → time_step += 1 → next round
```

## Node Discovery (3-Layer)

```
Node startup
  ├─ Layer 1: mDNS (LAN, zero cost)
  ├─ Layer 2: IPFS public DHT (WAN, zero infra)
  │   → content-route: /mirofish/1.0.0
  │   → GossipSub topic: mirofish/simulations
  └─ Layer 3: GitHub known-peers.json (fallback)
```

When Coordinator wants workers:
1. Publish simulation request to GossipSub
2. Nodes that receive it auto-decide to join (based on local policy: idle, topic match, etc.)
3. Joining Worker sends its gRPC endpoint to Coordinator
4. Coordinator assigns agents → simulation begins

## Files to Change

### New files (~600 LOC)
| File | Purpose |
|:---|:---|
| `oasis/network/__init__.py` | Package init |
| `oasis/network/proto/channel.proto` | gRPC service definition |
| `oasis/network/channel_server.py` | Coordinator gRPC server |
| `oasis/network/channel_client.py` | Worker gRPC client |
| `oasis/network/coordinator.py` | Agent grouping, barrier sync |
| `oasis/network/worker.py` | Worker process manager |
| `oasis/network/discovery.py` | libp2p DHT + mDNS + fallback |

### Modified files (~100 LOC changes)
| File | Change |
|:---|:---|
| `oasis/social_platform/channel.py` | Add `NetworkChannel(Channel)` subclass |
| `oasis/environment/env.py` | Add `DistributedOasisEnv(OasisEnv)` subclass |

## Implementation Phases

| Phase | Work | Est. Time |
|:---|:---|:---|
| **1** | NetworkChannel (gRPC) + single-machine multi-process test | 3-4 days |
| **2** | Docker multi-node | 2-3 days |
| **3** | MiroFish CLI integration (`--distributed` flag) | 2-3 days |
| **4** | libp2p discovery layer | 3-4 days |
| **5** | Fault tolerance + upstream PR | 3-5 days |
| **Total** | | **~3 weeks** |

## Lifecycle Management

### Completion Detection (Barrier Sync)

```
Each round:
  Coordinator sends StartRound → records "need X Workers to report"
  Each Worker finishes → sends RoundComplete
  Coordinator receives X RoundCompletes → ✅ round done
  round_num == total_rounds → SimulationComplete → all Workers disconnect
```

Timeout: If a Worker hasn't sent `RoundComplete` within 15 min, log warning but **keep waiting** (LLM can be slow). No auto-skip in v1.

### Disconnection Handling

| Scenario | Detection | Response (v1) |
|:---|:---|:---|
| **Worker drops** | gRPC heartbeat timeout (10s interval) | Mark Worker's agents as "orphaned", skip them this round |
| **Coordinator drops** | Worker's gRPC connection breaks | Workers pause, retry reconnect every 30s |
| **Worker graceful exit** (Ctrl+C) | Worker sends `Unregister` RPC | Coordinator skips those agents going forward |

Orphaned agents simply don't act that round — OASIS already supports "not every agent is active every round", so this is safe.

Agent migration to surviving Workers deferred to Phase 5.

### Shutdown Flow

**Normal completion:**
```
All rounds done
  → Coordinator: gRPC SimulationComplete(sim_id, SUCCESS) → all Workers
  → Workers: cleanup agents → disconnect gRPC → return to idle (GossipSub listening)
  → Coordinator: generate Report → done
```

**User abort (Ctrl+C / API cancel):**
```
  → Coordinator: gRPC SimulationAbort(reason) → all Workers
  → Workers: cancel in-flight LLM calls → cleanup → disconnect
  → Coordinator: save partial results to SQLite → exit
```

### Report Distribution & Notification

```
Simulation complete
  → Coordinator generates Report
  → gRPC SimulationComplete(report_data) → all Workers get full report
  → GossipSub broadcast report summary to mirofish/reports topic
  → Each Worker saves to ~/.mirofish/reports/<sim_id>.md
  → OpenClaw Extension triggers notify.js → Gateway push to owner
  → Owner gets notified on Discord/TG: "模擬完成！主題: BTC走勢, 3節點共同推演"
```

All participants get the full report. Observers on GossipSub get summary only.

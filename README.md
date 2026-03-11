# MiroClaw

[MiroFish](https://github.com/666ghj/MiroFish) × [OpenClaw](https://openclaw.ai) — 群體智能推演引擎 CLI + OpenClaw Skill

## 什麼是 MiroClaw？

將 MiroFish 的 55 AI Agent 群體智能推演引擎包裝成 CLI 工具 + OpenClaw skill，讓你用一句話推演未來趨勢。

```bash
mirofish predict "如果比特幣突破15萬美元，加密市場會怎樣？"
```

## 安裝

```bash
npm install -g mirofish-cli
```

### 前置需求

- **Node.js** ≥ 18
- **Docker Desktop**（推薦）或 **Python + uv**（Apple Silicon fallback）
- **LLM API key**（支援任何 OpenAI 格式端點）
- **ZEP API key**（免費：https://app.getzep.com/）

## 使用

```bash
# 首次設定
mirofish serve start
# → 自動生成 ~/.mirofish/.env 模板
# → 填入 API key 後重新 start

# 一鍵推演
mirofish predict "如果美聯儲降息200基點"

# 查看結果
mirofish report <simulation_id>

# 追問
mirofish chat <simulation_id> "哪些 KOL 最極端？"

# 採訪 Agent
mirofish interview <simulation_id> 0 "你的觀點是什麼？"

# 視覺化 Dashboard
mirofish canvas <simulation_id>
```

## P2P 分散式推演

多台機器各自跑 MiroFish，互相分享推演結果，最後合併分析。

### 1. 設定 Peers

```bash
# 加入遠端節點
mirofish peers add http://192.168.1.200:5001 "lab-server"
mirofish peers add http://192.168.1.201:5001 "gpu-box"

# 查看已設定的 peers
mirofish peers list

# 確認 peers 健康
mirofish peers health
# ✅ lab-server (http://192.168.1.200:5001)
# ✅ gpu-box (http://192.168.1.201:5001)
```

### 2. 分散式推演

```bash
# --p2p 旗標：先廣播種子給所有 peers，本機也同時跑，跑完廣播結果
mirofish predict "如果比特幣突破15萬" --p2p
```

**流程圖：**
```
Node A (你的機器)          Node B (lab-server)       Node C (gpu-box)
──────────────────       ──────────────          ────────────
1. 廣播種子 ──────────> 收到種子 (📋 queued)    收到種子 (📋 queued)
2. 本機推演開始          [可手動觸發推演]        [可手動觸發推演]
3. 本機推演完成
4. 廣播結果 ──────────> 儲存結果               儲存結果
```

### 3. 合併多節點結果

```bash
# 收集所有 peer 的結果，合併產生 meta-report
mirofish meta "如果比特幣突破15萬"
```

### 4. 後端 P2P API

每個 MiroFish 後端自動提供 P2P endpoints：

| Endpoint | 方法 | 說明 |
|:---|:---|:---|
| `/api/p2p/predict` | POST | 接收種子廣播 |
| `/api/p2p/result` | POST | 接收其他節點推演結果 |
| `/api/p2p/results?topic=...` | GET | 查詢已收集結果 |
| `/api/p2p/seeds` | GET | 查看收到的種子列表 |

### 5. Auto-Predict（選擇性）

讓 peer 收到種子後自動推演（需設定環境變數）：

```bash
# 在 peer 端啟動時開啟
P2P_AUTO_PREDICT=true uv run flask run --port 5001

# 或在 .env 加入
P2P_AUTO_PREDICT=true
```

> ⚠️ Auto-predict 會消耗 LLM API quota。預設關閉，需明確開啟。

## OpenClaw Skill

安裝 skill 後，直接在 OpenClaw 對話中說「推演 XXX」即可觸發：

```bash
clawhub install mirofish-predict
```

## 架構

```
mirofish predict "topic" --p2p
  ├── broadcastSeed() → POST /api/p2p/predict to all peers
  ├── predict()       → 本機 7-step pipeline (ontology → graph → simulate → report)
  └── broadcastResult() → POST /api/p2p/result to all peers

mirofish meta "topic"
  ├── collectResults() → GET /api/p2p/results from all peers
  └── generateMetaReport() → 合併 + 共識/衝突分析
```

## 專案結構

```
miro_claw/
├── cli/                    # mirofish-cli npm 包
│   ├── bin/mirofish.js     # CLI 入口
│   ├── lib/api.js          # HTTP client
│   ├── lib/docker.js       # Docker/Native daemon 管理
│   ├── lib/predict.js      # 高階推演流程 (7-step pipeline)
│   ├── lib/canvas.js       # 視覺化 Dashboard
│   ├── lib/notify.js       # 推播通知
│   ├── lib/peer-config.js  # P2P peer 管理 (peers.json)
│   ├── lib/p2p.js          # P2P 種子/結果廣播
│   ├── lib/meta-report.js  # 多節點結果合併分析
│   ├── test/               # 測試
│   │   ├── peer-config.test.js  # 12 tests
│   │   ├── p2p.test.js          # 8 tests
│   │   ├── meta-report.test.js  # 7 tests
│   │   └── e2e-p2p.sh          # 16 E2E tests (雙 Flask server)
│   └── package.json
├── skills/                 # OpenClaw skill
│   └── mirofish-predict/
├── MiroFish/               # Core engine (submodule)
│   └── backend/
│       ├── app/api/p2p.py  # P2P Flask Blueprint (14 pytest)
│       └── tests/test_p2p.py
└── .env                    # 環境變數
```

## 測試

```bash
# 全部 57 tests
cd MiroFish/backend && uv run pytest tests/test_p2p.py -q          # 14 passed
cd ../../cli && node test/peer-config.test.js                      # 12 passed
cd ../cli && node test/p2p.test.js                                 # 8 passed
cd ../cli && node test/meta-report.test.js                         # 7 passed
cd .. && bash cli/test/e2e-p2p.sh                                  # 16 passed
```

## 測試注意事項

### 環境需求

| 項目 | 說明 |
|:---|:---|
| LLM 服務 | LM Studio / Ollama / 任何 OpenAI 格式 API |
| ZEP Cloud | 免費 tier，key 會過期需更新 |
| Docker | AMD64 only（Apple Silicon 自動 fallback native） |
| Native 模式 | 需 `uv` + Python 3.11 + MiroFish source |

### 已知問題

1. **Docker pull 延遲** — 每次 `serve start` 會嘗試 pull image（ARM64 會失敗後 fallback），增加 ~4 秒
2. **短 seed text** — `predict` 自動擴展 <200 字元的輸入為 ~1100 字元結構化文檔（確保 ZEP 能提取足夠實體）
3. **Report 非同步** — `predict` 結束時 report 可能還是 `pending`，Report Agent 在後台生成

### Troubleshooting

```bash
# 確認 LLM 可達
curl http://YOUR_LLM_IP:1234/v1/models

# 確認 backend 健康
curl http://localhost:5001/health

# P2P: 查看 peer 收到的種子
curl http://localhost:5001/api/p2p/seeds

# P2P: 測試結果寫入
curl -X POST http://localhost:5001/api/p2p/result \
  -H 'Content-Type: application/json' \
  -d '{"topic":"test","simulation_id":"sim_1","origin_node":"me","report":{"status":"ok"}}'

# 查看 native 模式 PID
cat ~/.mirofish/backend.pid

# 強制清理
pkill -f "uv run python run.py"
rm -f ~/.mirofish/backend.pid
```

## License

MIT


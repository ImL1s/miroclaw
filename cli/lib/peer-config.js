/**
 * MiroFish P2P Peer 配置管理
 *
 * 管理已知的 peer 列表，存在 ~/.mirofish/peers.json
 * 支援手動加入和 mDNS 自動發現（未來）
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const MIROFISH_DIR = path.join(os.homedir(), '.mirofish');
const PEERS_FILE = path.join(MIROFISH_DIR, 'peers.json');

/**
 * 預設 peer 結構
 * @typedef {Object} Peer
 * @property {string} id - 唯一 ID（hostname 或自定義名稱）
 * @property {string} endpoint - MiroFish API endpoint (http://host:port)
 * @property {number} addedAt - 加入時間戳
 * @property {string} [label] - 可選的顯示標籤
 * @property {boolean} [active] - 是否啟用
 */

function ensureDir() {
    if (!fs.existsSync(MIROFISH_DIR)) {
        fs.mkdirSync(MIROFISH_DIR, { recursive: true });
    }
}

function loadPeers() {
    ensureDir();
    if (!fs.existsSync(PEERS_FILE)) {
        return [];
    }
    try {
        return JSON.parse(fs.readFileSync(PEERS_FILE, 'utf-8'));
    } catch {
        return [];
    }
}

function savePeers(peers) {
    ensureDir();
    fs.writeFileSync(PEERS_FILE, JSON.stringify(peers, null, 2));
}

/**
 * 新增一個 peer
 * @param {string} endpoint - e.g. "http://192.168.1.100:5001"
 * @param {string} [label] - 可選標籤
 * @returns {Peer}
 */
function addPeer(endpoint, label) {
    const peers = loadPeers();

    // 正規化 endpoint（移除尾部 /）
    endpoint = endpoint.replace(/\/+$/, '');

    // 驗證 URL 格式
    let parsedUrl;
    try {
        parsedUrl = new URL(endpoint);
    } catch {
        throw new Error(`Invalid endpoint URL: ${endpoint}`);
    }

    // 檢查是否已存在
    const existing = peers.find(p => p.endpoint === endpoint);
    if (existing) {
        console.log(`   ⚠️  Peer already exists: ${existing.id} (${endpoint})`);
        return existing;
    }

    const peer = {
        id: label || parsedUrl.hostname,
        endpoint,
        label: label || null,
        addedAt: Date.now(),
        active: true,
    };

    peers.push(peer);
    savePeers(peers);
    return peer;
}

/**
 * 移除一個 peer
 * @param {string} idOrEndpoint - peer ID 或 endpoint
 * @returns {boolean}
 */
function removePeer(idOrEndpoint) {
    const peers = loadPeers();
    const idx = peers.findIndex(p => p.id === idOrEndpoint || p.endpoint === idOrEndpoint);
    if (idx === -1) return false;
    peers.splice(idx, 1);
    savePeers(peers);
    return true;
}

/**
 * 取得所有活躍的 peers
 * @returns {Peer[]}
 */
function getActivePeers() {
    return loadPeers().filter(p => p.active !== false);
}

/**
 * 列出所有 peers
 * @returns {Peer[]}
 */
function listPeers() {
    return loadPeers();
}

/**
 * 健康檢查一個 peer
 * @param {Peer} peer
 * @returns {Promise<boolean>}
 */
async function checkPeerHealth(peer) {
    try {
        const url = `${peer.endpoint}/health`;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timeout);
        return res.ok;
    } catch {
        return false;
    }
}

/**
 * 檢查所有 peers 的健康狀態
 * @returns {Promise<Array<{peer: Peer, healthy: boolean}>>}
 */
async function checkAllPeersHealth() {
    const peers = getActivePeers();
    const results = await Promise.all(
        peers.map(async (peer) => ({
            peer,
            healthy: await checkPeerHealth(peer),
        }))
    );
    return results;
}

module.exports = {
    addPeer,
    removePeer,
    getActivePeers,
    listPeers,
    checkPeerHealth,
    checkAllPeersHealth,
    PEERS_FILE,
};

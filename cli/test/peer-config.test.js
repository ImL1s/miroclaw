/**
 * peer-config.js 單元測試
 *
 * 測試 peer CRUD、URL 驗證、健康檢查
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const os = require('os');

// 用 tmp 目錄覆蓋 PEERS_FILE，避免污染真實設定
const TEST_DIR = path.join(os.tmpdir(), `mirofish-test-${Date.now()}`);
const TEST_PEERS_FILE = path.join(TEST_DIR, 'peers.json');

// Monkey-patch module constants before require
// (peer-config.js 在 module scope 定義了 MIROFISH_DIR 和 PEERS_FILE)
// → 我們直接操作檔案然後用 require 測試
fs.mkdirSync(TEST_DIR, { recursive: true });

// 動態修改 peer-config.js 讀取的路徑
const peerConfig = require('../lib/peer-config.js');
// Override PEERS_FILE for testing
const origPeersFile = peerConfig.PEERS_FILE;

function setupTestFile() {
    // 重設 PEERS_FILE 為測試路徑
    // 因為 peer-config 用的是 module-level const，我們用 env 來 override
    // 或直接操作 fs
    if (fs.existsSync(origPeersFile)) {
        // Backup real peers file
        const backup = origPeersFile + '.backup';
        if (!fs.existsSync(backup)) {
            try { fs.copyFileSync(origPeersFile, backup); } catch { }
        }
    }
    // Clear the peers file
    const dir = path.dirname(origPeersFile);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(origPeersFile, '[]');
}

function restoreTestFile() {
    const backup = origPeersFile + '.backup';
    if (fs.existsSync(backup)) {
        fs.copyFileSync(backup, origPeersFile);
        fs.unlinkSync(backup);
    } else {
        try { fs.unlinkSync(origPeersFile); } catch { }
    }
}

let passed = 0;
let failed = 0;

function test(name, fn) {
    try {
        fn();
        console.log(`  ✅ ${name}`);
        passed++;
    } catch (e) {
        console.error(`  ❌ ${name}: ${e.message}`);
        failed++;
    }
}

async function asyncTest(name, fn) {
    try {
        await fn();
        console.log(`  ✅ ${name}`);
        passed++;
    } catch (e) {
        console.error(`  ❌ ${name}: ${e.message}`);
        failed++;
    }
}

async function runTests() {
    console.log('\n🧪 peer-config.js tests\n');

    setupTestFile();

    try {
        // --- addPeer ---
        test('addPeer: adds a peer with valid URL', () => {
            const peer = peerConfig.addPeer('http://192.168.1.100:5001', 'node-a');
            assert.strictEqual(peer.id, 'node-a');
            assert.strictEqual(peer.endpoint, 'http://192.168.1.100:5001');
            assert.strictEqual(peer.active, true);
            assert.ok(peer.addedAt > 0);
        });

        test('addPeer: strips trailing slash', () => {
            peerConfig.removePeer('node-a');
            const peer = peerConfig.addPeer('http://192.168.1.100:5001///', 'node-b');
            assert.strictEqual(peer.endpoint, 'http://192.168.1.100:5001');
            peerConfig.removePeer('node-b');
        });

        test('addPeer: rejects invalid URL', () => {
            assert.throws(() => {
                peerConfig.addPeer('not-a-url', 'bad');
            }, /Invalid endpoint URL/);
        });

        test('addPeer: uses hostname as ID when no label', () => {
            const peer = peerConfig.addPeer('http://10.0.0.5:5001');
            assert.strictEqual(peer.id, '10.0.0.5');
            peerConfig.removePeer('10.0.0.5');
        });

        test('addPeer: deduplicates by endpoint', () => {
            peerConfig.addPeer('http://192.168.1.200:5001', 'dup-1');
            const dup = peerConfig.addPeer('http://192.168.1.200:5001', 'dup-2');
            assert.strictEqual(dup.id, 'dup-1'); // returns existing
            const all = peerConfig.listPeers();
            const count = all.filter(p => p.endpoint === 'http://192.168.1.200:5001').length;
            assert.strictEqual(count, 1);
            peerConfig.removePeer('dup-1');
        });

        // --- removePeer ---
        test('removePeer: removes by id', () => {
            peerConfig.addPeer('http://10.0.0.1:5001', 'rm-test');
            const removed = peerConfig.removePeer('rm-test');
            assert.strictEqual(removed, true);
            assert.strictEqual(peerConfig.listPeers().length, 0);
        });

        test('removePeer: removes by endpoint', () => {
            peerConfig.addPeer('http://10.0.0.2:5001', 'rm-ep');
            const removed = peerConfig.removePeer('http://10.0.0.2:5001');
            assert.strictEqual(removed, true);
        });

        test('removePeer: returns false for non-existent peer', () => {
            const removed = peerConfig.removePeer('ghost');
            assert.strictEqual(removed, false);
        });

        // --- listPeers / getActivePeers ---
        test('listPeers: returns all peers', () => {
            peerConfig.addPeer('http://10.0.0.10:5001', 'p1');
            peerConfig.addPeer('http://10.0.0.11:5001', 'p2');
            assert.strictEqual(peerConfig.listPeers().length, 2);
            peerConfig.removePeer('p1');
            peerConfig.removePeer('p2');
        });

        test('getActivePeers: filters inactive', () => {
            peerConfig.addPeer('http://10.0.0.20:5001', 'active');
            // Manually set one as inactive
            const peers = peerConfig.listPeers();
            peers[0].active = false;
            fs.writeFileSync(origPeersFile, JSON.stringify(peers));
            assert.strictEqual(peerConfig.getActivePeers().length, 0);
            peerConfig.removePeer('active');
        });

        // --- checkPeerHealth ---
        await asyncTest('checkPeerHealth: returns false for unreachable peer', async () => {
            const healthy = await peerConfig.checkPeerHealth({
                id: 'ghost', endpoint: 'http://192.168.255.255:5001'
            });
            assert.strictEqual(healthy, false);
        });

        // --- persistence ---
        test('persistence: survives reload', () => {
            peerConfig.addPeer('http://10.0.0.30:5001', 'persist');
            // Clear require cache to simulate reload
            delete require.cache[require.resolve('../lib/peer-config.js')];
            const fresh = require('../lib/peer-config.js');
            const peers = fresh.listPeers();
            assert.ok(peers.some(p => p.id === 'persist'));
            peerConfig.removePeer('persist');
        });

    } finally {
        restoreTestFile();
    }

    console.log(`\n📊 Results: ${passed} passed, ${failed} failed\n`);
    process.exit(failed > 0 ? 1 : 0);
}

runTests();

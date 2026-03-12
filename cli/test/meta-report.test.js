/**
 * meta-report.js 單元測試（TDD — 先寫測試）
 *
 * 測試多節點推演結果的合併分析邏輯
 */
const assert = require('assert');

// 先試 require，預期會失敗（RED phase）
let metaReport;
try {
    metaReport = require('../lib/meta-report.js');
} catch (e) {
    console.error('❌ Cannot load meta-report.js — need to implement it first');
    process.exit(1);
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

// --- 模擬資料 ---
const REPORT_A = {
    node: 'node-a',
    simulation_id: 'sim_001',
    topic: '如果比特幣突破15萬',
    report: {
        outline: {
            title: 'Bitcoin 150k Analysis',
            sections: [
                { title: 'Market Impact', content: 'BTC surge causes altcoin rally. ETH follows to $8000.' },
                { title: 'Regulation', content: 'SEC may increase scrutiny. Spot ETF inflows accelerate.' },
            ]
        },
        status: 'completed',
    }
};

const REPORT_B = {
    node: 'node-b',
    simulation_id: 'sim_002',
    topic: '如果比特幣突破15萬',
    report: {
        outline: {
            title: 'BTC $150K Scenario',
            sections: [
                { title: 'Macro Effects', content: 'Dollar weakens. Gold correlation breaks. Institutional FOMO.' },
                { title: 'Retail Sentiment', content: 'Extreme greed index. New retail investors flood in.' },
            ]
        },
        status: 'completed',
    }
};

const REPORT_C = {
    node: 'node-c',
    simulation_id: 'sim_003',
    topic: '如果比特幣突破15萬',
    report: {
        outline: {
            title: 'BTC 150K Impact',
            sections: [
                { title: 'Mining', content: 'Hash rate increases. Mining profitability soars.' },
            ]
        },
        status: 'completed',
    }
};

const EMPTY_REPORT = {
    node: 'node-empty',
    simulation_id: 'sim_004',
    topic: '如果比特幣突破15萬',
    report: { status: 'pending' },
};

// --- markdown_content 格式的報告（現版）---
const REPORT_MD_A = {
    node: 'node-md-a',
    simulation_id: 'sim_010',
    topic: 'ETH 突破 $10,000',
    report: {
        markdown_content: '# ETH 分析報告\n\n## 市場影響\n\nETH 突破萬元引發 DeFi 復興。\n\n## 監管反應\n\nSEC 對 ETH ETF 態度轉正。',
        status: 'completed',
    }
};

const REPORT_MD_B = {
    node: 'node-md-b',
    simulation_id: 'sim_011',
    topic: 'ETH 突破 $10,000',
    report: {
        markdown_content: '# ETH 情境推演\n\n## 技術面分析\n\n鏈上活躍地址破 100 萬。\n\n## 機構動向\n\nBlackRock 加碼 ETH 配置。',
        status: 'completed',
    }
};

const REPORT_MD_NO_HEADERS = {
    node: 'node-md-c',
    simulation_id: 'sim_012',
    topic: 'ETH 突破 $10,000',
    report: {
        markdown_content: '這是一份沒有標題的簡短報告。ETH 很棒。',
        status: 'completed',
    }
};


function runTests() {
    console.log('\n🧪 meta-report.js tests\n');

    // --- mergeReports: outline.sections 格式 ---
    test('mergeReports: merges 2 reports into meta-report', () => {
        const meta = metaReport.mergeReports([REPORT_A, REPORT_B]);
        assert.ok(meta.topic, 'should have topic');
        assert.strictEqual(meta.nodeCount, 2);
        assert.ok(meta.nodes.includes('node-a'));
        assert.ok(meta.nodes.includes('node-b'));
        assert.ok(meta.sections.length > 0, 'should have merged sections');
    });

    test('mergeReports: handles 3+ reports', () => {
        const meta = metaReport.mergeReports([REPORT_A, REPORT_B, REPORT_C]);
        assert.strictEqual(meta.nodeCount, 3);
        assert.ok(meta.sections.length >= 3);
    });

    test('mergeReports: skips pending/incomplete reports', () => {
        const meta = metaReport.mergeReports([REPORT_A, EMPTY_REPORT]);
        assert.strictEqual(meta.nodeCount, 1);
        assert.ok(!meta.nodes.includes('node-empty'));
    });

    test('mergeReports: returns empty meta for no valid reports', () => {
        const meta = metaReport.mergeReports([EMPTY_REPORT]);
        assert.strictEqual(meta.nodeCount, 0);
        assert.strictEqual(meta.sections.length, 0);
    });

    test('mergeReports: handles empty input', () => {
        const meta = metaReport.mergeReports([]);
        assert.strictEqual(meta.nodeCount, 0);
    });

    // --- mergeReports: markdown_content 格式 ---
    test('mergeReports: merges markdown_content format reports', () => {
        const meta = metaReport.mergeReports([REPORT_MD_A, REPORT_MD_B]);
        assert.strictEqual(meta.nodeCount, 2);
        assert.ok(meta.sections.length >= 4, `should have 4+ sections, got ${meta.sections.length}`);
        assert.ok(meta.sections.some(s => s.title === '市場影響'));
        assert.ok(meta.sections.some(s => s.title === '技術面分析'));
        assert.ok(meta.sections.some(s => s.source === 'node-md-a'));
        assert.ok(meta.sections.some(s => s.source === 'node-md-b'));
    });

    test('mergeReports: handles markdown without ## headers', () => {
        const meta = metaReport.mergeReports([REPORT_MD_NO_HEADERS]);
        assert.strictEqual(meta.nodeCount, 1);
        assert.ok(meta.sections.length >= 1, 'should create fallback section');
    });

    test('mergeReports: mixes outline + markdown formats', () => {
        const meta = metaReport.mergeReports([REPORT_A, REPORT_MD_A]);
        assert.strictEqual(meta.nodeCount, 2);
        assert.ok(meta.sections.some(s => s.source === 'node-a'));
        assert.ok(meta.sections.some(s => s.source === 'node-md-a'));
    });

    // --- parseMarkdownSections ---
    test('parseMarkdownSections: splits on ## headers', () => {
        const sections = metaReport.parseMarkdownSections(
            '# Title\n\n## Section A\n\nContent A\n\n## Section B\n\nContent B'
        );
        assert.strictEqual(sections.length, 2);
        assert.strictEqual(sections[0].title, 'Section A');
        assert.ok(sections[0].content.includes('Content A'));
        assert.strictEqual(sections[1].title, 'Section B');
    });

    test('parseMarkdownSections: fallback for no ## headers', () => {
        const sections = metaReport.parseMarkdownSections('Just plain text.');
        assert.strictEqual(sections.length, 1);
        assert.ok(sections[0].content.includes('Just plain text.'));
    });

    // --- formatMetaReport ---
    test('formatMetaReport: produces readable markdown', () => {
        const meta = metaReport.mergeReports([REPORT_A, REPORT_B]);
        const md = metaReport.formatMetaReport(meta);
        assert.ok(md.includes('# '), 'should have markdown header');
        assert.ok(md.includes('node-a'), 'should mention source nodes');
        assert.ok(md.includes('node-b'));
        assert.ok(md.includes('如果比特幣突破15萬'), 'should include topic');
    });

    test('formatMetaReport: shows section sources', () => {
        const meta = metaReport.mergeReports([REPORT_A, REPORT_B]);
        const md = metaReport.formatMetaReport(meta);
        // Each section should attribute its source node
        assert.ok(md.includes('node-a') || md.includes('node-b'));
    });

    console.log(`\n📊 Results: ${passed} passed, ${failed} failed\n`);
    process.exit(failed > 0 ? 1 : 0);
}

runTests();

// 检验现有工具的更新可见性与实验计量完整性；只使用隔离夹具。
// 用法：node meta/research/2026-10-13-rag-evaluation/contract-probes.mjs
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripTypeScriptTypes } from 'node:module';

const taskDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(taskDir, '../../..');
const webRoot = process.env.RESEARCH_WEB_ROOT || 'E:/arkriicinfra/riicweb';
const source = await readFile(path.join(webRoot, 'src/server/agent/knowledge.ts'), 'utf8');
const fixture = await mkdtemp(path.join(taskDir, '.fixture-'));
const realNow = Date.now;
const notes = [];
try {
  for (const dir of ['docs', 'index']) await mkdir(path.join(fixture, dir));
  const doc = path.join(fixture, 'docs/条目.md');
  const toc = path.join(fixture, 'index/标题清单.md');
  await writeFile(path.join(fixture, 'index/消歧字典.json'), '{}');
  await writeFile(toc, '- `docs/条目.md`（mechanism，2026-10-12）旧规则：旧值\n');
  await writeFile(doc, '# 旧规则\n旧值=10\n');
  const api = await import('data:text/javascript;base64,' + Buffer.from(stripTypeScriptTypes(source
    .replace('import "server-only";', '')
    .replace('import { agentKnowledgeDir } from "./config.ts";', `const agentKnowledgeDir = () => ${JSON.stringify(fixture)};`))).toString('base64'));
  const baseTime = realNow(); Date.now = () => baseTime;
  assert.equal((await api.searchKnowledgeBase('旧规则')).matched[0]?.path, 'docs/条目.md');
  await writeFile(toc, '- `docs/条目.md`（mechanism，2026-10-13）新规范：新值\n');
  await writeFile(doc, '# 新规范\n新值=20\n');
  const stale = await api.searchKnowledgeBase('旧规则');
  const fresh = await api.readKnowledgeDoc('docs/条目.md');
  assert.equal(stale.matched[0]?.label, '旧规则：旧值');
  assert.equal(fresh.title, '新规范');
  notes.push({ probe: '标题缓存与正文更新', result: '已复现', routeLabel: stale.matched[0].label, readTitle: fresh.title,
    implication: '60秒TTL内可以返回旧候选说明，同时读到新正文；单次会话没有共享知识快照。' });
  Date.now = () => baseTime + 60_001;
  assert.equal((await api.searchKnowledgeBase('新规范')).matched[0]?.label, '新规范：新值');
  notes.push({ probe: '缓存TTL到期', result: '已复现', observedAfterMs: 60_001, implication: '重建标题索引后，下次查询可在TTL到期后看到更新；实际正文更新本身不会生成索引。' });
  await assert.rejects(() => api.readKnowledgeDoc('meta/secret.md'));
  await assert.rejects(() => api.readKnowledgeDoc('docs/../index/标题清单.md'));
  notes.push({ probe: '现有正文入口范围', result: '通过', implication: 'meta与简单路径穿越被拒绝。本探针不是完整安全审计。' });
} finally {
  Date.now = realNow;
  const resolved = path.resolve(fixture);
  if (!resolved.startsWith(path.resolve(taskDir) + path.sep) || !path.basename(resolved).startsWith('.fixture-')) throw new Error('夹具清理路径不合法');
  await rm(resolved, { recursive: true });
}

const results = JSON.parse(await readFile(path.join(taskDir, 'results.json'), 'utf8'));
assert.equal(results.details.length, 36 * 5 * 3);
assert.equal(results.community.results.length, 82 * 5);
const files = new Set();
for (const detail of results.details) {
  assert.ok(detail.ranked.length <= 8);
  assert.equal(new Set(detail.ranked).size, detail.ranked.length);
  assert.ok(detail.ranked.every((f) => f.startsWith('docs/') && f.endsWith('.md')));
  assert.ok(detail.gold.every((g) => g.length > 0));
  assert.ok(detail.latencyMs >= 0);
  for (const f of detail.ranked) files.add(f);
  if (detail.repeat > 1) {
    const first = results.details.find((r) => r.repeat === 1 && r.mode === detail.mode && r.id === detail.id);
    assert.deepEqual(detail.ranked, first.ranked);
  }
}
for (const d of results.details.filter((d) => d.repeat === 1)) {
  for (const g of d.gold) {
    // gold既可以在候选中出现，也可能被漏检；从真实docs递归确认可定位。
    const toc = await readFile(path.join(root, 'index/标题清单.md'), 'utf8');
    assert.ok(g.some((name) => toc.includes('/' + name + '`')), 'gold目标不存在：' + g.join('/'));
  }
}
notes.push({ probe: '实验计量完整性', result: '通过', retrievalRecords: results.details.length,
  communityRecords: results.community.results.length, identicalRankingsAcrossRepeats: true,
  implication: '540条带标签记录、410条未标注记录；三个重复只衡量运行计时与确定性，不表示LLM三轮作答。' });
await writeFile(path.join(taskDir, 'probes.json'), JSON.stringify(notes, null, 2) + '\n');
console.log(JSON.stringify(notes, null, 2));

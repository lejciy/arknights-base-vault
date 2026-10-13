// 只读检索实验：直接加载网站路由与参考项目 BM25，结果只写入本实验目录。
// 不运行主 agent，不修改其提示词、工具选择或计算流程，不调用远程模型。
// 用法：node meta/research/2026-10-13-rag-evaluation/benchmark.mjs
import { readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { stripTypeScriptTypes } from 'node:module';
import { performance } from 'node:perf_hooks';

const taskDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(taskDir, '../../..');
const webRoot = process.env.RESEARCH_WEB_ROOT || 'E:/arkriicinfra/riicweb';
const referenceRoot = process.env.RESEARCH_REFERENCE_ROOT || 'E:/佩奇knowledgeagent/RIIC-KnowledgeAgent';
const importTS = async (source) => import('data:text/javascript;base64,' + Buffer.from(stripTypeScriptTypes(source)).toString('base64'));
const sourceWeb = await readFile(path.join(webRoot, 'src/server/agent/knowledge.ts'), 'utf8');
const baseline = await importTS(sourceWeb
  .replace('import "server-only";', '')
  .replace('import { agentKnowledgeDir } from "./config.ts";', `const agentKnowledgeDir = () => ${JSON.stringify(root)};`));
const sourceBM25 = await readFile(path.join(referenceRoot, 'bench/src/retriever.ts'), 'utf8');
const bm25 = await importTS(sourceBM25
  .replace(/^import .* from 'jieba-node'\r?\n/m, 'const addWord = () => {}; const setLogLevel = () => {}; const lcut = () => { throw new Error("本实验只允许 bigram"); }; const lcutForSearch = lcut;\n')
  .replace(/^import .* from '\.\/terms\.js'\r?\n/m, 'const ENTITY_WORDS = [];\n')
  .replace(/^import .* from '\.\/config\.js'\r?\n/m, "const EXPERIMENT = { tokenizer: 'bigram', entityBoost: 0 };\n"));
const sourceCorpus = await readFile(path.join(referenceRoot, 'bench/src/corpus.ts'), 'utf8');
const referenceCorpus = await importTS(sourceCorpus);
const dictionary = JSON.parse(await readFile(path.join(root, 'index/消歧字典.json'), 'utf8'));
const labels = JSON.parse(await readFile(path.join(taskDir, 'cases.json'), 'utf8'));
const samples = await readFile(path.join(root, 'meta/问答测试样例.md'), 'utf8');
const originals = new Map([...samples.matchAll(/^## 样例 (\d+)｜[^\n]+\n[\s\S]*?\*\*题目\*\*：([^\n]+)/gm)].map((m) => [Number(m[1]), m[2].trim()]));
const cases = [
  ...labels.existing.map((c) => ({ ...c, id: `O${String(c.id).padStart(2, '0')}`, question: originals.get(c.id), suite: 'original' })),
  ...labels.existing.map((c) => ({ ...c, id: `P${String(c.id).padStart(2, '0')}`, question: c.paraphrase, suite: 'paraphrase' })),
  ...labels.heldout.map((c) => ({ ...c, suite: 'heldout' })),
];
if (cases.some((c) => !c.question)) throw new Error('题目解析失败');

const files = [];
async function walk(dir) {
  for (const entry of (await readdir(dir, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name, 'zh'))) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(p);
    else if (entry.name.endsWith('.md')) {
      const text = await readFile(p, 'utf8');
      const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---/)?.[1] || '';
      files.push({ absolute: p, file: path.relative(root, p).replaceAll('\\', '/'), text,
        title: text.match(/^# (.+)$/m)?.[1] || entry.name,
        status: fm.match(/^status:\s*(.+)$/m)?.[1] || null,
        type: fm.match(/^type:\s*(.+)$/m)?.[1] || null,
        updated: fm.match(/^updated:\s*(.+)$/m)?.[1] || null,
        generated: text.startsWith('<!-- 本文件由 scripts/render-skill-snapshot.mjs'),
      });
    }
  }
}
await walk(path.join(root, 'docs'));
const contentFiles = files.filter((f) => f.type !== 'index');
const byFile = new Map(files.map((f) => [f.file, f]));
const clean = (s) => s.toLowerCase().replace(/[\s·・]/g, '');

// 别名只从现有索引抽取。最长命中优先；重叠别名不擅自选择某一候选。
const aliases = [];
for (const group of ['combination_aliases', 'operator_aliases', 'skill_equivalence', 'other_aliases']) {
  for (const [alias, value] of Object.entries(dictionary[group] || {})) {
    aliases.push({ alias, key: clean(alias), value, group });
  }
}
aliases.sort((a, b) => b.key.length - a.key.length);
function expand(query) {
  const q = clean(query); const additions = new Set(); const occupied = [];
  for (const item of aliases) {
    if (!item.key) continue;
    let start = q.indexOf(item.key);
    if (start < 0 || occupied.some(([s, e]) => start >= s && start + item.key.length <= e)) continue;
    occupied.push([start, start + item.key.length]);
    const v = item.value;
    if (v.canonical) additions.add(v.canonical);
    for (const target of v.targets || []) additions.add(target);
    for (const g of v.groups || []) {
      for (const name of g.equivalent || []) additions.add(name);
      for (const holder of g.holders || []) additions.add(holder.split('☆')[0]);
    }
  }
  return `${query} ${[...additions].join(' ')}`;
}

const buildStart = performance.now();
const rawChunks = contentFiles.flatMap((f) => referenceCorpus.splitChunks(f.absolute, root));
const rawIndex = bm25.buildIndex(rawChunks);
// 通用标题上下文：不添加生成式总结；正文不含 front matter，代码围栏不参与标题定位。
const chunks = [];
for (const doc of contentFiles) {
  const text = doc.text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '');
  const lines = text.split(/\r?\n/); let headings = []; let buf = []; let start = 1; let fenced = false;
  const aliasNames = aliases.filter((a) => a.value.file === doc.file).map((a) => a.alias);
  function flush() {
    const body = buf.join('\n').trim();
    if (body) chunks.push({ id: `${doc.file}:${start}`, file: doc.file, heading: headings.map((h) => h.name).join(' > '),
      anchor: [doc.title, ...aliasNames].join(' '), text: body, status: doc.status, startLine: start });
    buf = [];
  }
  lines.forEach((line, i) => {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    const h = !fenced && /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      flush(); const level = h[1].length; headings = headings.filter((p) => p.level < level); headings.push({ level, name: h[2] }); start = i + 2;
    } else buf.push(line);
  });
  flush();
}
const enrichedIndex = bm25.buildIndex(chunks);
const buildMs = performance.now() - buildStart;
function rankedDocs(index, blocks, question) {
  const ranks = bm25.search(index, question, blocks.length); const seen = new Set(); const docs = [];
  for (const i of ranks) if (!seen.has(blocks[i].file)) { seen.add(blocks[i].file); docs.push(blocks[i].file); }
  return docs;
}
function fuse(rankLists) {
  const scores = new Map();
  for (const ranks of rankLists) ranks.slice(0, 30).forEach((file, rank) => scores.set(file, (scores.get(file) || 0) + 1 / (60 + rank + 1)));
  return [...scores.entries()].sort((a, b) => b[1] - a[1]).map(([f]) => f);
}
const modes = {
  route: async (q) => (await baseline.searchKnowledgeBase(q)).matched.map((d) => d.path),
  reference_bm25: async (q) => rankedDocs(rawIndex, rawChunks, q).slice(0, 8),
  contextual_bm25: async (q) => rankedDocs(enrichedIndex, chunks, expand(q)).slice(0, 8),
  route_raw_bm25: async (q) => fuse([
    (await baseline.searchKnowledgeBase(q)).matched.map((d) => d.path),
    rankedDocs(rawIndex, rawChunks, q),
  ]).slice(0, 8),
  route_bm25: async (q) => fuse([
    (await baseline.searchKnowledgeBase(q)).matched.map((d) => d.path),
    rankedDocs(enrichedIndex, chunks, expand(q)),
  ]).slice(0, 8),
};
const summaries = []; const details = [];
function percentile(a, p) { const v = [...a].sort((x, y) => x - y); return v[Math.ceil(p * v.length) - 1] || 0; }
const match = (file, alternatives) => alternatives.some((name) => file.endsWith('/' + name));
for (let repeat = 1; repeat <= 3; repeat++) {
  // 排序轮换减少固定执行顺序带来的热缓存偏差。首个 route 查询另记冷启动。
  const ids = Object.keys(modes); const order = ids.slice(repeat - 1).concat(ids.slice(0, repeat - 1));
  for (const mode of order) {
    const results = [];
    for (const c of cases) {
      const started = performance.now(); const ranked = await modes[mode](c.question); const elapsed = performance.now() - started;
      const goldHits = c.gold.map((g) => ranked.some((f) => match(f, g)));
      const rr = c.gold.map((g) => { const i = ranked.findIndex((f) => match(f, g)); return i >= 0 ? 1 / (i + 1) : 0; });
      const detail = { repeat, mode, suite: c.suite, id: c.id, question: c.question, gold: c.gold, ranked,
        recall: goldHits.filter(Boolean).length / goldHits.length, complete: goldHits.every(Boolean), anyHit: goldHits.some(Boolean),
        firstRelevantRR: Math.max(...rr), latencyMs: elapsed,
        draftCandidates: ranked.filter((f) => byFile.get(f)?.status === 'draft'),
        navigationCandidates: ranked.filter((f) => byFile.get(f)?.type === 'index'),
      };
      results.push(detail); details.push(detail);
    }
    for (const suite of ['original', 'paraphrase', 'heldout', 'all']) {
      const selected = results.filter((r) => suite === 'all' || r.suite === suite);
      summaries.push({ repeat, mode, suite, questions: selected.length,
        meanGoldGroupRecallAt8: selected.reduce((s, r) => s + r.recall, 0) / selected.length,
        completeGoldQuestions: selected.filter((r) => r.complete).length,
        anyGoldQuestions: selected.filter((r) => r.anyHit).length,
        mrr: selected.reduce((s, r) => s + r.firstRelevantRR, 0) / selected.length,
        p50Ms: percentile(selected.map((r) => r.latencyMs), .5), p95Ms: percentile(selected.map((r) => r.latencyMs), .95),
        draftCandidateQuestions: selected.filter((r) => r.draftCandidates.length).length,
      });
    }
  }
}
// 保留全部82道评论题的未标注检索结果，仅用于失败分析，不能生成准确率。
const questionList = await readFile(path.join(root, 'meta/mirror/bilibili_comments_questions_split.md'), 'utf8');
const communityQuestions = [...questionList.matchAll(/^\*\*(\d+)\.\*\*\s*(.+)$/gm)].map((m) => ({ id: Number(m[1]), question: m[2].trim() }));
if (communityQuestions.length !== 82) throw new Error('82题清单解析失败');
const communityResults = [];
for (const c of communityQuestions) {
  for (const [mode, search] of Object.entries(modes)) {
    const started = performance.now(); const ranked = await search(c.question);
    communityResults.push({ ...c, mode, ranked, latencyMs: performance.now() - started });
  }
}
// 补充: 五份 draft 不进入默认可信证据时，原始 gold 的可达性。
const authorityGaps = cases.filter((c) => c.gold.some((g) => !contentFiles.some((d) => d.status !== 'draft' && match(d.file, g)))).map((c) => c.id);
const result = {
  date: '2026-10-13', root, webRoot, referenceRoot, nodeVersion: process.version,
  scope: '检索层：每种方法最多8份候选文档；未运行LLM回答/向量/重排。原题与标签不作为检索输入。',
  methods: {
    route: '直接加载网站 knowledge.ts，仅替换目录注入与 server-only 导入',
    reference_bm25: '直接加载参考项目 splitChunks/buildIndex/search；bigram、entityBoost=0、按首次块命中去重到8文档',
    contextual_bm25: '标题上下文分块+索引别名扩展+参考项目BM25；消融分块与扩词的组合影响',
    route_raw_bm25: '原路由与未改写参考BM25的RRF融合；消融融合本身影响；k=60，两路各最多30文档候选',
    route_bm25: '标题上下文分块+索引别名扩展+原路由与正文BM25的RRF融合；k=60，两路各最多30文档候选',
  },
  corpus: { docs: files.length, navigation: files.filter((f) => f.type === 'index').length, content: contentFiles.length,
    draft: contentFiles.filter((f) => f.status === 'draft').map((f) => f.file), noFrontMatter: contentFiles.filter((f) => !f.status).map((f) => f.file),
    sourceChars: files.reduce((s, f) => s + f.text.length, 0), rawChunks: rawChunks.length, enrichedChunks: chunks.length, buildMs },
  goldenAuthorityGaps: authorityGaps, summaries, details,
  community: { count: communityQuestions.length, scored: false, results: communityResults },
};
await writeFile(path.join(taskDir, 'results.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ corpus: result.corpus, goldenAuthorityGaps: authorityGaps, firstRepeat: summaries.filter((s) => s.repeat === 1) }, null, 2));

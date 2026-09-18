#!/usr/bin/env node
// 把主仓库的知识产物派生成对外发布版（lejciy/RIIC-knowledge）。
//
// 用法（在仓库根执行）：
//   node meta/tools/sync-public.mjs                  # 同步到 ../RIIC-knowledge
//   node meta/tools/sync-public.mjs --target <dir>   # 指定对外版工作副本路径
//   node meta/tools/sync-public.mjs --check          # 只报告差异与校验结果，不写入
//
// 设计约定：
// - 主仓库是唯一真源；对外版是派生物，正文一律不要直接改对外版。
// - 白名单复制 + 替换表（抹掉内部路径、素材出处与决策编号）→ 重建索引 → 校验。
// - **校验 fail-closed**：产物里若仍命中内部痕迹（meta/、external/、库方、决策编号等）
//   即非零退出。新增文档引用内部文件时同步会当场失败，而不是把断链静默发布出去。
// - 对外版自有、本脚本不覆盖：README.md、tests/。README 仅做篇数校准。
// - 白名单目录内做 prune（删除源仓库已不存在的文件），删除项逐条打印；
//   README.md 与 tests/ 永不在 prune 范围内。

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, rmSync, existsSync } from 'node:fs';
import { join, relative, dirname, sep } from 'node:path';
import { execFileSync } from 'node:child_process';

const ROOT = process.cwd();
const args = process.argv.slice(2);
const CHECK = args.includes('--check');
const targetIndex = args.indexOf('--target');
const TARGET = targetIndex >= 0 ? args[targetIndex + 1] : join(ROOT, '..', 'RIIC-knowledge');

if (!existsSync(TARGET)) {
  console.error(`✗ 对外版目录不存在：${TARGET}`);
  console.error('  先在 GitHub 建好仓库并 clone 到该路径，或用 --target 指定。');
  process.exit(1);
}

// ---- 1. 白名单：源文件 → 目标路径 ----
// 目录项递归复制；单文件项直接复制。SRC 为仓库相对路径。
const DIRS = ['docs', 'skill'];
const FILES = [
  ['index/README.md', 'index/README.md'],
  ['index/导诊表.md', 'index/导诊表.md'],
  ['AGENTS.md', 'AGENTS.md'],
  ['LICENSE', 'LICENSE'],
  ['scripts/build-agent-index.mjs', 'scripts/build-agent-index.mjs'],
  ['meta/agent/SYSTEM_PROMPT.md', 'agent/SYSTEM_PROMPT.md'],
];
// 由 build-agent-index.mjs 在目标目录内重建，不从源复制
const GENERATED = ['index/消歧字典.json', 'index/标题清单.md'];

// ---- 2. 替换表：把内部痕迹抹成对外可读的表述 ----
// 每条 {file, from, to, all}；file 为源仓库相对路径。from 未命中只告警（真安全网是第 4 步校验）。
const RULES = [
  {
    file: 'docs/1-基础设定/README.md',
    from: '。模块边界与归属判断见根目录《知识库模块设计》。',
    to: '。',
  },
  {
    file: 'docs/2-干员技能/README.md',
    from: '根目录快照由 `scripts/render-skill-snapshot.mjs` 从 `meta/mirror/RIIC-Web/clean/` 数据**全量生成，请勿手改**；人工维护区为 `释义/` 子目录，歧义消歧两页已迁模块3 [歧义/](../3-组合库/歧义/)；全量真源、清洗过程与刷新口径见 `meta/mirror/RIIC-Web/`。',
    to: '根目录快照由 [RIIC-Web](https://github.com/KnightCodeSquareMatrix/RIIC-Web) 数据**全量生成，请勿手改**；人工维护区为 `释义/` 子目录，歧义消歧两页已迁模块3 [歧义/](../3-组合库/歧义/)。',
  },
  { file: 'docs/2-干员技能/README.md', from: '使用 `meta/templates/tpl-特殊技能释义.md`，存放于 `释义/`', to: '存放于 `释义/`' },
  { file: 'docs/2-干员技能/README.md', from: '（受管增补，D18）', to: '（受管增补）' },
  { file: 'docs/2-干员技能/README.md', from: '为 `clean/` 的静态副本', to: '为上游清洗数据的静态副本' },
  {
    file: 'docs/1-基础设定/资源体系/基建生产关系.md',
    from: '换算常数取自玩家口径（素材 `external/搓玉与库存.docx`）：',
    to: '换算常数取自玩家口径：',
  },
  {
    file: 'docs/3-组合库/README.md',
    from: '新组合先按 [组合库写作规范](../../meta/templates/组合库写作规范.md) 落深稿',
    to: '新组合先落深稿',
  },
  {
    file: 'docs/3-组合库/**',
    from: 'source: [用户素材（external/中枢等补充组合.txt）, 公孙长乐]',
    to: 'source: [用户素材, 公孙长乐]',
    all: true,
  },
  {
    file: 'docs/4-排班算法/README.md',
    from: '求解器实现规范镜像位于 `meta/mirror/ArknightsInfraCalc/`（只读、不具裁决权、不入 RAG）',
    to: '求解器实现规范来自外部项目 ArknightsInfraCalc（只读、不具裁决权、不入 RAG）',
  },
  {
    file: 'docs/5-换班操作/README.md',
    from: '各自独立成文（写作骨架见 `meta/templates/tpl-换班方式.md`）：',
    to: '各自独立成文：',
  },
  {
    file: 'docs/1-基础设定/资源体系/产出常数表.md',
    from: 'source: [prts, mirror, 公孙长乐,',
    to: 'source: [prts, ArknightsInfraCalc 求解器, 公孙长乐,',
  },
  { file: 'index/README.md', from: '与 `skill/`、`meta/agent/` 同属行为支撑层', to: '与 `skill/`、`agent/` 同属行为支撑层' },
  {
    file: 'index/导诊表.md',
    from: '- `meta/`、`external/`、镜像与治理文档不作为回答依据。',
    to: '- `index/`、`skill/`、`agent/`、`scripts/` 属行为与检索支撑层，不作为回答依据。',
  },
  { file: 'skill/README.md', from: '定位与 `meta/agent/SYSTEM_PROMPT.md` 同层', to: '定位与 `agent/SYSTEM_PROMPT.md` 同层' },
  {
    file: 'skill/README.md',
    from: '本目录属于 agent 行为层，与 `meta/agent/` 一样不入 RAG 语料；目录名不带编号——模块编号体系只覆盖 `docs/` 下的 7 个内容模块，本目录在其外并列，不改变「7 内容模块」的结构真源。',
    to: '本目录属于 agent 行为层，与 `agent/`、`index/` 一样不入 RAG 语料；目录名不带编号——模块编号体系只覆盖 `docs/` 下的 7 个内容模块，本目录在其外并列。',
  },
  {
    file: 'skill/README.md',
    from: '各 skill 由 84 题高频提问清单（`meta/mirror/bilibili_comments_questions_split.md`，2026-09-18 入库）逐类实测知识库回答路径后提炼',
    to: '各 skill 由高频提问逐类实测知识库回答路径后提炼',
  },
  {
    file: 'skill/README.md',
    from: `| skill | 承接的问题形态 | 实测对应题号（节选） |
|---|---|---|
| [skill-1-检索路由与歧义消解](skill-1-检索路由与歧义消解.md) | 检索前置：俗称、同效技能名、组合别名先消歧，再按模块路由 | 全部问题的前置；巫恋组=龙舌兰组、裁缝β多名持有者 |
| [skill-2-产出核算链](skill-2-产出核算链.md) | 多级换算与「效率→产出」计算：日产、月产、折玉折抽、回本周期 | 7、10、45、49、50、53、54、55、63、65、66 |
| [skill-3-缺员替代与组合降级](skill-3-缺员替代与组合降级.md) | 缺干员、缺练度时查降级档、找等价替换、复校互斥 | 37、38、58、59、61 |
| [skill-4-组合对比与场景选型](skill-4-组合对比与场景选型.md) | 两组合同场景比较：赤金充裕/紧缺分支、布局前提、互斥检查 | 32、33、35、36、46、47、62 |
| [skill-5-报表对账与差异定位](skill-5-报表对账与差异定位.md) | 三日报表判读、实际与预期差额归因、工具预估与简报不一致 | 6、39、64、65、66 |
| [skill-6-边界识别与转介](skill-6-边界识别与转介.md) | 排班工具操作、MAA、账号与产品侧问题的拆分应答与转介 | 20、67、71、72、73、75、80、81、82 |
| [skill-7-练卡取舍与回本判断](skill-7-练卡取舍与回本判断.md) | 值不值得练、先练谁、多久回本：定身份 → 五档判据 → 差值口径回本 → 玩家类型顺序 | —（2026-09-18 按公孙长乐指令立项，题号待实测补登） |
| [skill-8-产出数值诊断](skill-8-产出数值诊断.md) | 报表数值判定：产能指数/钱书和快速分档，逐线效率、平衡账、钱书比详细体检 | —（2026-09-18 按公孙长乐指令立项，题号待实测补登） |`,
    to: `| skill | 承接的问题形态 |
|---|---|
| [skill-1-检索路由与歧义消解](skill-1-检索路由与歧义消解.md) | 检索前置：俗称、同效技能名、组合别名先消歧，再按模块路由（如巫恋组＝龙舌兰组、裁缝 β 多名持有者） |
| [skill-2-产出核算链](skill-2-产出核算链.md) | 多级换算与「效率→产出」计算：日产、月产、折玉折抽、回本周期 |
| [skill-3-缺员替代与组合降级](skill-3-缺员替代与组合降级.md) | 缺干员、缺练度时查降级档、找等价替换、复校互斥 |
| [skill-4-组合对比与场景选型](skill-4-组合对比与场景选型.md) | 两组合同场景比较：赤金充裕／紧缺分支、布局前提、互斥检查 |
| [skill-5-报表对账与差异定位](skill-5-报表对账与差异定位.md) | 三日报表判读、实际与预期差额归因、工具预估与简报不一致 |
| [skill-6-边界识别与转介](skill-6-边界识别与转介.md) | 排班工具操作、MAA、账号与产品侧问题的拆分应答与转介 |
| [skill-7-练卡取舍与回本判断](skill-7-练卡取舍与回本判断.md) | 值不值得练、先练谁、多久回本：定身份 → 五档判据 → 差值口径回本 → 玩家类型顺序 |
| [skill-8-产出数值诊断](skill-8-产出数值诊断.md) | 报表数值判定：产能指数／钱书和快速分档，逐线效率、平衡账、钱书比详细体检 |`,
  },
  {
    file: 'skill/README.md',
    from: '按库方指令直接立项的（如 skill-7），题号列待实测后补登。',
    to: '先行立项未实测的（如 skill-7、skill-8），入库后补实测复核。',
  },
  { file: 'skill/skill-1-检索路由与歧义消解.md', from: '产物俗称先归一（2026-09-18 D58）：', to: '产物俗称先归一：' },
  {
    file: 'skill/skill-8-产出数值诊断.md',
    from: '正文不夹出处标注（与 D56 出处末尾化口径一致）。',
    to: '正文不夹出处标注。',
  },
  { file: 'skill/skill-8-产出数值诊断.md', from: '算例（库方口径）：', to: '算例：' },
  { file: 'skill/skill-8-产出数值诊断.md', from: '与 [[产出常数表]]·跨资源换算，D59）', to: '与 [[产出常数表]]·跨资源换算）' },
  { file: 'skill/skill-8-产出数值诊断.md', from: '五项仍为 2026-09-18 库方口径、暂驻', to: '五项为 2026-09-18 口径、暂驻' },
  {
    file: 'AGENTS.md',
    from: '治理规则以 `meta/协作与引用规范.md` 为准，本文件只做指引，不新增规则。',
    to: '仓库总览与数据源见根目录 `README.md`，本文件只做检索指引。',
  },
  {
    file: 'AGENTS.md',
    from: '配套 `skill/` 场景问答手册与 `meta/agent/SYSTEM_PROMPT.md` 行为总则。`meta/`（治理与镜像）、`external/`、`TODO.md` 与根目录治理文档均不是知识语料。',
    to: '配套 `skill/` 场景问答手册与 `agent/SYSTEM_PROMPT.md` 行为总则。`skill/`、`index/`、`agent/` 属行为与检索支撑层，不是知识语料。',
  },
  { file: 'AGENTS.md', from: '1. 行为总则：`meta/agent/SYSTEM_PROMPT.md`', to: '1. 行为总则：`agent/SYSTEM_PROMPT.md`' },
  {
    file: 'AGENTS.md',
    from: '- 不入语料：`meta/`、`external/`、`TODO.md`、根目录治理文档；`skill/` 与 `index/` 属行为与检索支撑层，作流程依据而非事实来源。',
    to: '- 不入语料：`skill/`、`index/`、`agent/`、`tests/` 与 `scripts/`，属行为、检索与测试支撑层，作流程依据而非事实来源。',
  },
];

// ---- 3. 内部痕迹校验模式（fail-closed）----
const FORBIDDEN = [
  { re: /meta\//g, label: '内部治理路径 meta/' },
  { re: /external\//g, label: '素材暂存路径 external/' },
  { re: /TODO\.md/g, label: '内部待办 TODO.md' },
  { re: /知识库模块设计/g, label: '内部结构文档名' },
  { re: /库方/g, label: '内部称谓「库方」' },
  { re: /决策记录/g, label: '内部决策记录引用' },
  { re: /内容目录/g, label: '内部进度文档引用' },
  { re: /\bD\d{1,2}\b/g, label: '内部决策编号' },
];

// ---- 工具 ----
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}
const toPosix = (p) => p.split(sep).join('/');
const matchGlob = (pattern, relPath) =>
  pattern.endsWith('/**') ? relPath.startsWith(pattern.slice(0, -2)) : relPath === pattern;
// 源仓库行尾混用（CRLF/LF 并存）：匹配与补丁统一按 LF 处理，写回时还原原行尾，避免整库行尾 churn。
const normalizeEol = (raw) => ({ text: raw.replaceAll('\r\n', '\n'), eol: raw.includes('\r\n') ? '\r\n' : '\n' });
const restoreEol = (text, eol) => (eol === '\r\n' ? text.replaceAll('\n', '\r\n') : text);

// ---- 4. 收集源文件清单 ----
const sources = [];
for (const dir of DIRS) {
  for (const abs of walk(join(ROOT, dir))) {
    sources.push({ src: toPosix(relative(ROOT, abs)), dst: toPosix(relative(ROOT, abs)) });
  }
}
for (const [src, dst] of FILES) sources.push({ src, dst });

// ---- 5. 打补丁（内容级）----
// 按规则统计命中：一条规则在所有匹配文件里一次都没命中才算失效（通配规则不会逐文件告警）。
const ruleHits = RULES.map(() => 0);
function patch(relSrc, content) {
  let out = content;
  RULES.forEach((rule, i) => {
    if (!matchGlob(rule.file, relSrc)) return;
    if (!out.includes(rule.from)) return;
    ruleHits[i] += 1;
    out = rule.all ? out.replaceAll(rule.from, rule.to) : out.replace(rule.from, rule.to);
  });
  return out;
}

// ---- 6. prune：白名单目录内，删除源仓库已不存在的文件 ----
const expected = new Set(sources.map((s) => s.dst).concat(GENERATED));
const pruneRoots = DIRS.concat(['agent', 'scripts']);
const stale = [];
for (const root of pruneRoots) {
  const abs = join(TARGET, root);
  if (!existsSync(abs)) continue;
  for (const f of walk(abs)) {
    const rel = toPosix(relative(TARGET, f));
    if (!expected.has(rel)) stale.push(rel);
  }
}

// ---- 7. 组装产物内容（先算后写，使 --check 能精确预演同步后的应然状态）----
const docsCount = walk(join(ROOT, 'docs')).filter((f) => f.endsWith('.md')).length;
const outputs = new Map(); // dst → { text, eol }
for (const { src, dst } of sources) {
  const { text, eol } = normalizeEol(readFileSync(join(ROOT, src), 'utf8'));
  outputs.set(dst, { text: patch(src, text), eol });
}
// 篇数校准：AGENTS.md 为派生件（在 outputs 内），README.md 为对外版自有（不覆盖，只校正数字）
const calibrate = (text) => text.replace(/(\d+) 篇/g, `${docsCount} 篇`);
if (outputs.has('AGENTS.md')) outputs.get('AGENTS.md').text = calibrate(outputs.get('AGENTS.md').text);
const readmeAbs = join(TARGET, 'README.md');
let readmeOut = null;
if (existsSync(readmeAbs)) {
  const { text, eol } = normalizeEol(readFileSync(readmeAbs, 'utf8'));
  const calibrated = calibrate(text);
  if (calibrated !== text) readmeOut = { text: calibrated, eol };
}

// ---- 8. 写入（或预演）----
if (CHECK) {
  console.log(`[--check] 对外版：${TARGET}`);
  console.log(`  源文件 ${sources.length} 个（docs ${docsCount} 篇）；待删除 ${stale.length} 个`);
  stale.forEach((f) => console.log(`    - ${f}`));
  if (readmeOut) console.log('  README.md 篇数待校准');
} else {
  stale.forEach((f) => {
    console.log(`  ✗ 删除（源仓库已无）：${f}`);
    rmSync(join(TARGET, f));
  });
  for (const [dst, { text, eol }] of outputs) {
    const dest = join(TARGET, dst);
    mkdirSync(dirname(dest), { recursive: true });
    writeFileSync(dest, restoreEol(text, eol), 'utf8');
  }
  console.log(`✓ 复制并打补丁：${outputs.size} 个文件（docs ${docsCount} 篇）`);

  // 重建索引（派生物，不在源仓库内复制）
  execFileSync(process.execPath, [join(TARGET, 'scripts/build-agent-index.mjs')], { cwd: TARGET, stdio: 'inherit' });

  if (readmeOut) {
    writeFileSync(readmeAbs, restoreEol(readmeOut.text, readmeOut.eol), 'utf8');
    console.log('  ✓ 校准 README.md 篇数');
  }
}

// ---- 9. 校验：产物内不得残留内部痕迹 ----
// 非 --check 时读盘；--check 时用「应然状态」——本轮写入的内容 + 未被删除的现存文件。
const scan = new Map();
if (CHECK) {
  for (const [dst, { text }] of outputs) scan.set(dst, text);
  if (readmeOut) scan.set('README.md', readmeOut.text);
  for (const f of walk(TARGET)) {
    const rel = toPosix(relative(TARGET, f));
    if (rel.startsWith('.git/') || stale.includes(rel) || scan.has(rel) || rel === 'README.md') continue;
    scan.set(rel, normalizeEol(readFileSync(f, 'utf8')).text);
  }
} else {
  for (const f of walk(TARGET)) {
    const rel = toPosix(relative(TARGET, f));
    if (rel.startsWith('.git/')) continue;
    scan.set(rel, normalizeEol(readFileSync(f, 'utf8')).text);
  }
}

const hits = [];
for (const [rel, text] of scan) {
  for (const { re, label } of FORBIDDEN) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) {
      const line = text.slice(0, m.index).split('\n').length;
      hits.push(`${rel}:${line}  ${label} → ${m[0]}`);
    }
  }
}
if (hits.length) {
  console.error(`\n✗ 校验失败：${CHECK ? '同步后仍有' : '产物内仍有'} ${hits.length} 处内部痕迹，请补替换规则后重跑`);
  hits.forEach((h) => console.error(`   ${h}`));
  process.exit(1);
}
console.log(`\n✓ 校验通过：${CHECK ? '按同步后状态预演，' : ''}无内部痕迹（扫描 ${scan.size} 个文件）`);
const dead = RULES.map((r, i) => (ruleHits[i] === 0 ? `  - ${r.file}：${r.from.slice(0, 40)}…` : null)).filter(Boolean);
if (dead.length) {
  console.warn(`⚠ 有 ${dead.length} 条替换规则未命中任何文件（源文本可能已变，规则待更新）：`);
  dead.forEach((d) => console.warn(d));
}
if (CHECK) console.log('\n（--check 未写入任何文件；去掉该参数即执行同步）');
else console.log(`\n下一步：cd ${TARGET} && git status 复核差异 → git commit → git push`);


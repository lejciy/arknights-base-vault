# RIIC-KnowledgeAgent 外部参考

> 记录上游仓库 [Pegaiur/RIIC-KnowledgeAgent](https://github.com/Pegaiur/RIIC-KnowledgeAgent)（引入时 commit `b24af3e`，2026-09-08 clone）与本库的关系。本目录属 meta 写作支撑层，**不入 RAG 语料**。

## 那是什么项目

明日方舟基建 RAG 查询 Agent 及其成本基准测试工具集（TypeScript/pnpm，Qwen3.7-Flash via DashScope）。`knowledge/` 是其数据层：`references/`（arkntools 生成的机械事实真源）、`base/`（机制基线语料）、`guides/`（审定玩家散文）、`raw/`（原始语料，不入其检索白名单）。

## 与本库的血缘

- 其 `raw/` = 本库 `docs/练卡推荐相关/`，内容零差异（仅换行符）；多出一篇 `心情消耗恢复与工休时间.md`。
- 其 `base/机制-*.md` 是本库 `docs/0-规则/` 的 RAG 散文清洗重写版：去掉 front matter 与求解向公式、剥离决策经验，来源改为 PRTS 2026-09-03 重抓（本库原文为 2026-06-21 knightcode/PRTS 混合源）。**未引入本库**，可作为机制文档逐篇校对的新抓取对照。
- 其 `guides/`（贸易站组合/制造站组合/跨设施组合/高效率散件/新手培养）已按新命名体系重写组合知识，2026-09-08 引入本库模块3/6；其 `references/` 13 篇引入 `docs/6-干员技能/`。

## 本目录文件

- `查询Agent决策契约.md` — 其 `knowledge/AGENTS.md`：查询 Agent 的人工指令源（检索工具使用规则、口径核对清单、作答边界），可与本库 `meta/templates/SYSTEM_PROMPT.md` 对照参考。
- `corpus-manifest.json` — 其 RAG 语料白名单（30 篇，raw/ 不在内），可对照检验本库语料边界划分。

## 已知实质性分歧（裁决前勿合并）

1. **技能叠加顺序**：其 `base/机制-后勤技能结算.md` 明确否定本库 `0-规则/buff叠加模型.md` 的九步统一顺序，主张"只确认技能原文声明的局部关系"。需对照其 2026-09-03 PRTS 重抓语料校对后裁决。
2. **组合命名**：其 guides 实体化了练卡推荐《组合知识库》的改名裁决（感知信息组/龙舌兰组/格拉斯哥帮组、但书与叙拉古解绑、但书为全基建核心散件），与本库 `docs/2-体系/` 旧命名文档现已实体共存于模块3。
3. 其 guides 将本库多篇旧体系散文（企鹅物流、灵孑银崖喀兰、散件干员速查中枢部分等）标记为"已废弃（2026-09-03）"，本库尚未跟进该裁决。

本地 clone 位置（未入库）：`D:\其他\方舟\RIIC-KnowledgeAgent`。

# RIIC-Web 技能数据镜像（模块2 数据真源）

> 干员基建技能原文的**机器可读真源**。`docs/2-干员技能/` 的 Markdown 快照由此类数据派生（经 RIIC-KnowledgeAgent 渲染），本目录持有原始 JSON，供脚本消费与快照刷新核对。
> 引入日期：2026-09-08。不入 RAG。

## 出处（双层来源）

| 层 | 仓库 | commit |
|---|---|---|
| 引入通道 | `KnightCodeSquareMatrix/RIIC-Web`（`src/generated/arkntools/`，原样镜像） | `a4279694bad3fa846d84c35c452d2028f914e5e9`（2026-09-08，"chore: 同步 arkntools 干员资源"） |
| 数据源头 | `arkntools/arknights-toolbox-data`（见 `src/generated/arkntools/source.json`） | `302105b1404bd488c4700d063da9dcf3661a94f0` |

数据规模：干员 429 / 基建技能 755 / 术语 82（`source.json` 内含清单）。

## 目录结构

```
维护更新说明.md                  操作真源：字段口径、解锁/提升规则、刷新流程、使用示例
src/generated/arkntools/*.json   原样镜像，只读，勿手改（真源）
clean/*.json                     纯文本清洗版，脚本生成，勿手改
../../scripts/clean-riic-skills.mjs   清洗脚本（仓库根 scripts/ 下）
```

各文件内容：

| 文件 | 内容 |
|---|---|
| `building-skill-catalog.json` | 基建技能目录：id / name / description(Rich) / tags / icon(仅 raw) |
| `operator-catalog.json` | 干员目录：id / name / rarity / profession / position / portrait(仅 raw) / buildingSkills（技能 id + elite/level 解锁条件） |
| `term-catalog.json` | 官方术语表（desc / descText 双版本） |
| `operator-rarities.json` | 干员 → 星级 |
| `source.json` | 上游出处与资源清单（provenance） |

清洗版差异（raw → clean）：

- 富文本标记全部剥除，`descriptionRich` → `description` 纯文本。标记只有两种：配对标签 `<@cc.kw|vup|vdown|rem>文字</>`（保留文字）与自包含占位符 `<$cc.xxx>`（删除，显示名永远由紧随的配对标签携带，已全量核对无信息损失）。
- 删除图片路径字段：技能 `icon`、干员 `portrait`（指向 RIIC-Web 本地资源，在本库无意义）。
- `term-catalog` 取上游自带 `descText` 为 `desc`。
- 干员每个技能槽位新增 `unlock` 中文解锁标签（「初始/等级N/精英N」×「解锁/提升」，与 RIIC-Web 部署站点口径一致），干员附 `professionLabel` 职业中文名，`elite`/`level`/`profession`/`position` 原始字段保留。
- 新增 `operator-skill-text.json`：干员技能**全文视图**（技能文本 × 解锁口径合并，对应站点技能查询页形态），日常引用优先用它。
- 新增 `skill-terms.json`：**词条/类别集中索引**（官方术语、描述内占位词条及其显示文字与引用技能、技能标签词汇、设施前缀映射），「作业平台」这类词条的释义与技能关联查这里；引用词条的官方弹窗释义同时以 `termRefs` 内嵌进每个技能条目（自包含）。
- 干员技能解锁条件仅有 elite/level（无潜能字段）——与裁决一致：基建技能解锁不需要潜能条件。

**字段语义、口径分布表、提升判定规则与典型形态见 [`维护更新说明.md`](维护更新说明.md)。**

## 刷新方式

详见 [`维护更新说明.md`](维护更新说明.md) §4（含下载命令模板、校验基线与差异登记步骤）。概要：按新 commit 覆盖 `src/generated/arkntools/` → 更新本 README 出处表 → 重跑 `node scripts/clean-riic-skills.mjs`（仓库根执行）。

## 已知口径

- 本真源（arkntools@`302105b`）**新于** `docs/2-干员技能/` Markdown 快照的底料（arkntools@`4d47475`，747 技能/425 干员/81 术语），即快照落后本源 8 技能/4 干员/1 术语。快照刷新依赖上游 RIIC-KnowledgeAgent 重跑 `build_refs.py` 后整体重新引入；差异登记见 `知识库模块设计.md` §2.2。
- `operator-catalog` 的 `profession`/`position` 为数值代码（非文本），如需语义化在上游消费侧映射。

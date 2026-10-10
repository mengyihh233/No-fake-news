# 报告 JSON 结构 v1.2（兼容 v1.0 / v1.1）

UTF-8 JSON。以下字段供网页与独立 HTML 渲染器共同使用。材料包保存事实和出处；模型生成的解释不得修改服务器检索得到的来源 URL、日期或摘录。

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 新研究使用 `1.1`；附校验过的引文复核用 `1.2`；已有 `1.0` / `1.1` 继续可读 |
| `topic`、`scope` | 原始问题、核查的时间/地域/定义边界 |
| `language` | 正文语言：`zh-CN`（回退）、`en` 或 `ja`；语言不改变证据标准 |
| `summary_language` | 后加判断的语言或 null；既有证据与 observations 不自动翻译 |
| `source_policy` | `balanced`（默认）或 `preferred-only`，须披露限定覆盖范围 |
| `preferred_sources` | 最多 6 个非秘密 `{url, label}`；实际纳入资料仍看 evidence |
| `mode` | `evidence-only` 或 `ai-summary` |
| `depth` | `brief`、`standard`（默认）或 `deep`，独立于 mode |
| `generated_at` | 带时区的实际生成时间 |
| `limitations` | 限制和取证缺口，字符串数组 |
| `claims` | `{id, text, kind}`；kind 为 fact/causal/prediction/value/mixed |
| `evidence` | 下文所列来源对象 |
| `links` | `{from, to, relation, note}`；来源 ID → 命题 ID |
| `timeline` | `{date, title, detail, evidence_ids}` |
| `charts` | `{title, unit, kind, points, note}`；kind 为 bar/line |
| `comparisons` | `{case, date, similarities, differences, limits, evidence_ids}` |
| `observations` | 两模式共享：`{kind, text, claim_ids, evidence_ids}`，kind 为 data/logic/history；有引用的中性比对分析，不是真假裁决 |
| `questions` | 尚待核查的问题，字符串数组 |
| `search_log` | `{query, intent, provider, result_count, ran_at}` |
| `reasoning` | 仅 AI 总结：`{id, premise_ids, claim_id, text, kind}` |
| `summary` | 仅 AI 总结：`{text, verdict, caveats, evidence_ids}` |

所有命题 ID 为 C1…，来源为 E1…，公开论证为 R1…。必须唯一且引用已存在对象，论证只引用证据或更早的论证，不建立循环。不要凭图表数量推断证据充分程度。

每个来源包含：

```json
{
  "id": "E1",
  "title": "已打开的来源标题",
  "url": "https://example.org/original",
  "publisher": "发布机构",
  "published_at": null,
  "retrieved_at": "2026-10-09T10:00:00+08:00",
  "source_type": "unknown",
  "content_kind": "full_text",
  "excerpt": "与命题有关且保留原文措辞、空白及上下文的短摘录。",
  "context": "定位、访问限制、翻译或转述说明。",
  "source_family": "同源转引使用相同标识",
  "status": "retrieved",
  "claim_ids": ["C1"],
  "screenshots": []
}
```

`source_type` 为 primary/secondary/unknown；`content_kind` 为 full_text/search_extract/snippet；`status` 为 retrieved/snippet_only/unavailable。搜索摘要不是已读取全文。excerpt 不能超过来源允许的引用额度，大段正文不进入公开导出；缩短原文引用并注明省略，转述另写说明，不能冒充精确引句。

实际截图对象：`{url, captured_at, sha256, source_url}`。网页应用的 url 可为 `/captures/<文件>.png`；独立渲染器使用 `{path, captured_at, sha256, source_url}`，path 为相对 JSON 文件的真实本地图片路径。哈希必须实际计算；缺失不补造。图片源网址应与来源一致（合法跳转注明）。

图表每点：`{label, value, evidence_ids}`，value 为有限数值或 null。null 表示缺失，不能当作零；保留单位、口径和计算说明。没有数据则 charts 为空。时间线是事件日期，不能用发布或访问日期冒充。

网页应用还支持从所引摘录确定性计数：点上附 `calculation: {operation: "count", source_quotes: ["摘录里精确存在且互不重复的条目"], description: "纳入/排除口径"}`，value 必须等于条目数。0 可以用空条目，但必须说明完整清单口径；程序不能自动证明清单涵盖全集。其他换算或推算应在单独经过复核的计算流程完成，不让模型补出数字。

`links.relation` 可为 relevant_to/supports/contradicts/qualifies/context；后四项中的支持/反驳属于 AI 解释。自行判断模式只保留 relevant_to/context，并去掉原支持/反驳注释；按时间或原始来源顺序呈现，不按结论排序。

## 两种模式的真实数据边界

自行判断模式采用字段白名单投影，必须删除 `summary`、`reasoning`、每个 claim 的 `verdict`/`analysis` 以及支持/反驳边上的推论注释。HTML、可下载 JSON、内嵌脚本、页面标题和无障碍文本同样遵守，不能仅用 CSS 隐藏。

`observations` 始终保留。它说明数据口径、公开论证成立所需的前提、历史案例的异同与混杂因素；不使用全局真假判决或立场评价。每项引用已有的命题和证据。深入档的网页报告最多 24 个来源、8 条初轮查询，加最多 2 条可选补充查询；简要和标准仍使用相同字段。

scope/limitations/excerpt/questions/chart.note 等自由文本也应遵守所选模式；结构过滤无法自动识别自然语言里的所有暗含倾向，因此仍需检查措辞和选择偏差。自行判断保留客观可重算的数字以及可比性差异，但不输出总裁决。

AI 总结模式的每条结论/推论有可定位的引用。`summary` 本身不冒充证据；不确定时说明哪些新材料可以改变结论。

## 语言与非秘密来源元数据

`--language zh-CN|en|ja` 只切换渲染标签和提示，省略时沿用报告 language 或 zh-CN，不翻译既有正文。原始标题、excerpt、精确 source_quotes、查询词、URL、数值、日期、截图跨语言保持一致；翻译另行标明。后加总结语言不同则记录 summary_language，保留原基础分析。

## v1.1 引文与检索元数据

新研究的每条 observations、timeline、comparisons、reasoning、claim_assessments 和 summary 均带非空 `citations: [{evidence_id: "E1", quote: "E1 展示摘录中的逐字原句"}]`。包括空白与原语言在内逐字匹配，来源须属于该条 evidence_ids 或推理前提可追溯的证据。没有原句时省略无依据的事实条目，把缺失写入 questions/limitations。对 `1.0` 追加的新判断也提供精确引句，旧基础资料保持原样，不为旧资料补造定位。

网页服务器生成 `verification: "exact_match"`、`semantic_support: "unverified"` 与 `locator: {start, end, prefix, suffix, excerpt_sha256, match_count, coordinate_system: "unicode_codepoints"}`。`[start,end)` 为**保存摘录**的 Unicode 码点位置，不是原网页或 PDF 页码。前后文各最多 80 字符，重复引句定位首处并记录全部精确匹配次数。`excerpt_sha256` 是摘录 UTF-8 的小写 SHA-256，证据也可带 `excerpt_metadata: {sha256, coordinate_system: "unicode_codepoints"}`。元数据须对应实际文本，模型不生成服务器验证字段。缺少确定性校验工具的宿主 Skill 使用 `1.0` 保留普通 `{evidence_id, quote}`，不得声称已经服务器校验。导入/渲染的一致性不认证来源真实性或语义支持。

图表输入 `source_quote` 或 `calculation.source_quotes` 经校验后保留为 `citations`；数值须在对应引句中，每个计数条目有匹配引文。缺失值仍为 null；空清单零值无条目可引，必须保留已有完整性限制。

证据可选字段：`document_format` 为 `unknown|html|text|pdf|csv|tsv`；`content_sha256` 为 null 或本次取得**响应字节**的小写 SHA-256，与摘录哈希不同。`source_family_method` 为 `domain|exact_content|exact_excerpt|near_duplicate`；`source_family_evidence_ids` 列出关联的现有证据 ID。这是可能经其他条目传递的暂定依赖提示，不证明所有权、独立报道、真假或出版者签名。不能从提取文字或搜索摘要伪造响应字节哈希。

`search_log` 增加 `round: "initial"|"supplemental"` 与 `gap_claim_ids: ["C1"]`，总计最多 10 条。`retrieval_gaps` 最多 12 条 `{claim_id, reason: "no_keyword_match"|"limited_families", query, attempted}`，记录**初轮**启发式快照。已派发的查询也可能失败，失败另行披露，不能记作成功的零结果。没有缺口或 `attempted=true` 均不认证完整覆盖或论断成立。网页请求 `adaptive_search` 默认 false；开启后简要/标准/深入最多额外 1/2/2 查询，可能增加费用，来源总量和时限不变。独立 Skill 的实际执行上限由宿主工具与用户预算决定。

preferred_sources 只记录显式指定的 URL/标签，不证明访问成功。任何字段、网址、搜索记录、截图或导出均不得包含密码、Cookie、Authorization、Bearer token、MFA 等秘密。网页账户凭据只保存在内存并绑定精确 origin；认证来源禁止截图。正文送外部 AI 前须知情，限定来源模式须披露范围限制。

## v1.2 可选引文复核快照

仅 AI 总结报告可携 `citation_review`，资料模式响应和导出完整删除。`1.2` 沿用全部 `1.1` 精确引文要求，也允许没有复核（如资料模式投影）。旧 `1.0` / `1.1` 继续可读；服务器实际附加复核并升级前，`1.1` 不存复核元数据。

`citation_review` 包含 `generated_at`（1–100 字符）、`language`（`zh-CN|en|ja`）、`model`（1–200）、`method: "ai_advisory"`、`available_targets`（0–323）、`selected_targets`（0–40）、`reviewed_targets`（0–40）、`not_reviewed_targets`（0–323）、`capacity`（简要/标准/深入为 12/24/40）、`input_character_limit: 120000`、`input_characters`（0–120000）及 `items`（0–40）。整数计数不是置信度或真假分数。已复核量等于唯一条目数，未复核量等于总量减已复核量；提交量/输入量须符合服务器按容量与输入预算重算的选择。

每项包括 `target_id`、64 位小写十六进制 `target_sha256`、`relation`（`aligned|partial|unsupported|conflicting|unclear`）、最多七个不重复 `issues`（`scope|time|definition|causality|numeric|translation|context`）、`explanation`（1–3000）及 1–100 个既有完整 `Citation`。引文须为目标原引用的子集，保留原句与精确定位，不新增证据或改变 `semantic_support`；解释按转义纯文本呈现。

目标 ID：`summary`、`claim:C1`、`reasoning:R1`、`observation:1`、`timeline:1`、`comparison:1`、`chart:1:point:1`（数字从 1 开始）。仅有完整精确引文者合格。先总结，再按观察、已评判命题、时间线、图表点、历史比较、推论六类轮转。逐项试加入，达到容量则停止；超过输入上限的目标跳过并继续后项。user-message JSON 保留 Unicode、使用默认分隔符，按 Unicode 码点计长至 120,000，固定系统指令和 schema 另有开销，不截断引句/陈述/摘录。[证据边界](../../../docs/EVIDENCE.md)说明覆盖与费用。

服务器快照绑定 `target_id`、`statement: {report_topic, report_scope, content}`、目标全部已存 `citations` 及按首见证据排序去重的 `context: [{evidence_id, title, context, excerpt}]`。`content` 为可见目标去掉 citations，图表另含 title/unit/kind/note 和 point，补齐模型默认字段。哈希递归把非布尔数转固定十进制字符串，去小数尾零和尾点，负零归 `"0"`；再将保留 Unicode、键排序、紧凑分隔符的 JSON 按 UTF-8 算 SHA-256。元数据由服务器生成，模型不得编造；它仅检查快照一致性，不认证 AI 作者、正确性或来源。更新分析清除过时复核。

无确定性服务器能力的独立宿主可按用户请求用 `1.0` 可选判断字段提供语义建议，不得捏造 `1.2` 快照或声称服务器已核验。离线渲染器只校验和显示既有复核，不调用 AI/搜索。

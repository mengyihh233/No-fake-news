# 报告 JSON 结构 v1.0

UTF-8 JSON。以下字段供网页与独立 HTML 渲染器共同使用。材料包保存事实和出处；模型生成的解释不得修改服务器检索得到的来源 URL、日期或摘录。

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 固定字符串 `1.0` |
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
  "excerpt": "与命题有关且保留上下文的短摘录或明确标为转述的内容。",
  "context": "定位、访问限制、翻译或转述说明。",
  "source_family": "同源转引使用相同标识",
  "status": "retrieved",
  "claim_ids": ["C1"],
  "screenshots": []
}
```

`source_type` 为 primary/secondary/unknown；`content_kind` 为 full_text/search_extract/snippet；`status` 为 retrieved/snippet_only/unavailable。搜索摘要不是已读取全文。excerpt 不能超过来源允许的引用额度；大段正文不进入公开导出，必要时使用简短忠实转述并注明。

实际截图对象：`{url, captured_at, sha256, source_url}`。网页应用的 url 可为 `/captures/<文件>.png`；独立渲染器使用 `{path, captured_at, sha256, source_url}`，path 为相对 JSON 文件的真实本地图片路径。哈希必须实际计算；缺失不补造。图片源网址应与来源一致（合法跳转注明）。

图表每点：`{label, value, evidence_ids}`，value 为有限数值或 null。null 表示缺失，不能当作零；保留单位、口径和计算说明。没有数据则 charts 为空。时间线是事件日期，不能用发布或访问日期冒充。

网页应用还支持从所引摘录确定性计数：点上附 `calculation: {operation: "count", source_quotes: ["摘录里精确存在且互不重复的条目"], description: "纳入/排除口径"}`，value 必须等于条目数。0 可以用空条目，但必须说明完整清单口径；程序不能自动证明清单涵盖全集。其他换算或推算应在单独经过复核的计算流程完成，不让模型补出数字。

`links.relation` 可为 relevant_to/supports/contradicts/qualifies/context；后四项中的支持/反驳属于 AI 解释。自行判断模式只保留 relevant_to/context，并去掉原支持/反驳注释；按时间或原始来源顺序呈现，不按结论排序。

## 两种模式的真实数据边界

自行判断模式采用字段白名单投影，必须删除 `summary`、`reasoning`、每个 claim 的 `verdict`/`analysis` 以及支持/反驳边上的推论注释。HTML、可下载 JSON、内嵌脚本、页面标题和无障碍文本同样遵守，不能仅用 CSS 隐藏。

`observations` 始终保留。它说明数据口径、公开论证成立所需的前提、历史案例的异同与混杂因素；不使用全局真假判决或立场评价。每项引用已有的命题和证据。深入档的网页报告最多 24 个来源、8 条搜索记录；简要和标准仍使用相同字段。

scope/limitations/excerpt/questions/chart.note 等自由文本也应遵守所选模式；结构过滤无法自动识别自然语言里的所有暗含倾向，因此仍需检查措辞和选择偏差。自行判断保留客观可重算的数字以及可比性差异，但不输出总裁决。

AI 总结模式的每条结论/推论有可定位的引用。`summary` 本身不冒充证据；不确定时说明哪些新材料可以改变结论。

## 语言与非秘密来源元数据

`--language zh-CN|en|ja` 只切换渲染标签和提示，省略时沿用报告 language 或 zh-CN，不翻译既有正文。原始标题、excerpt、精确 source_quotes、查询词、URL、数值、日期、截图跨语言保持一致；翻译另行标明。后加总结语言不同则记录 summary_language，保留原基础分析。

preferred_sources 只记录显式指定的 URL/标签，不证明访问成功。任何字段、网址、搜索记录、截图或导出均不得包含密码、Cookie、Authorization、Bearer token、MFA 等秘密。网页账户凭据只保存在内存并绑定精确 origin；认证来源禁止截图。正文送外部 AI 前须知情，限定来源模式须披露范围限制。

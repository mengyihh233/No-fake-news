---
name: tell-me-truth
description: "联网事实核查与可复核资料分析 / Evidence-based fact checking / 検証可能な資料分析。支持简体中文、English、日本語；可选判断与独立分析深度。"
---

# tell me truth

中文 · English · 日本語。输入论题、新闻、问题或情景，生成可追溯来源的数据、逻辑与历史比较；判断可选，深度独立可选。不承诺绝对无偏或终极真相。

Turn a claim, news item, question, or scenario into a traceable evidence report with data, logic, and historical comparisons. Verdicts are optional; depth is independent. Do not promise absolute neutrality or final truth.

主張・ニュース・質問・状況を、出典をたどれるデータ・論理・歴史比較のレポートにします。判定は任意、深さは独立して選択します。完全な無偏向や最終的な真実を保証しません。

v0.3：保留原样引文与可复核定位，只报告实际研究进度。用户可另选 AI 复核引用关系；须说明同模型、额外调用费用及未复核范围。无确定性服务器能力的宿主沿用 `1.0`，不自造 `1.1` 定位或 `1.2` 复核元数据。详见对应语言使用说明。

v0.3: retain original quotes and reproducible locations; report actual research progress. Users may request an AI review of citation relationships; disclose the same model, extra call costs, and unreviewed scope. Hosts without deterministic server capabilities use `1.0`, never invented `1.1` locators or `1.2` review metadata. See the matching usage reference.

v0.3：原文引用と再計算できる位置を保持し、実際の調査進捗のみ表示します。引用関係の AI 確認は任意で、同じモデル、追加料金、未確認範囲を明記します。確定的なサーバー機能のない環境は `1.0` を使い、`1.1` の位置情報や `1.2` の確認メタデータを捏造しません。各言語の使用手順を参照してください。

## Read the complete instructions / 阅读完整说明 / 詳細手順

Select the user's requested language, otherwise the conversation language; fall back to `zh-CN`. Read the matching usage, methodology, and report-format files before research. All three versions carry the same requirements.

优先用户指定语言，其次对话语言，无法判断时使用 `zh-CN`。开始研究前完整阅读对应语言的使用说明、核查方法与报告结构；三语要求一致。

ユーザーが指定した言語を優先し、指定がなければ会話の言語、不明なら `zh-CN` を使います。調査前に該当言語の使用手順・方法・形式をすべて読みます。要件は三言語で共通です。

| Language | Usage | Methodology | Report format |
| --- | --- | --- | --- |
| 简体中文 `zh-CN` | [完整使用说明](references/usage.zh-CN.md) | [核查方法](references/methodology.md) | [报告结构](references/report-format.md) |
| English `en` | [Complete usage](references/usage.en.md) | [Methodology](references/methodology.en.md) | [Report format](references/report-format.en.md) |
| 日本語 `ja` | [詳しい使い方](references/usage.ja.md) | [検証方法](references/methodology.ja.md) | [レポート形式](references/report-format.ja.md) |

Default: `mode=evidence-only`, `depth=standard`. Both modes retain cited neutral analysis; only `ai-summary` adds verdicts. `brief/standard/deep` change coverage, never the evidence standard.

默认：列出信息自行判断、标准深度。两模式均保留有来源的中性分析，AI 总结才增加判断。深度改变覆盖范围，不改变证据标准。

既定：資料を見て自分で判断・標準の深さ。両モードで出典付きの中立的分析を残し、AI 要約のみ判定を追加します。深さは調査範囲を変え、証拠基準は変えません。

Preserve original excerpts, exact source quotes, URLs, numbers, and screenshots across languages. Never fabricate completed research or screenshots. Honor source restrictions, network/cost limits, and authorized account access; never put credentials in reports. Disclose external AI processing of retrieved content.

语言切换保留原始摘录、精确引句、网址、数值与截图。不得伪造查证或截图；尊重来源范围、联网/费用限制及账户授权，报告不得包含凭据。正文送外部 AI 前须让用户知情。

言語を変えても原文の抜粋・正確な引用・URL・数値・画像を保持します。調査済み資料や画像を捏造せず、情報源・ネット接続・費用・アカウント利用の制約を守ります。認証情報をレポートに含めず、外部 AI に本文を送信する場合は事前に知らせます。

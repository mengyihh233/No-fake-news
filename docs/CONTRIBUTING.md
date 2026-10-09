# Contributing / 贡献 / 貢献

[English README](../README.md) · [中文说明](../README.zh-CN.md) · [日本語 README](../README.ja.md)

## English

Start with a small issue or pull request explaining the user-visible problem, proposed behavior, and relevant evidence. Use synthetic or public fixtures; remove personal data, credentials, and private source content. Security reports follow [SECURITY.md](SECURITY.md).

Run `python -m pytest tests -q` and `node --test tests/*.cjs`. Add meaningful regression tests for changed trust boundaries or report semantics. Provider tests should use mocks; do not require paid accounts in CI. For a browser change, inspect all three languages and both report modes.

Maintain these invariants:

- Evidence-only output must not contain AI verdicts or evaluative reasoning, including in exports.
- Quotes, screenshots, source URLs, units, timestamps, and numeric values must not be fabricated or silently translated.
- Every comparison, chart, and public inference must cite existing evidence IDs. Missing data is not zero.
- New visible text needs zh-CN, en, and ja translations. Keep report language separate from UI language; preserve original excerpts.
- Credentials must not enter browser storage, logs, reports, model prompts, search requests, or another origin. Preserve SSRF defenses.
- Declare actual research limits and uncertainty. Search volume or model consensus is not a truth score.

Original project contributions are provided under the [MIT license](../LICENSE). Attribute third-party materials separately; the project license does not relicense them.

## 简体中文

通过小范围 issue 或 PR 说明用户遇到的问题、预期行为及相关证据。使用合成或公开测试材料，删除个人数据、凭据及私有正文。安全问题遵循 [SECURITY.md](SECURITY.md)。

运行 `python -m pytest tests -q` 和 `node --test tests/*.cjs`。信任边界或报告语义改变时添加有效回归测试。供应商调用用模拟响应，CI 不依赖付费账户。界面改动须观察三种语言及两种模式。

- 资料模式及导出不能含 AI 裁决或评判性推论。
- 引文、截图、网址、单位、时间及数值不得编造或悄悄翻译。
- 比较、图表及公开推论必须引用存在的证据 ID；缺失不等于零。
- 新增可见文字须提供 zh-CN、en、ja；界面语言与报告语言分开，保留原始摘录。
- 凭据不得进入浏览器存储、日志、报告、模型提示、搜索请求或其他来源；保留 SSRF 防护。
- 披露实际研究范围和不确定性，搜索量及模型共识不是可信度分数。

原创贡献采用 [MIT](../LICENSE)。第三方材料单独注明，项目许可证不改变其条款。

## 日本語

小さな issue / PR で利用者の問題、期待する動作、関連する根拠を説明してください。合成または公開のテスト資料を使用し、個人情報、認証情報、非公開本文を除いてください。セキュリティ報告は [SECURITY.md](SECURITY.md) に従います。

`python -m pytest tests -q` と `node --test tests/*.cjs` を実行します。信頼境界や仕様の変更には有効な回帰テストを追加してください。提供元呼出しはモックを使い、CI は有料アカウントに依存させません。UI 変更は三言語と両モードを確認します。

- 資料モードと書出しに AI 判定や評価的推論を含めないこと。
- 引用、画像、URL、単位、時刻、数値を捏造したり黙って翻訳したりしないこと。
- 比較、グラフ、公開論証は存在する証拠 ID を引用し、欠損とゼロを区別すること。
- 可視テキストは zh-CN / en / ja を用意し、UI 言語と本文言語を分け、原文抜粋を保持すること。
- 認証情報を保存領域、ログ、レポート、モデル、検索、別オリジンへ渡さず、SSRF 対策を保持すること。
- 実際の範囲と不確実性を明示し、検索量やモデルの一致を真実度にしないこと。

オリジナルの貢献には [MIT](../LICENSE) を適用します。第三者資料は別途出典を示し、独自の条件を保持します。

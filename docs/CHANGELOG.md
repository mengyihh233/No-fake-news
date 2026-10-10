# Changelog / 更新记录 / 変更履歴

## 0.3.0 — 2026-10-10

### English

- Real SSE research stages and actual completed-query/retrieval counts, including unknown or changing totals; no simulated percentage, ETA, or streamed model tokens.
- Canceling stops subsequent local tasks; already-dispatched provider calls and fees cannot be recalled or refunded by this app.
- Optional AI review of citation relationships for existing AI-summary `1.1` / `1.2` reports: one extra call to the same configured model, no new search/retrieval, and an upfront cost explanation.
- Depth caps of 12 / 24 / 40 targets and a 120,000-codepoint input limit; all omissions remain explicitly unreviewed. AI advice is separate from exact matching and is not independent verification or a truth score.
- Schema `1.2` attaches report-bound review snapshots and original citation subsets. Import/export and the standalone renderer validate target hashes, exact locators, selection, and counts; evidence-only projection removes the entire review.
- Three-language roadmap separates planned improvements from shipped features.
- Three-language UI, README, evidence boundaries, Skill references, and offline review display. Existing `1.0` / `1.1` remain readable; standalone hosts must not invent server metadata.

### 简体中文

- SSE 展示真实研究阶段及已完成查询/抓取计数，允许未知或变化总数，不模拟百分比、剩余时间或模型逐字流。
- 中止停止本机后续任务；应用不能撤回已发给供应商的调用或保证退费。
- 已有 AI 总结 `1.1` / `1.2` 可选引文关系复核：同一配置模型额外调用一次，不新增搜索/抓取，事前说明可能收费。
- 深度上限 12 / 24 / 40 目标及 120,000 码点输入限制，全部省略项明确未复核；AI 建议与逐字匹配分开，不是独立核实或真假评分。
- `1.2` 附报告快照绑定的复核及既有引文子集；导入/导出、离线渲染核验目标哈希、精确定位、选集和计数；资料模式完整删除复核。
- 三语路线图区分后续优化规划与已发布功能。
- 界面、README、证据边界、Skill 参考和离线展示同步三语。旧 `1.0` / `1.1` 可读，独立宿主不得编造服务器元数据。

### 日本語

- SSE で実際の調査段階と完了した検索・取得件数を表示。総数不明・変動を扱い、百分率、残り時間、モデルの逐語出力を模擬しません。
- 中断は以後のローカル処理を停止しますが、送信済みの呼出しの取消しや返金は保証しません。
- 既存 AI 要約 `1.1` / `1.2` に任意の引用関係確認。同じ設定のモデルを追加一回呼び、再検索・再取得せず、料金の可能性を事前に説明します。
- 深さ別の 12 / 24 / 40 対象と 120,000 コードポイントの入力上限。省略はすべて未確認で、AI の助言は文字一致と別であり、独立検証・真偽の点数ではありません。
- `1.2` はレポート快照に結ぶ確認と既存引用の部分集合を保持。読込・書出し・独立描画で対象ハッシュ、精確位置、選択、件数を検査し、資料モードは確認全体を削除します。
- 三言語のロードマップは今後の計画と提供済み機能を区別します。
- UI、README、証拠の限界、Skill 参照、オフライン表示を三言語で更新。既存 `1.0` / `1.1` も読め、独立ホストはサーバー情報を捏造しません。

## 0.2.0 — 2026-10-10

### English

- Exact quotations with extract positions, context, fingerprints, and first-occurrence ambiguity; server-issued passage IDs make generation reliable without treating approximate text as original.
- Optional supplemental retrieval, default off, with initial gap markers and visible search rounds, within existing source/time budgets.
- Bounded text-based PDF, HTML-table, CSV, and TSV extraction; PDF workers have hard time/memory limits and receive no API keys.
- Provisional duplicate-source grouping, with explicit methods and related evidence IDs.
- Request-wide known website credential checks on source URLs and retrieval/screenshot redirects, while authentication headers remain origin-bound.
- Three-language UI, export, README, and Skill updates; existing `1.0` reports remain readable alongside new `1.1` research.
- One bounded analysis repair after failed validation, disclosed on success; exact matching does not establish semantic support or truth.

### 简体中文

- 精确引文展示摘录定位、上下文、指纹及重复匹配，服务器提供片段编号，避免把模型近似文字当原文。
- 默认关闭的可选补充检索，记录初轮缺口与搜索轮次，来源总量和时限不变。
- 有限的文本型 PDF、HTML 表格、CSV/TSV 提取；PDF 独立解析有时间、内存硬限制，不接收 API 密钥。
- 暂定转载/重复来源谱系，显示依据与关联证据 ID。
- 来源 URL 和抓取／截图跳转统一检查本次已知网站凭据，认证请求头仍严格绑定来源。
- 界面、导出、README 和 Skill 同步三语；新研究用 `1.1`，继续读取旧 `1.0`。
- 校验失败后最多一次有时限的分析修复，成功时披露；精确文字匹配不证明语义支持或真假。

### 日本語

- 抜粋位置、文脈、指紋、重複一致を持つ精確引用。サーバーの断片 ID を使い、モデルの近似文を原文と扱いません。
- 初期値無効の任意補足検索。初回の不足とラウンドを記録し、情報源の総枠と時間は不変です。
- 有限のテキスト PDF、HTML 表、CSV/TSV 抽出。PDF は時間・メモリ制限付き別プロセスで、API キーを受け取りません。
- 分類方法と関連証拠 ID を示す暫定重複情報系統。
- 情報源 URL と取得・画像保存の転送でリクエスト全体の既知サイト認証情報を検査し、認証ヘッダーは同一オリジンに限定。
- UI、書出し、README、Skill を三言語で更新。新規は `1.1`、既存 `1.0` も読めます。
- 検査失敗後は時間内で一回のみ分析を修正し、成功時は明記します。文字一致は意味的裏付けや真偽を証明しません。

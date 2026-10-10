# Changelog / 更新记录 / 変更履歴

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

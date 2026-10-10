# レポート JSON 形式 v1.2（v1.0 / v1.1 互換）

UTF-8 JSON を使います。ウェブアプリと単独レンダラーは以下の項目を共有します。資料と出所を保存し、モデルの解釈が取得済みの URL・日付・抜粋を変更してはいけません。

| 項目 | 意味 |
| --- | --- |
| `schema_version` | 新規調査は `1.1`、検査した引用確認付きは `1.2`。既存 `1.0` / `1.1` も読める |
| `topic`・`scope` | 元の質問、期間・地域・定義の範囲 |
| `language` | 本文の言語：`zh-CN`（既定）、`en`、`ja` |
| `summary_language` | 後で追加した要約の言語または null。既存の証拠と分析は無断翻訳しない |
| `mode` | `evidence-only` または `ai-summary` |
| `depth` | `brief`・`standard`（既定）・`deep`。mode とは独立 |
| `source_policy` | `balanced`（既定）または `preferred-only`。制限範囲を開示 |
| `preferred_sources` | 最大 6 件の秘密を含まない `{url, label}`。実際の採用資料は evidence を参照 |
| `generated_at` | タイムゾーン付きの実際の作成日時 |
| `limitations` | 制約と不足の文字列配列 |
| `claims` | `{id, text, kind}`。kind：fact/causal/prediction/value/mixed |
| `evidence` | 以下の情報源オブジェクト |
| `links` | `{from, to, relation, note}`。証拠 ID → 主張 ID |
| `timeline` | `{date, title, detail, evidence_ids}` |
| `charts` | `{title, unit, kind, points, note}`。kind：bar/line |
| `comparisons` | `{case, date, similarities, differences, limits, evidence_ids}` |
| `observations` | 両モード共通：`{kind, text, claim_ids, evidence_ids}`。kind：data/logic/history。出典付き中立分析であり判定ではない |
| `questions` | 未解決の問いの文字列配列 |
| `search_log` | `{query, intent, provider, result_count, ran_at}` |
| `reasoning` | 要約専用：`{id, premise_ids, claim_id, text, kind}` |
| `summary` | 要約専用：`{text, verdict, caveats, evidence_ids}` |

主張は C1…、証拠は E1…、論証は R1…とし、一意で既存の参照に結びます。論証は証拠または先行する論証のみ参照し、循環しません。グラフの数で証拠の十分性を判断しません。

情報源オブジェクト：

```json
{
  "id": "E1",
  "title": "情報源の元タイトル",
  "url": "https://example.org/original",
  "publisher": "発行者",
  "published_at": null,
  "retrieved_at": "2026-10-09T10:00:00+08:00",
  "source_type": "unknown",
  "content_kind": "full_text",
  "excerpt": "原文の言い回し、空白、文脈を保持する短い抜粋",
  "context": "位置・アクセス制限・翻訳や言い換えの説明",
  "source_family": "同じ原資料の転載に共通の識別子",
  "status": "retrieved",
  "claim_ids": ["C1"],
  "screenshots": []
}
```

source_type は primary/secondary/unknown、content_kind は full_text/search_extract/snippet、status は retrieved/snippet_only/unavailable です。スニペットは閲覧済み本文ではありません。引用量の制限を守り、本文の大量コピーを公開しません。言語版を変えても、原タイトル・抜粋・正確な引用・検索語・URL・数値・日付・画像は保持し、翻訳は明示して別に追加します。

画像はウェブ版で `{url, captured_at, sha256, source_url}` を使い、url は `/captures/<file>` です。単独レンダラーは JSON を基準とする `{path, captured_at, sha256, source_url}`、または `--capture-dir` 付きアプリ URL に対応します。実ファイルからハッシュを計算し、不明値を捏造しません。出典 URL と画像の元 URL は一致させ、正当なリダイレクトは説明します。

グラフの各点は `{label, value, evidence_ids}` です。value は有限の数値または null で、null は欠損を意味し 0 ではありません。単位と集計・計算方法を残し、データがなければ charts を空にします。時系列には出来事の日付を使い、公開日・取得日で代用しません。

ウェブ版は確定的な件数計算にも対応します。`calculation: {operation: "count", source_quotes: ["引用抜粋に実在する重複のない項目"], description: "採用・除外基準"}` を付け、value を項目数と一致させます。0 は空一覧と明確な完全一覧の範囲説明を使えますが、プログラムは一覧が全集を網羅することを証明できません。他の換算は別の確認済み計算手順で行い、モデルに数値を補わせません。

links.relation は relevant_to/supports/contradicts/qualifies/context です。支持・反証・限定は解釈です。資料モードでは relevant_to/context のみを残し、評価的注記を削除します。日時または原資料順で並べ、希望する判定順に並べません。

## モードと言語の境界

資料モードは許可項目だけを出力し、summary、reasoning、claim の verdict/analysis、評価的な関連注記を削除します。HTML、ダウンロード JSON、埋め込みスクリプト、タイトル、アクセシビリティ文字列にも適用し、CSS で隠すだけにしません。

observations は両モードで保持します。集計基準、論証の必要条件、歴史上の共通点・差異・交絡要因を既存の主張・証拠 ID とともに説明し、全体の真偽や立場の評価はしません。詳細ウェブ調査は最大 24 資料・初回 8 検索、任意の補足は追加で最大 2 検索で、全深度が同じ形式を使います。

scope/limitations/excerpt/questions/chart.note などの自由文もモードを守ります。構造フィルターだけでは暗黙の誘導を全て検出できないため、表現と選択を確認します。再計算可能な数値・比較は残し、総合判定は出しません。要約の結論は証拠と推論に結び、要約そのものを証拠にしません。判定を変え得る資料を示します。

`--language zh-CN|en|ja` はラベルとエラーのみ変更し、省略時は report.language または zh-CN を使います。本文・引用は翻訳しません。要約だけ異なる言語なら summary_language を記録し、元の基礎分析を保持します。

## 秘密を含まない設定とアカウント

preferred_sources は明示された URL・ラベルであり、取得成功を意味しません。パスワード、Cookie、Authorization、Bearer token、MFA コード等をレポートの全項目・URL・検索記録・画像・出力に入れません。範囲のメタデータにも秘密を含めません。ウェブ版は認証情報をメモリー内だけに保持し、正確な origin に結び付け、認証資料の撮影を無効にします。本文を外部 AI に送る前に知らせます。指定先限定の調査は範囲の制限を開示します。

## v1.1 の引用と検索メタデータ

新規調査の observations、timeline、comparisons、reasoning、claim_assessments、summary は各項目に空でない `citations: [{evidence_id: "E1", quote: "E1 の表示抜粋に存在する原文"}]` を付けます。空白と言語を含めて一字ずつ一致させ、項目の evidence_ids または推論の前提からたどれる証拠を参照します。原文がない事実項目は省略し、不足を questions/limitations に書きます。`1.0` への新しい判断も原文引用を付けますが、古い基礎資料は変更せず、位置を捏造しません。

ウェブサーバーは `verification: "exact_match"`、`semantic_support: "unverified"`、`locator: {start, end, prefix, suffix, excerpt_sha256, match_count, coordinate_system: "unicode_codepoints"}` を生成します。`[start,end)` は**保存した抜粋**の Unicode コードポイント位置で、原ページや PDF ページではありません。前後は各 80 文字まで、複数一致は最初の位置と全一致件数を記録します。`excerpt_sha256` は UTF-8 抜粋の小文字 SHA-256 で、証拠にも `excerpt_metadata: {sha256, coordinate_system: "unicode_codepoints"}` を付けられます。実際の文と一致させ、モデルがサーバーの検証項目を生成してはいけません。確定的な検査ツールのないホスト Skill は `1.0` に通常の `{evidence_id, quote}` を保持し、検証済みと主張しません。読込・描画の整合性は出典の真正性や意味的裏付けではありません。

グラフは入力の `source_quote` または `calculation.source_quotes` を検査して `citations` に保持します。数値は対応する引用中に必要で、各計数項目は一致する引用を持ちます。欠損は null のままです。空一覧の 0 には引用項目がなく、既存の網羅性の制約が必要です。

証拠の任意項目：`document_format` は `unknown|html|text|pdf|csv|tsv`、`content_sha256` は null または取得した**応答バイト**の小文字 SHA-256 で、抜粋ハッシュとは異なります。`source_family_method` は `domain|exact_content|exact_excerpt|near_duplicate`、`source_family_evidence_ids` は関連する既存証拠 ID です。推移的な場合もある暫定依存の目安で、所有、独立報道、真偽、発行者署名を証明しません。抽出文字やスニペットから応答の指紋を捏造しません。

`search_log` は `round: "initial"|"supplemental"` と `gap_claim_ids: ["C1"]` を追加し、合計最大 10 件です。`retrieval_gaps` は最大 12 件の `{claim_id, reason: "no_keyword_match"|"limited_families", query, attempted}` で、**初回**の目安を保存します。開始した検索も失敗し得るため、失敗は別途明記し、成功したゼロ件と記録しません。不足の不在や `attempted=true` は完全性や主張成立を認証しません。ウェブリクエストの `adaptive_search` は初期値 false、有効時は簡潔・標準・詳細で追加最大 1/2/2 件、料金増加の可能性があり、出典数と時間の上限は不変です。独立 Skill の実行上限はホストのツールと利用者予算に従います。

## v1.2 任意の引用確認スナップショット

`citation_review` は AI 要約のみ保持し、資料モードの応答・書出しは全体を削除します。`1.2` は `1.1` の精確引用の要件をすべて保持し、資料モードへの投影など確認なしも有効です。旧 `1.0` / `1.1` も読めます。サーバーが確認を付けて更新するまで、`1.1` に確認メタデータは保存しません。

`citation_review` は `generated_at`（1–100 文字）、`language`（`zh-CN|en|ja`）、`model`（1–200）、`method: "ai_advisory"`、`available_targets`（0–323）、`selected_targets`（0–40）、`reviewed_targets`（0–40）、`not_reviewed_targets`（0–323）、`capacity`（簡潔/標準/詳細で 12/24/40）、`input_character_limit: 120000`、`input_characters`（0–120000）、`items`（0–40）を持ちます。整数件数であり、確信度・真偽の点数ではありません。確認件数は一意な項目数、未確認は総数から確認件数を引き、送信数・入力量はサーバーの件数・入力制約付き選択の再計算に一致させます。

各項目は `target_id`、小文字 64 桁十六進の `target_sha256`、`relation`（`aligned|partial|unsupported|conflicting|unclear`）、重複のない最大七つの `issues`（`scope|time|definition|causality|numeric|translation|context`）、`explanation`（1–3000）、1–100 個の既存の完全な `Citation` です。引用は対象の元引用の部分集合で、原文と正確な位置を保持し、証拠の追加や `semantic_support` の変更は不可です。説明はエスケープしたプレーンテキストにします。

対象 ID は `summary`、`claim:C1`、`reasoning:R1`、`observation:1`、`timeline:1`、`comparison:1`、`chart:1:point:1`（数字は 1 始まり）。完全な精確引用を持つ対象のみ選びます。要約を先に、観察、評価済み主張、時系列、グラフ点、歴史比較、論証の六種類を巡回します。一つずつ試して件数上限で終了し、入力上限を超える候補は飛ばして後を試します。user-message JSON は Unicode と既定の区切りを保持し、コードポイントで 120,000 までを測り、固定システム指示・schema は別の加算とし、引用・記述・抜粋は切り詰めません。[証拠の限界](../../../docs/EVIDENCE.md)に範囲・料金を記載しています。

サーバーは `target_id`、`statement: {report_topic, report_scope, content}`、対象の全保存 `citations`、初出証拠順に重複除去した `context: [{evidence_id, title, context, excerpt}]` を結びます。`content` は表示対象から citations を除き、グラフでは title/unit/kind/note と point を含み、モデルの既定項目も補います。非ブール数を固定十進文字列にし、小数末尾のゼロと点を削除、負のゼロを `"0"` に統一して、Unicode 保持・キー整列・コンパクト区切りの JSON を UTF-8 SHA-256 にします。サーバーが生成し、モデルは捏造しません。快照の整合性だけを調べ、AI の生成者・正しさ・出典を認証せず、分析更新で古い確認を削除します。

確定的なサーバー機能のない独立ホストは、希望時に `1.0` の任意判断項目で意味的な助言を提供できますが、`1.2` の快照やサーバー検証済みの主張を捏造しません。オフライン描画は既存確認の検査・表示のみで、AI・検索は呼びません。

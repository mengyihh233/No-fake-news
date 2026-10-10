# Evidence quality in v0.2 / v0.2 证据质量 / v0.2 の証拠品質

## English

**An inspectable record, not a truth certificate.** New research produces schema `1.1`; existing `1.0` reports and examples remain readable. Adding a judgment reuses existing material without searching again or authenticating imported sources.

### Exact quotations

Observations, timeline entries, historical comparisons, and optional judgments carry original quotations. The server rejects quotations absent from the referenced displayed extract. It derives a Unicode codepoint range `[start, end)`, up to 80 characters of preceding/following context, an extract SHA-256, and the number of exact occurrences. Repeated quotations point to their first occurrence. The interface exposes the quoted passage and source link; standalone HTML preserves this information.

For generation, the server partitions the displayed extract into original passages with temporary IDs. The model selects a passage ID; the server restores the source text and runs the same exact-quote checks. Omission/privacy markers are excluded. This avoids depending on a model to recopy whitespace correctly. Choosing a real passage still does not establish relevance or semantic support.

These positions locate the **stored extract**, not a live webpage or PDF page. The check establishes textual presence only: `verification=exact_match`, `semantic_support=unverified`. A real quote can be irrelevant, cherry-picked, misleading, or factually wrong. Read its context and review whether it supports the stated analysis. Imported hashes and quotes do not establish authenticity. Original language and whitespace are preserved.

If analysis fails format/reference checks, the app permits **one additional model attempt** using the same evidence, only with at least 45 seconds remaining. This can increase fees; a successful repair is disclosed in limitations. Failed repair returns an error, never a substitute report. No search or weaker validation is introduced by this repair.

### Optional supplemental searches

Disabled by default. Initial research still searches neutral records, supporting material, counter-evidence, and actor history. A deterministic heuristic flags claims with no matching extract keywords or fewer than two matching source families. When enabled, it issues at most **one extra query for brief, two for standard, or two for deep**. Queries ask for original records and definitions; they do not presume a verdict.

The source, claim, excerpt, and overall time limits stay unchanged. A few fetch slots are reserved for supplemental results; unused slots can use cached initial results. Preferred URLs have priority, and preferred-only domain restrictions apply to both rounds. Supplemental searches are skipped with fewer than 45 seconds remaining or no source capacity. Extra provider calls can increase fees, including DeepSeek model/search calls.

`retrieval_gaps` records the **initial** heuristic snapshot. `attempted` means a query was dispatched, not that it succeeded or resolved a gap. Successful queries identify their round and claim IDs in `search_log`. Failed supplemental calls are disclosed separately, while initial material is retained. Keyword and family counts neither establish semantic coverage nor measure truth, and can produce false positives or omissions.

### Documents and tables

Safe public-source retrieval accepts HTML, plain text, text-based PDF, CSV, and TSV, up to **1,500,000 response bytes**. Extraction keeps at most 16,000 characters; the displayed extract remains subject to the selected depth's smaller limit.

PDF uses `pypdf` in a disposable subprocess with a **six-second deadline, 512 MiB memory limit, first-12-page limit**, and an 8 MB decoded content-stream check. A failed resource guard stops parsing. It receives document bytes, not API keys or website headers, and does not save the PDF. No OCR, password unlocking, attachments, or PDF script execution is provided. Missing text, unsupported fonts, reading-order errors, truncated pages, and parsing failures are disclosed. PDF tables are text extraction, not verified cell reconstruction.

HTML/CSV/TSV tables preserve row/column order, empty cells, and nearby headers as bounded tab-separated text. Tables are limited to 500 rows and 100 columns. Extraction does not select favorable rows by keywords. Oversized first rows may be cut with an explicit warning; merged cells and truncation also carry caveats. Check units, footnotes, and the original document before comparing values.

### Provisional source families

The server groups matching hostnames, identical response-byte hashes, normalized identical extracts of at least 180 characters, and highly similar long extracts. Near-duplicate comparison uses five-token shingles, at least 500 characters and 60 distinct shingles per extract, with Jaccard similarity ≥ 0.90. Short boilerplate alone does not merge domains. Grouping can be transitive, and exposes its method and related evidence IDs.

This estimates possible dependence, not authorship, ownership, independence, plagiarism, or truth. It may miss paraphrases or group distinct reports using common material. `content_sha256` fingerprints the retrieved response bytes; `excerpt_metadata.sha256` fingerprints the displayed text. Neither is a publisher signature. Tracking parameters are ignored only for candidate deduplication; recorded source URLs remain unchanged.

## 简体中文

**可检查的资料记录，不是真实性证书。**新研究使用 `1.1` 格式，已有 `1.0` 报告与示例继续可读。追加判断沿用已有材料，不重新联网，也不认证导入来源。

### 精确引文

资料观察、时间轴、历史比较及可选判断附原文引句。服务器拒绝不在所引展示摘录中的句子，并生成 Unicode 码点区间 `[start, end)`、前后各最多 80 字符、摘录 SHA-256 和精确匹配次数。重复引句定位首处。界面展示引句、上下文和来源链接，独立 HTML 保留这些信息。

生成时，服务器把展示摘录分成带临时编号的原文片段，模型选择编号，服务器附回原文并执行同样的精确校验，排除省略与隐私遮盖标记。这避免依赖模型准确重打空白；选到真实片段仍不证明相关性或语义支持。

位置针对**保存的摘录**，不是原网页或 PDF 页码。校验仅确认文字存在：`verification=exact_match`、`semantic_support=unverified`。真实引句也可能无关、被断章取义或本身有误，仍需检查上下文及其是否支持分析。导入哈希和引句不证明真实性，原文语言与空白保持不变。

分析未通过格式/引用校验时，应用只在剩余至少 45 秒的情况下，允许对同一材料**额外调用一次模型修复**，可能增加费用；修复成功在限制中披露，仍失败则返回错误，不生成替代报告。修复不新增检索，也不降低校验标准。

### 可选补充检索

默认关闭。初轮仍覆盖中性记录、支持材料、反证与主体历史。确定性启发式标记摘录未匹配关键词、或匹配来源谱系不足两个的命题。开启后，简要最多**增加 1 条**查询，标准与深入最多**增加 2 条**；查询寻找原始记录与定义，不预设结论。

来源、命题、摘录和总时限不增加。系统预留少量抓取位置给补充结果，未使用的位置可纳入初轮缓存结果。指定网址优先，仅指定来源的域名限制同时约束两轮。剩余不足 45 秒或没有剩余来源名额时跳过补充。额外服务调用可能增加费用，包括 DeepSeek 的模型/搜索调用。

`retrieval_gaps` 保存**初轮**启发式快照；`attempted` 仅表示查询已派发，不表示成功或缺口补齐。成功查询在 `search_log` 记录轮次及命题 ID；补充失败另行披露并保留初轮材料。关键词与谱系数量不能验证语义覆盖或衡量真假，可能误报、漏报。

### 文档与表格

安全公开抓取支持 HTML、纯文本、文本型 PDF、CSV 和 TSV，响应最大 **1,500,000 字节**。抽取最多 16,000 字符；展示摘录仍受所选深度的较小字符上限约束。

PDF 通过独立临时进程中的 `pypdf` 解析，限制为 **6 秒、512 MiB、前 12 页**，并检查解码内容流是否超过 8 MB。无法施加资源限制时停止解析。解析器只接收文档字节，不继承 API 密钥或网站请求头，不落盘保存 PDF。不提供 OCR、密码解锁、附件提取或 PDF 脚本执行。无文字、字体/阅读顺序问题、截断与解析失败均需注明。PDF 表格属于文字提取，不是已验证的单元格重建。

HTML/CSV/TSV 表格按原顺序保留行列、空单元格和附近表头，转换为有限的制表符文本，最多 500 行、100 列。不按关键词挑选有利行；首行过长可能截断并明确警告，合并单元格与截断也注明限制。比较数值前核查单位、脚注和原文件。

### 暂定来源谱系

服务器按相同主机名、相同响应字节哈希、至少 180 字符的规范化相同摘录、或长摘录的高度相似性归组。近似重复使用五词元组合：每段至少 500 字符、60 个不同组合，Jaccard 相似度 ≥ 0.90。短小通用文字不会单独导致跨域合并。归组可能经其他条目传递，并显示方法及关联证据 ID。

这仅估计可能的依赖关系，不证明作者、所有权、独立性、抄袭或真假，可能漏掉改写转载，也可能把共用材料的不同报道归组。`content_sha256` 标识取得的响应字节，`excerpt_metadata.sha256` 标识展示文本，均不是出版者签名。追踪参数仅在候选去重时忽略，实际来源网址保持原样。

## 日本語

**検査できる資料記録であり、真実性の証明書ではありません。**新規調査は `1.1` 形式を使用し、既存の `1.0` レポートと例も読めます。判断の追加は既存資料を使い、再検索や読み込んだ出典の認証をしません。

### 精確な引用

観察、時系列、歴史比較、任意の判断に原文を付けます。サーバーは参照する表示抜粋に存在しない引用を拒否し、Unicode コードポイント区間 `[start, end)`、前後最大 80 文字、抜粋の SHA-256、完全一致件数を生成します。複数一致は最初の位置を示します。UI と独立 HTML で引用、文脈、出典リンクを確認できます。

生成時は表示抜粋を仮 ID 付きの原文断片に分け、モデルが ID を選び、サーバーが原文を戻して同じ精確検査を行います。省略・秘密の置換記号は除外します。モデルの空白再入力に依存しませんが、実在する断片の選択も関連性や意味的裏付けを証明しません。

位置は**保存された抜粋**に対するもので、元ウェブページや PDF のページ番号ではありません。検査は文字の存在のみ確認します：`verification=exact_match`、`semantic_support=unverified`。実在する引用も無関係、切り取り、事実誤認の場合があります。文脈と分析への裏付けを確認してください。読み込んだハッシュと引用は真正性を証明せず、原文の言語と空白を保持します。

形式・引用検査に失敗した場合、残り 45 秒以上に限り、同じ資料で**モデルを追加で一回**呼び出して修正できます。料金が増える場合があり、成功時は制約に明記します。再度失敗すると代替レポートではなくエラーを返し、検索を追加したり検査を弱めたりしません。

### 任意の補足検索

初期設定は無効です。初回は中立の記録、支持資料、反証、当事者の履歴を検索します。抜粋のキーワード一致がない、または一致する情報系統が二つ未満の主張を確定的な目安で示します。有効時は簡潔で**最大 1 件**、標準・詳細で**最大 2 件**を追加し、結論を前提とせず原記録と定義を探します。

情報源、主張、抜粋、総制限時間は増えません。補足結果用に少数の取得枠を予約し、未使用の枠は初回のキャッシュ結果で補えます。指定 URL は優先し、指定ドメインのみの制約は両ラウンドに適用します。残り 45 秒未満または取得枠がない場合は省略します。DeepSeek のモデル・検索呼出しなど、追加料金が発生する場合があります。

`retrieval_gaps` は**初回**の目安を保存します。`attempted` は検索開始のみで、成功や不足解消を示しません。成功した検索は `search_log` にラウンドと主張 ID を記録し、補足の失敗は別途明記して初回資料を保持します。キーワードと系統数は意味的な網羅性や真偽を検証せず、誤検出・見落としがあります。

### 文書と表

公開取得は HTML、テキスト、テキスト PDF、CSV、TSV に対応し、応答の上限は **1,500,000 バイト**です。抽出は最大 16,000 文字、表示する抜粋は選択した深さの小さい上限に従います。

PDF は使い捨てプロセス内の `pypdf` で解析し、**6 秒、512 MiB、先頭 12 ページ**を上限とし、復号した内容ストリームに 8 MB の検査を設けます。資源制限を適用できなければ停止します。文書バイトのみ受け取り、API キーやサイトのヘッダーを継承せず、PDF を保存しません。OCR、パスワード解除、添付抽出、PDF スクリプト実行は提供しません。文字の欠落、フォント・読み順の問題、切り詰め、失敗は明記します。PDF の表は文字抽出であり、検証済みセル復元ではありません。

HTML/CSV/TSV の表は元の行列順、空欄、付近の見出しを有限のタブ区切りテキストで保持し、最大 500 行・100 列です。検索語で有利な行を選びません。先頭行が長すぎる場合の切り詰め、結合セル、その他の切り詰めは注意を表示します。比較前に単位、脚注、原文書を確認してください。

### 暫定的な情報系統

同じホスト名、同じ応答バイトのハッシュ、180 文字以上の正規化同一抜粋、長い抜粋の高い類似度で分類します。近似重複は五トークンの組合せを使用し、各抜粋は 500 文字以上、異なる組合せ 60 件以上、Jaccard 類似度 ≥ 0.90 を必要とします。短い定型文だけで別ドメインを結合せず、推移的な分類の方法と関連証拠 ID を示します。

依存の可能性の目安であり、著者、所有、独立性、盗用、真偽を証明しません。言い換え転載を見落とし、共通資料を使う別記事をまとめる場合があります。`content_sha256` は取得応答のバイト、`excerpt_metadata.sha256` は表示テキストの指紋で、発行者の署名ではありません。追跡パラメーターは候補の重複除去のみで無視し、出典 URL は変更しません。

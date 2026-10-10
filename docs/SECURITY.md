# Security / 安全 / セキュリティ

## English

This is a local, single-user tool. The HTTP service is restricted to loopback and checks Host/Origin. It has no public-deployment authentication. Do not expose its port through a proxy or tunnel without designing appropriate access controls.

`python app.py` optionally reads the project `.env`. This is a local plaintext secret file, ignored by Git, and must be protected and excluded from shared folders/backups. Environment values win; the loader accepts only named project settings and does not execute or expand them. Native DeepSeek search uses a fixed official HTTPS endpoint. The local AI key is inherited only by an endpoint sharing its configured origin (scheme, host, port). Only an explicitly selected search key, `DEEPSEEK_API_KEY`, or an AI key whose destination is the official HTTPS origin can authenticate it.

Public-source retrieval rejects private/metadata addresses, validates redirects, and pins DNS resolutions. Website credentials are attached only to the authorized HTTPS origin and removed on cross-origin redirects. They stay in the active session and must never appear in report JSON, exports, browser storage, provider prompts, or search queries. Account-protected text may still be sent to the AI provider selected by the user. Review that content before use.

Never place real keys in `.env.example`, tests, screenshots, issues, or commits. `.env` and `runtime/` are ignored. A report itself may contain private retrieved material: inspect it before sharing. Imported reports are untrusted; import validates structure and references but does not independently reverify their truth.

Credential fields are not included as AI/search configuration. Source URLs and every retrieval/screenshot redirect are checked against known website password/token strings from the entire request, independently of origin-bound authentication headers. The source-text filter masks known password/token strings, not all personal data or arbitrary encodings. Retrieved usernames and email addresses may remain in text sent to the configured AI and in reports; this is not general anonymization.

PDF parsing runs in a disposable subprocess with a six-second deadline and an enforced 512 MiB memory limit (Windows Job Object / Unix resource limits), with bounded pages, input bytes, text, and content streams. It receives bytes over stdin with only minimal system environment, not application keys or source headers, and does not save the document or execute PDF scripts. A failed resource guard stops parsing. This is resource isolation, not a full OS sandbox or a third-party security audit; use trusted dependencies and inspect extraction warnings. Exact quotes and SHA-256 establish extract consistency, not publisher identity, authenticity, semantic support, or complete coverage. See [evidence boundaries](EVIDENCE.md).

Report vulnerabilities through GitHub's **private vulnerability reporting** for this repository if available. If unavailable, open a public issue requesting a private contact **without exploit details, credentials, or personal data**. No response SLA or third-party security audit is claimed.

## 简体中文

本工具面向本机单用户。HTTP 服务限制回环访问并检查 Host/Origin，没有公开部署认证。不要在未设计访问控制的情况下用代理或隧道暴露端口。

`python app.py` 可读取项目 `.env`。这是已被 Git 忽略的本机明文秘密文件，请保护权限，不要放入共享文件或公开备份。进程变量优先，加载器只接受规定字段，不执行或展开内容。DeepSeek 原生搜索固定使用官方 HTTPS 接口，本机 AI 密钥只向与配置相同的 origin（协议、主机、端口）继承。搜索仅接受明确选择的搜索密钥、`DEEPSEEK_API_KEY` 或目标为官方 HTTPS 来源的 AI 密钥。

公开资料抓取拒绝私网/元数据地址、检查重定向并固定 DNS 结果。网站凭据只附给授权 HTTPS 来源，跨来源重定向时移除；只在当前会话存在，不得进入 JSON、导出、浏览器存储、模型提示或搜索查询。账户正文可能发送给用户所选 AI，请先评估内容。

真实密钥不要放入模板、测试、截图、issue 或提交。`.env`、`runtime/` 已忽略。报告可能包含私有正文，分享前检查。导入会验证结构和引用，但不会独立重新证明真实性。

凭据字段不会作为 AI/搜索配置发送。来源 URL 及抓取／截图的每次跳转均对照本次请求中已知的网站密码和令牌检查，认证请求头仍单独绑定精确来源。正文过滤遮盖已知密码和令牌字符串，并非所有个人信息或任意编码。取得的用户名、邮箱可能留在发送给所配 AI 的正文与报告中，不提供通用匿名化保证。

PDF 在独立临时进程中解析，限制 6 秒及 512 MiB（Windows Job Object / Unix 资源限制），并约束页数、输入字节、文字及内容流。仅通过 stdin 接收字节，继承最小系统环境，不继承应用密钥或来源请求头，不保存文档或执行 PDF 脚本。无法施加限制时停止。这属于资源隔离，不是完整 OS 沙箱或第三方审计；请使用可信依赖并检查抽取警告。精确引文与 SHA-256 证明摘录一致性，不证明出版者、真实性、语义支持或完整覆盖。参见[证据边界](EVIDENCE.md)。

如仓库已启用 GitHub **私密漏洞报告**，请使用该入口。不可用时，可发布仅请求私密联系方式的 issue，**不要附漏洞利用细节、凭据或个人信息**。项目不承诺响应时限，也未宣称经过第三方安全审计。

## 日本語

本ツールはローカルの単一利用者向けです。HTTP はループバックと Host/Origin 検査に限定し、公開配置用認証はありません。適切なアクセス制御を設計せず、プロキシやトンネルで公開しないでください。

`python app.py` は任意のプロジェクト `.env` を読み込みます。Git から除外したローカル平文の秘密ファイルとして保護し、共有フォルダーや公開バックアップに含めないでください。既存環境を優先し、規定項目のみ読み込み、実行・変数展開はしません。DeepSeek 検索は固定した公式 HTTPS 接続先に、ローカル AI キーは設定と同一 origin（プロトコル・ホスト・ポート）にのみ引き継がれます。検索には明示した検索キー、`DEEPSEEK_API_KEY`、または公式 HTTPS 宛ての AI キーのみを使用します。

公開資料取得は内部・メタデータアドレスを拒否し、リダイレクトを検査して DNS 結果を固定します。サイト認証情報は許可した HTTPS オリジンだけに付与し、別オリジンへの転送では除去します。セッション中だけ保持し、JSON、書出し、ストレージ、モデル、検索に含めません。認証済み本文は選択した AI に送られる場合があるため、内容を確認してください。

本物のキーをテンプレート、テスト、画像、issue、コミットに含めないでください。`.env` と `runtime/` は除外しています。レポートの非公開本文は共有前に確認してください。読込時の構造・引用検査は真偽の再検証ではありません。

認証欄の値は AI・検索設定に含めません。情報源 URL と取得・画像保存の各リダイレクトは、リクエスト全体の既知のサイトパスワード・トークンと照合します。認証ヘッダーは別に同一オリジンだけへ付与します。本文の処理は既知のパスワード・トークン文字列を隠しますが、全個人情報や任意の符号化に対応しません。取得したユーザー名・メール等は AI に送る本文とレポートに残る場合があり、一般的な匿名化は保証しません。

PDF は使い捨てプロセス内で解析し、6 秒・512 MiB（Windows Job Object / Unix 資源制限）、ページ数、入力バイト、文字、内容ストリームを制限します。最小限のシステム環境と stdin の文書バイトのみ使い、アプリのキーや出典ヘッダーを継承せず、文書保存や PDF スクリプト実行をしません。制限を適用できなければ停止します。資源分離であり、完全な OS サンドボックスや第三者監査ではありません。信頼できる依存関係を使い、抽出警告を確認してください。引用と SHA-256 は抜粋の整合性を示し、発行者、真正性、意味的裏付け、網羅性を証明しません。[証拠の制約](EVIDENCE.md)を参照してください。

GitHub の**非公開脆弱性報告**が利用できる場合は使用してください。なければ非公開の連絡先だけを求める issue を作り、**攻撃手順、認証情報、個人情報は載せないでください**。応答期限や第三者監査は保証していません。

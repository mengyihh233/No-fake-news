# Security / 安全 / セキュリティ

## English

This is a local, single-user tool. The HTTP service is restricted to loopback and checks Host/Origin. It has no public-deployment authentication. Do not expose its port through a proxy or tunnel without designing appropriate access controls.

Public-source retrieval rejects private/metadata addresses, validates redirects, and pins DNS resolutions. Website credentials are attached only to the authorized HTTPS origin and removed on cross-origin redirects. They stay in the active session and must never appear in report JSON, exports, browser storage, provider prompts, or search queries. Account-protected text may still be sent to the AI provider selected by the user. Review that content before use.

Never place real keys in `.env.example`, tests, screenshots, issues, or commits. `.env` and `runtime/` are ignored. A report itself may contain private retrieved material: inspect it before sharing. Imported reports are untrusted; import validates structure and references but does not independently reverify their truth.

Credential fields are not included as AI/search configuration. The source-text filter masks known password/token strings, not all personal data or arbitrary encodings. Retrieved usernames and email addresses may remain in text sent to the configured AI and in reports; this is not general anonymization.

Report vulnerabilities through GitHub's **private vulnerability reporting** for this repository if available. If unavailable, open a public issue requesting a private contact **without exploit details, credentials, or personal data**. No response SLA or third-party security audit is claimed.

## 简体中文

本工具面向本机单用户。HTTP 服务限制回环访问并检查 Host/Origin，没有公开部署认证。不要在未设计访问控制的情况下用代理或隧道暴露端口。

公开资料抓取拒绝私网/元数据地址、检查重定向并固定 DNS 结果。网站凭据只附给授权 HTTPS 来源，跨来源重定向时移除；只在当前会话存在，不得进入 JSON、导出、浏览器存储、模型提示或搜索查询。账户正文可能发送给用户所选 AI，请先评估内容。

真实密钥不要放入模板、测试、截图、issue 或提交。`.env`、`runtime/` 已忽略。报告可能包含私有正文，分享前检查。导入会验证结构和引用，但不会独立重新证明真实性。

凭据字段不会作为 AI/搜索配置发送。正文过滤遮盖已知密码和令牌字符串，并非所有个人信息或任意编码。取得的用户名、邮箱可能留在发送给所配 AI 的正文与报告中，不提供通用匿名化保证。

如仓库已启用 GitHub **私密漏洞报告**，请使用该入口。不可用时，可发布仅请求私密联系方式的 issue，**不要附漏洞利用细节、凭据或个人信息**。项目不承诺响应时限，也未宣称经过第三方安全审计。

## 日本語

本ツールはローカルの単一利用者向けです。HTTP はループバックと Host/Origin 検査に限定し、公開配置用認証はありません。適切なアクセス制御を設計せず、プロキシやトンネルで公開しないでください。

公開資料取得は内部・メタデータアドレスを拒否し、リダイレクトを検査して DNS 結果を固定します。サイト認証情報は許可した HTTPS オリジンだけに付与し、別オリジンへの転送では除去します。セッション中だけ保持し、JSON、書出し、ストレージ、モデル、検索に含めません。認証済み本文は選択した AI に送られる場合があるため、内容を確認してください。

本物のキーをテンプレート、テスト、画像、issue、コミットに含めないでください。`.env` と `runtime/` は除外しています。レポートの非公開本文は共有前に確認してください。読込時の構造・引用検査は真偽の再検証ではありません。

認証欄の値は AI・検索設定に含めません。本文の処理は既知のパスワード・トークン文字列を隠しますが、全個人情報や任意の符号化に対応しません。取得したユーザー名・メール等は AI に送る本文とレポートに残る場合があり、一般的な匿名化は保証しません。

GitHub の**非公開脆弱性報告**が利用できる場合は使用してください。なければ非公開の連絡先だけを求める issue を作り、**攻撃手順、認証情報、個人情報は載せないでください**。応答期限や第三者監査は保証していません。

# Roadmap / 发展方向 / 今後の方向

[English](#english) · [简体中文](#简体中文) · [日本語](#日本語)

## English

These are proposed next steps, not released capabilities. Priorities favor evidence quality and reproducibility before broader automation.

| Priority | Direction | A useful completion criterion |
| --- | --- | --- |
| 1 | Evidence evaluation set | Publish annotated cases for misleading quotations, omitted qualifiers, repeated sources, and unavailable documents; measure false acceptance and abstention separately. |
| 1 | More precise source locations | Preserve PDF page numbers and table row/column references alongside the current saved-extract positions; a reader can reproduce each location. |
| 1 | Reader corrections | Allow a reader to propose a correction with a source, retain the original report, and record a visible revision history. |
| 2 | Optional second-provider review | Let users choose a different model and compare disagreements with explicit cost and privacy disclosures. Agreement must never become a truth score. |
| 2 | Reproducible numeric comparisons | Add explicit formulas, units, denominators, time ranges, and uncertainty. Independently recompute every supported calculation before display. |
| 2 | Source adapters | Add selected public datasets and user-authorized website sessions one at a time, with origin-bound credentials and tested access failures. |
| 3 | Research history and updates | Save reports locally by explicit choice, compare later evidence, and distinguish changed source content from changed AI interpretations. |
| 3 | Shared deployments | Design authentication, isolated user secrets, quotas, retention, and deletion before exposing the application outside localhost. |

OCR and multimedia analysis should follow labeled extraction evaluations and visible error reporting. Website snapshots must respect access rules, licensing, and personal information. No roadmap item can justify promising complete neutrality or bypassing another service's policies.

## 简体中文

以下是待开发方向，并非已发布功能。优先改善证据质量与可复现性，再扩展自动化范围。

| 优先级 | 方向 | 可验收的结果 |
| --- | --- | --- |
| 1 | 证据评测集 | 公开带标注的误引、遗漏限定条件、重复来源及无法访问案例，分别衡量误接受与主动保留判断。 |
| 1 | 更精确的原文定位 | 在现有保存摘录位置之外，保留 PDF 页码、表格行列；读者能复现每一处定位。 |
| 1 | 读者纠错 | 允许读者附来源提出修正，保留原报告并展示修订记录。 |
| 2 | 可选第二供应商复核 | 由用户选择不同模型并比较分歧，事先披露费用和隐私流向；模型共识不能转成真实性分数。 |
| 2 | 可复算的数值比对 | 明示公式、单位、分母、时间范围及不确定性；展示前独立重算每种受支持运算。 |
| 2 | 资料来源适配 | 逐个接入公开数据集及用户授权的网站会话，认证严格绑定来源并测试访问失败。 |
| 3 | 研究档案与更新 | 经用户明确选择后在本地保存报告，比对后续证据，区分来源内容变化与 AI 解释变化。 |
| 3 | 多用户部署 | 对外开放前先完成认证、用户密钥隔离、配额、保存期限与删除机制。 |

OCR 和音视频分析应先有带标注的提取评测，并显示识别错误。网页留存需考虑访问规则、许可及个人信息。任何发展方向都不能承诺完全无偏，或以绕过其他服务规则为目标。

## 日本語

以下は開発候補であり、公開済みの機能ではありません。自動化の範囲を広げる前に、証拠の品質と再現性を優先します。

| 優先度 | 方向 | 完了を確認できる基準 |
| --- | --- | --- |
| 1 | 証拠評価セット | 誤引用、条件の省略、情報源の重複、取得できない文書の注釈付き事例を公開し、誤受理と判断保留を別々に測定。 |
| 1 | より精確な原文位置 | 保存抜粋内の位置に加えて PDF ページ番号と表の行・列を保持し、読者が再現可能にする。 |
| 1 | 読者による訂正 | 出典付き訂正案を受け付け、元のレポートを残し、改訂履歴を表示。 |
| 2 | 任意の別事業者レビュー | 別モデルを選択して相違を比較できるようにし、費用と送信先を事前に開示。合意を真実性スコアに変換しない。 |
| 2 | 再計算できる数値比較 | 式、単位、分母、期間、不確実性を明示し、対応する計算を表示前に独立して再計算。 |
| 2 | 情報源アダプター | 公開データと利用者が許可したサイトのセッションを個別に追加し、認証の同一オリジン制限と取得失敗を検査。 |
| 3 | 調査履歴と更新 | 利用者の明示選択でローカルに保存し、後の証拠を比較。情報源の変更と AI 解釈の変更を区別。 |
| 3 | 共有環境への配置 | localhost 外で公開する前に、認証、利用者ごとの秘密情報分離、上限、保存期間、削除を設計。 |

OCR と音声・動画分析は、注釈付き抽出評価と可視のエラー表示を先に整備します。ページ保存ではアクセス規則、ライセンス、個人情報を考慮します。完全な中立性や、他サービスの規則の回避を約束する方向にはしません。

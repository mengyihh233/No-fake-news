#!/usr/bin/env python3
"""Render a checked evidence package to portable HTML; never calls AI or search."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

# Renderer labels only. Report prose, excerpts and exact source quotes are never translated here.
_MESSAGES = {
    "map_title": ("证据关系图", "Evidence map", "証拠の関連図"),
    "map_note": ("线条仅表示报告中记录的引用关联，不代表因果、证明或可信度。点击编号可定位全文；文字对应内容见下方命题、来源和比对分析。", "Lines show recorded citation relationships, not causation, proof, or confidence. Select an ID to read its record; complete text equivalents appear in the claims, sources, and comparisons below.", "線は記録された引用関係であり、因果・証明・信頼度ではありません。ID から全文へ移動できます。対応する説明は下の主張・出典・比較分析にあります。"),
    "title": ("证据报告", "Evidence report", "証拠レポート"),
    "evidence-only": ("列出信息自行判断", "Evidence for your own judgment", "資料を見て自分で判断"),
    "ai-summary": ("AI 生成总结", "AI summary", "AI による要約"),
    "brief": ("简要", "Brief", "簡潔"),
    "standard": ("标准", "Standard", "標準"),
    "deep": ("深入", "Deep", "詳細"),
    "depth": ("分析深度", "Analysis depth", "分析の深さ"),
    "generated": ("报告生成", "Generated", "作成日時"),
    "limits": ("范围与限制", "Scope and limitations", "対象範囲と制約"),
    "claims": ("命题与证据链", "Claims and evidence links", "主張と証拠のつながり"),
    "sources": ("来源档案", "Source records", "情報源の記録"),
    "type": ("类型", "Type", "種類"),
    "published": ("发布", "Published", "公開日"),
    "retrieved": ("访问", "Retrieved", "取得日"),
    "family": ("来源谱系", "Source lineage", "情報源の系統"),
    "claim_refs": ("对应命题", "Related claims", "関連する主張"),
    "observations": ("资料比对分析", "Evidence comparison and analysis", "資料の比較・分析"),
    "observations_note": ("本栏在两种模式中都保留；分析说明口径、条件与差异，真假裁决由所选模式决定。", "Retained in both modes: this section explains definitions, conditions and differences. Verdicts depend on the selected mode.", "両モードで表示します。定義・条件・相違点を説明し、真偽の判定は選択したモードに従います。"),
    "data": ("数据口径与比较", "Data definitions and comparisons", "データの定義と比較"),
    "logic": ("逻辑前提与条件", "Logical premises and conditions", "論理上の前提と条件"),
    "history": ("历史可比性与局限", "Historical comparability and limits", "歴史的な比較可能性と限界"),
    "claim": ("命题", "Claims", "主張"),
    "source": ("来源", "Sources", "情報源"),
    "charts": ("数据与口径", "Data and definitions", "データと集計基準"),
    "unit": ("单位", "Unit", "単位"),
    "item": ("项目", "Item", "項目"),
    "value": ("数值", "Value", "数値"),
    "count_rules": ("计数口径", "Counting rules", "件数の集計基準"),
    "count_entries": ("所列条目数：{count}。零条目不证明全集完整。", "Listed entries: {count}. Zero entries do not establish completeness.", "記載された項目数：{count}。0 件であっても一覧の完全性は証明されません。"),
    "timeline": ("时间轴", "Timeline", "時系列"),
    "comparisons": ("历史可比性", "Historical comparability", "歴史的な比較可能性"),
    "similarities": ("相似条件", "Shared conditions", "共通する条件"),
    "differences": ("关键差异", "Key differences", "主な相違点"),
    "inference_limits": ("推论边界", "Limits of inference", "推論の限界"),
    "summary": ("AI 总结与公开论证", "AI summary and inspectable reasoning", "AI 要約と検証可能な論証"),
    "premises": ("前提", "Premises", "前提"),
    "questions": ("待解问题", "Open questions", "未解決の問い"),
    "search_log": ("搜索记录与覆盖范围", "Search log and coverage", "検索記録と調査範囲"),
    "results": ("条结果", "results", "件の結果"),
    "footer": ("来源选择仍可能有偏差，请核对原件及报告范围。", "Source selection can still introduce bias. Check original materials and the report's scope.", "情報源の選択には偏りが残る可能性があります。原資料と調査範囲を確認してください。"),
    "missing": ("缺失", "Missing", "欠損"),
    "not_provided": ("未提供", "Not provided", "未提供"),
    "empty_chart": ("无可绘制数值。", "No numeric values to plot.", "描画できる数値がありません。"),
    "screenshot_missing": ("截图未内嵌；本材料包没有可读取的本地原图。", "Screenshot not embedded: no readable local original is included.", "読み取れるローカル原画像がないため、スクリーンショットは埋め込まれていません。"),
    "screenshot_alt": ("原网页证据截图", "Original source webpage screenshot", "情報源の元ウェブページのスクリーンショット"),
    "captured": ("采集", "Captured", "撮影日時"),
    "screenshot_note": ("截图及哈希辅助复核采集文件，不认证页面说法。", "Screenshots and hashes help inspect captured files; they do not verify the page's claims.", "画像とハッシュは取得ファイルの確認を補助しますが、ページの主張の真実性を証明しません。"),
    "content_preserved": ("界面标签已切换语言；报告正文与原始摘录保留原有语言。", "Interface labels use this language; report prose and source excerpts retain their supplied language.", "画面のラベルのみ言語を切り替えています。レポート本文と引用資料は提供された言語のままです。"),
    "relevant_to": ("关联资料", "Related material", "関連資料"),
    "context": ("背景资料", "Background material", "背景資料"),
    "supports": ("支持（AI 解释）", "Supports (AI interpretation)", "支持（AI の解釈）"),
    "contradicts": ("反驳（AI 解释）", "Contradicts (AI interpretation)", "反証（AI の解釈）"),
    "qualifies": ("限定（AI 解释）", "Qualifies (AI interpretation)", "条件・限定（AI の解釈）"),
    "fact": ("事实", "Fact", "事実"),
    "causal": ("因果", "Causal", "因果"),
    "prediction": ("预测", "Prediction", "予測"),
    "value_kind": ("价值判断", "Value judgment", "価値判断"),
    "mixed": ("混合", "Mixed", "複合"),
    "primary": ("原始来源", "Primary source", "一次資料"),
    "secondary": ("二手来源", "Secondary source", "二次資料"),
    "unknown": ("待核实分类", "Unverified classification", "分類未確認"),
    "full_text": ("已读取正文", "Page text retrieved", "本文取得済み"),
    "search_extract": ("搜索服务摘录", "Search-provider extract", "検索サービスによる抜粋"),
    "snippet": ("搜索摘要", "Search snippet", "検索スニペット"),
    "status_retrieved": ("已取得", "Retrieved", "取得済み"),
    "snippet_only": ("仅摘要/摘录", "Snippet/extract only", "スニペット・抜粋のみ"),
    "unavailable": ("未取得", "Unavailable", "未取得"),
    "summary_required": ("AI 总结模式需要已有 summary；本脚本不会生成总结。", "AI-summary mode requires an existing summary; this script does not generate one.", "AI 要約モードには既存の summary が必要です。このスクリプトは要約を生成しません。"),
    "bad_language": ("language 只支持 zh-CN、en、ja。", "language must be zh-CN, en, or ja.", "language は zh-CN、en、ja のいずれかです。"),
    "bad_mode": ("mode 只支持 evidence-only、ai-summary。", "mode must be evidence-only or ai-summary.", "mode は evidence-only または ai-summary です。"),
    "bad_url": ("来源 URL 必须是无凭据的 http(s) 地址。", "Source URLs must be http(s) addresses without embedded credentials.", "情報源の URL は認証情報を含まない http(s) アドレスである必要があります。"),
    "bad_schema": ("需要 schema_version=1.0 或 1.1 和 topic。", "schema_version=1.0 or 1.1 and topic are required.", "schema_version=1.0 または 1.1 と topic が必要です。"),
    "bad_depth": ("depth 应为 brief、standard 或 deep。", "depth must be brief, standard, or deep.", "depth は brief、standard、deep のいずれかです。"),
    "duplicate_ids": ("命题及来源 ID 必须唯一。", "Claim and source IDs must be unique.", "主張と情報源の ID は一意である必要があります。"),
    "bad_ids": ("命题/来源 ID 应为 C1…/E1…。", "Claim/source IDs must use C1…/E1….", "主張・情報源の ID は C1…・E1… の形式にしてください。"),
    "missing_refs": ("数据、事件及总结需要引用已存在的证据 ID。", "Data, events and summaries must cite existing evidence IDs.", "データ・出来事・要約には既存の証拠 ID を引用してください。"),
    "bad_claim_ref": ("来源引用了不存在的命题。", "A source cites a nonexistent claim.", "情報源が存在しない主張を参照しています。"),
    "bad_link": ("证据链存在无效引用。", "An evidence link has an invalid reference.", "証拠のつながりに無効な参照があります。"),
    "bad_observation": ("资料比对分析须有有效类型及命题、证据引用。", "Observations require a valid kind and claim/evidence references.", "比較分析には有効な種類と主張・証拠の参照が必要です。"),
    "bad_chart": ("图表 kind 只支持 bar/line。", "Chart kind must be bar or line.", "グラフの kind は bar または line です。"),
    "bad_value": ("图表数据必须是有限数值或 null。", "Chart values must be finite numbers or null.", "グラフの値は有限の数値または null である必要があります。"),
    "bad_count": ("派生计数需要唯一、实际存在的摘录及明确口径，且数值等于条目数。", "Derived counts require unique existing excerpts, explicit counting rules, and a value equal to the entry count.", "派生件数には重複のない実在する抜粋と明確な集計基準が必要で、値は項目数と一致する必要があります。"),
    "bad_reasoning": ("论证须引用证据或前置论证，且不允许循环。", "Reasoning must cite evidence or earlier reasoning without cycles.", "論証は証拠または先行する論証を参照し、循環してはいけません。"),
    "image_large": ("单张截图上限为 12 MB。", "Each screenshot must be at most 12 MB.", "スクリーンショットは 1 枚につき最大 12 MB です。"),
    "image_type": ("只接受真实 PNG/JPEG/WebP 截图，不接受 HTML/SVG 伪装图片。", "Only genuine PNG/JPEG/WebP images are accepted, not HTML/SVG disguised as images.", "実際の PNG・JPEG・WebP 画像のみ対応します。画像に偽装した HTML・SVG は受け付けません。"),
    "image_hash": ("截图 SHA-256 与材料记录不一致。", "The screenshot SHA-256 does not match its record.", "画像の SHA-256 が記録と一致しません。"),
    "image_read": ("无法读取截图文件。", "Cannot read the screenshot file.", "画像ファイルを読み取れません。"),
    "cli_description": ("将已核查的材料包渲染为可携带 HTML；不调用 AI 或搜索。", "Render a checked evidence package as portable HTML; no AI or search calls.", "確認済み資料を単独の HTML に変換します。AI・検索への呼び出しは行いません。"),
    "cli_report": ("UTF-8 JSON 材料包", "UTF-8 JSON evidence package", "UTF-8 JSON 資料パッケージ"),
    "cli_output": ("输出 HTML 文件", "Output HTML file", "出力 HTML ファイル"),
    "cli_mode": ("输出模式；默认 evidence-only", "Output mode; default: evidence-only", "出力モード（既定：evidence-only）"),
    "cli_language": ("界面/提示语言；省略时使用报告 language 或 zh-CN；不翻译正文", "Label/message language; defaults to report language or zh-CN; does not translate prose", "表示・メッセージの言語（省略時はレポートの language または zh-CN）。本文は翻訳しません"),
    "cli_capture": ("将网页应用 /captures/ 地址解析到此本地目录", "Resolve web-app /captures/ URLs against this local directory", "ウェブアプリの /captures/ URL に対応するローカルフォルダー"),
    "cli_help": ("显示帮助并退出", "Show this help and exit", "ヘルプを表示して終了"),
    "usage": ("用法", "usage", "使い方"),
    "positionals": ("位置参数", "positional arguments", "位置引数"),
    "options": ("选项", "options", "オプション"),
    "required": ("缺少必要参数", "Required arguments are missing", "必須の引数がありません"),
    "unrecognized": ("无法识别的参数", "Unrecognized arguments", "認識できない引数"),
    "argument_value": ("参数需要一个值", "An argument requires a value", "引数に値が必要です"),
    "invalid_arguments": ("参数无效，请使用 --help 查看用法。", "Invalid arguments; use --help for usage.", "引数が無効です。--help で使い方を確認してください。"),
    "error": ("错误", "error", "エラー"),
    "saved": ("已保存 {path}（{mode}）", "Saved {path} ({mode})", "保存しました：{path}（{mode}）"),
    "render_failed": ("无法生成报告", "Cannot render report", "レポートを生成できません"),
    "json_error": ("无法解析 UTF-8 JSON 材料包。", "Cannot parse the UTF-8 JSON evidence package.", "UTF-8 JSON 資料パッケージを解析できません。"),
    "structure_error": ("材料包结构不完整或字段类型错误。", "The package has missing fields or invalid field types.", "資料パッケージに不足する項目または不正な型があります。"),
    "file_error": ("无法读取输入或写入输出文件。", "Cannot read input or write the output file.", "入力の読み取りまたは出力ファイルの書き込みができません。"),
    "source_scope": ("指定来源与检索范围", "Preferred sources and coverage", "指定情報源と調査範囲"),
    "balanced": ("补充指定来源并综合检索", "Supplement preferred sources with balanced research", "指定情報源に加えて幅広く調査"),
    "preferred-only": ("仅指定来源", "Designated sources only", "指定情報源のみ"),
    "preferred_note": ("网址仅表示用户指定范围；是否实际取得请查看来源档案。", "These URLs describe the user's preferred scope; consult source records for actual retrieval.", "URL はユーザーの指定範囲です。実際の取得状況は情報源の記録を確認してください。"),
    "bad_source_policy": ("来源策略无效或指定来源超过 6 个。", "Invalid source policy or more than six preferred sources.", "情報源の方針が無効、または指定情報源が 6 件を超えています。"),
    "summary_language": ("总结语言", "Summary language", "要約の言語"),
    "exact_citations": ("精确原句引用（{count}）", "Exact quotations ({count})", "精確な原文引用（{count}）"),
    "citation_note": ("原句仅与本材料包中的摘录逐字匹配；这不验证原网页真实性、统计解释或引文对论断的语义支持关系。", "Quotations match extracts in this package verbatim. This does not establish the original webpage's authenticity, statistical interpretation, or semantic support for a claim.", "引用文はこの資料の抜粋とそのまま一致します。元ページの真正性、統計の解釈、主張への意味的な裏付けは検証していません。"),
    "citation_legacy": ("此条旧资料未提供精确引文定位。", "This legacy record has no exact quotation locator.", "この旧形式の記録には精確な引用位置がありません。"),
    "citation_position": ("摘录字符位置 {start}–{end}（Unicode 码点，结束位置不包含）· 匹配 {count} 处，定位首处", "Extract character positions {start}–{end} (Unicode code points, end exclusive) · {count} matches, first occurrence selected", "抜粋の文字位置 {start}–{end}（Unicode コードポイント、終端を含まない）・{count} 件一致、最初の位置を選択"),
    "citation_no_locator": ("原句存在于摘录；未提供定位元数据。", "The quote occurs in the extract; no locator metadata was supplied.", "引用文は抜粋内にありますが、位置メタデータは未提供です。"),
    "bad_citation": ("精确引文缺失、引用无效，或原句、位置、上下文与摘录摘要不一致。", "An exact citation is missing, invalid, or inconsistent with the quotation, position, context, or extract hash.", "精確引用が不足・無効、または原文、位置、文脈、抜粋ハッシュと一致しません。"),
    "bad_metadata": ("资料格式、来源谱系、摘要或检索缺口元数据无效。", "Invalid document format, source lineage, hash, or retrieval-gap metadata.", "資料形式、情報源系統、ハッシュ、検索の不足のメタデータが無効です。"),
    "document_format": ("资料格式", "Document format", "資料形式"),
    "format_unknown": ("未识别", "Unidentified", "未判定"),
    "format_html": ("HTML 网页", "HTML webpage", "HTML ページ"),
    "format_text": ("纯文本", "Plain text", "プレーンテキスト"),
    "format_pdf": ("PDF 文档", "PDF document", "PDF 文書"),
    "format_csv": ("CSV 表格", "CSV table", "CSV 表"),
    "format_tsv": ("TSV 表格", "TSV table", "TSV 表"),
    "family_method": ("归组方式", "Grouping method", "グループ化の方法"),
    "family_domain": ("同一域名", "Same domain", "同一ドメイン"),
    "family_exact_content": ("响应字节完全一致", "Identical response bytes", "応答バイトが完全一致"),
    "family_exact_excerpt": ("摘录完全一致", "Identical extracts", "抜粋が完全一致"),
    "family_near_duplicate": ("正文近似重复", "Near-duplicate text", "本文が近似一致"),
    "family_note": ("来源归组是启发式提示，不证明转载关系、资料独立性或真实性。", "Lineage grouping is a heuristic hint, not proof of syndication, source independence, or truth.", "系統のグループ化は経験則による手掛かりです。転載関係、情報源の独立性、真実性の証明ではありません。"),
    "content_hash": ("响应字节 SHA-256（声明值）", "Response-byte SHA-256 (declared)", "応答バイトの SHA-256（申告値）"),
    "excerpt_hash": ("展示摘录 SHA-256", "Displayed-extract SHA-256", "表示抜粋の SHA-256"),
    "hash_note": ("渲染器可复算包内摘录摘要；无法从包内文字核验原始响应字节摘要，也不重新访问来源。", "The renderer can recompute the packaged extract's hash. It cannot verify the original response-byte hash from extract text and does not revisit sources.", "レンダラーは資料内の抜粋ハッシュを再計算できますが、抜粋から元の応答バイトのハッシュを検証できず、情報源にも再アクセスしません。"),
    "retrieval_gaps": ("检索缺口与补搜", "Retrieval gaps and follow-up searches", "検索の不足と追加検索"),
    "gaps_note": ("这些是词项匹配和来源谱系数量的启发式缺口提示，不代表命题真假、资料独立性或完整覆盖。", "These heuristic gaps concern term matches and source-family counts. They do not establish truth, independence, or complete coverage.", "検索語の一致と情報源系統の件数に基づく経験則上の不足です。真偽、独立性、網羅性を示しません。"),
    "gap_no_keyword_match": ("缺少词项匹配资料", "No matching source terms", "検索語が一致する資料なし"),
    "gap_limited_families": ("来源谱系覆盖有限", "Limited source-family coverage", "情報源系統の範囲が限定的"),
    "gap_attempted": ("已尝试补搜", "Follow-up search attempted", "追加検索を試行済み"),
    "gap_not_attempted": ("未尝试补搜", "Follow-up search not attempted", "追加検索は未試行"),
    "round_initial": ("初始检索", "Initial search", "初回検索"),
    "round_supplemental": ("补充检索", "Follow-up search", "追加検索"),
    "intent_neutral": ("中性资料", "Neutral sources", "中立的な資料"),
    "intent_support": ("支持方向", "Supporting direction", "支持する方向"),
    "intent_counter": ("反证方向", "Counter-evidence direction", "反証の方向"),
    "intent_actor_history": ("主体历史", "Actor history", "当事者の履歴"),
}
LANGUAGES = ("zh-CN", "en", "ja")
LOCALES = {language: {key: values[index] for key, values in _MESSAGES.items()} for index, language in enumerate(LANGUAGES)}


def tr(language: str, key: str, **values) -> str:
    if language not in LOCALES:
        raise ValueError(LOCALES["en"]["bad_language"])
    template = LOCALES[language].get(key)
    return template.format(**values) if template is not None else str(key)


def report_language(report: dict, override: str | None = None) -> str:
    language = override or report.get("language", "zh-CN")
    if language not in LOCALES:
        raise ValueError(tr("en", "bad_language"))
    return language


PUBLIC_FIELDS = (
    "schema_version", "topic", "scope", "generated_at", "depth", "language", "source_policy", "preferred_sources", "limitations", "claims",
    "evidence", "links", "timeline", "charts", "comparisons", "observations", "questions", "search_log", "retrieval_gaps",
)
FIELDS = {
    "claims": ("id", "text", "kind"),
    "evidence": ("id", "title", "url", "publisher", "published_at", "retrieved_at", "source_type", "content_kind", "excerpt", "context", "source_family", "status", "claim_ids", "screenshots", "excerpt_metadata", "document_format", "source_family_method", "source_family_evidence_ids", "content_sha256"),
    "links": ("from", "to", "relation", "note"),
    "timeline": ("date", "title", "detail", "evidence_ids", "citations"),
    "charts": ("title", "unit", "kind", "points", "note"),
    "comparisons": ("case", "date", "similarities", "differences", "limits", "evidence_ids", "citations"),
    "observations": ("kind", "text", "claim_ids", "evidence_ids", "citations"),
    "search_log": ("query", "intent", "provider", "result_count", "ran_at", "round", "gap_claim_ids"),
    "retrieval_gaps": ("claim_id", "reason", "query", "attempted"),
}


def project_citations(items):
    result = []
    for item in items:
        citation = {key: copy.deepcopy(item[key]) for key in ("evidence_id", "quote", "locator", "verification", "semantic_support") if key in item}
        if isinstance(citation.get("locator"), dict):
            citation["locator"] = {key: value for key, value in citation["locator"].items() if key in ("start", "end", "prefix", "suffix", "excerpt_sha256", "match_count", "coordinate_system")}
        result.append(citation)
    return result


def project_report(report: dict, mode: str) -> dict:
    """Allowlist public data rather than hiding verdicts with CSS."""
    result = {key: copy.deepcopy(report[key]) for key in PUBLIC_FIELDS if key in report}
    result["mode"] = mode
    result["depth"] = result.get("depth", "standard")
    result["language"] = report_language(report)
    result["source_policy"] = report.get("source_policy", "balanced")
    result["preferred_sources"] = [{key: item[key] for key in ("url", "label") if key in item} for item in report.get("preferred_sources", [])]
    if mode not in ("evidence-only", "ai-summary"):
        raise ValueError(tr(result["language"], "bad_mode"))
    for field, keys in FIELDS.items():
        result[field] = [{key: obj[key] for key in keys if key in obj} for obj in result.get(field, [])]
    for chart in result["charts"]:
        chart["points"] = [{key: p[key] for key in ("label", "value", "evidence_ids", "calculation", "citations") if key in p} for p in chart.get("points", [])]
        for point in chart["points"]:
            if isinstance(point.get("calculation"), dict):
                point["calculation"] = {k: v for k, v in point["calculation"].items() if k in ("operation", "source_quotes", "description")}
    for evidence in result["evidence"]:
        evidence["screenshots"] = [{key: s[key] for key in ("path", "url", "captured_at", "sha256", "source_url") if key in s} for s in evidence.get("screenshots", [])]
        if isinstance(evidence.get("excerpt_metadata"), dict):
            evidence["excerpt_metadata"] = {key: value for key, value in evidence["excerpt_metadata"].items() if key in ("sha256", "coordinate_system")}
    if mode == "ai-summary":
        if report.get("summary_language") is not None:
            result["summary_language"] = report_language(report, report["summary_language"])
        if not report.get("summary"):
            raise ValueError(tr(result["language"], "summary_required"))
        result["summary"] = {k: copy.deepcopy(v) for k, v in report["summary"].items() if k in ("text", "verdict", "caveats", "evidence_ids", "citations")}
        result["reasoning"] = [{k: copy.deepcopy(v) for k, v in row.items() if k in ("id", "premise_ids", "claim_id", "text", "kind", "citations")} for row in report.get("reasoning", [])]
        for projected, original in zip(result["claims"], report.get("claims", [])):
            for key in ("verdict", "analysis", "citations"):
                if key in original:
                    projected[key] = copy.deepcopy(original[key])
    else:
        for link in result["links"]:
            link["relation"] = "context" if link.get("relation") == "context" else "relevant_to"
            link["note"] = ""
    cited_items = [*result["claims"], *result["timeline"], *result["comparisons"], *result["observations"],
                   *result.get("reasoning", []), *([result["summary"]] if "summary" in result else []),
                   *(point for chart in result["charts"] for point in chart["points"])]
    for item in cited_items:
        if "citations" in item:
            item["citations"] = project_citations(item["citations"])
    return result


def safe_url(value: str, language: str = "zh-CN") -> str:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        raise ValueError(tr(language, "bad_url")) from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(tr(language, "bad_url"))
    return str(value)


def numeric_values(text: str) -> set[Decimal]:
    values = set()
    for token in re.findall(r"(?<![\d.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d|\.\d)", text):
        try:
            values.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            pass
    return values


def validate_exact_citations(item: dict, evidence: dict, allowed: set, language: str,
                             *, required: bool = False, maximum: int = 24) -> None:
    quotes = item.get("citations", [])
    if not isinstance(quotes, list) or len(quotes) > maximum or (required and not quotes):
        raise ValueError(tr(language, "bad_citation"))
    seen = set()
    for citation in quotes:
        eid, quote = citation.get("evidence_id"), citation.get("quote")
        if eid not in allowed or eid not in evidence or not isinstance(quote, str) or not quote.strip() or len(quote) > 2000 or "[REDACTED CREDENTIAL]" in quote or (eid, quote) in seen:
            raise ValueError(tr(language, "bad_citation"))
        seen.add((eid, quote))
        excerpt = evidence[eid].get("excerpt", "")
        start = excerpt.find(quote)
        if start < 0 or citation.get("semantic_support", "unverified") != "unverified" or citation.get("verification") not in (None, "exact_match"):
            raise ValueError(tr(language, "bad_citation"))
        locator = citation.get("locator")
        if required and (not isinstance(locator, dict) or citation.get("verification") != "exact_match"):
            raise ValueError(tr(language, "bad_citation"))
        if citation.get("verification") == "exact_match" and locator is None:
            raise ValueError(tr(language, "bad_citation"))
        if locator is not None:
            if not isinstance(locator, dict):
                raise ValueError(tr(language, "bad_citation"))
            end = start + len(quote)
            count, cursor = 0, start
            while cursor >= 0:
                count += 1
                cursor = excerpt.find(quote, cursor + 1)
            expected = {"start": start, "end": end, "prefix": excerpt[max(0, start - 80):start],
                        "suffix": excerpt[end:end + 80], "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                        "match_count": count, "coordinate_system": "unicode_codepoints"}
            if any(isinstance(locator.get(key), bool) or not isinstance(locator.get(key), int) for key in ("start", "end", "match_count")) or any(locator.get(key, "unicode_codepoints" if key == "coordinate_system" else None) != value for key, value in expected.items()):
                raise ValueError(tr(language, "bad_citation"))


def validate(report: dict, language: str | None = None) -> None:
    language = report_language(report, language)
    if report.get("schema_version") not in ("1.0", "1.1") or not report.get("topic"):
        raise ValueError(tr(language, "bad_schema"))
    strict_citations = report["schema_version"] == "1.1"
    if report.get("depth", "standard") not in ("brief", "standard", "deep"):
        raise ValueError(tr(language, "bad_depth"))
    if report.get("source_policy", "balanced") not in ("balanced", "preferred-only") or len(report.get("preferred_sources", [])) > 6:
        raise ValueError(tr(language, "bad_source_policy"))
    for item in report.get("preferred_sources", []):
        safe_url(item["url"], language)
    claims = [c["id"] for c in report["claims"]]
    evidence = [e["id"] for e in report["evidence"]]
    all_ids = claims + evidence
    if len(all_ids) != len(set(all_ids)):
        raise ValueError(tr(language, "duplicate_ids"))
    import re
    if any(not re.fullmatch(r"C[1-9]\d*", cid) for cid in claims) or any(not re.fullmatch(r"E[1-9]\d*", eid) for eid in evidence):
        raise ValueError(tr(language, "bad_ids"))
    known_claims, known_evidence = set(claims), set(evidence)
    source_by_id = {item["id"]: item for item in report["evidence"]}
    def refs(items):
        if not items or any(i not in known_evidence for i in items):
            raise ValueError(tr(language, "missing_refs"))
    for item in report["evidence"]:
        safe_url(item["url"], language)
        if any(cid not in known_claims for cid in item.get("claim_ids", [])):
            raise ValueError(tr(language, "bad_claim_ref"))
        if item.get("document_format", "unknown") not in ("unknown", "html", "text", "pdf", "csv", "tsv") or item.get("source_family_method", "domain") not in ("domain", "exact_content", "exact_excerpt", "near_duplicate") or any(eid not in known_evidence for eid in item.get("source_family_evidence_ids", [])):
            raise ValueError(tr(language, "bad_metadata"))
        content_hash = item.get("content_sha256")
        if content_hash is not None and (not isinstance(content_hash, str) or not re.fullmatch("[a-f0-9]{64}", content_hash)):
            raise ValueError(tr(language, "bad_metadata"))
        metadata = item.get("excerpt_metadata")
        if metadata is not None and (not isinstance(metadata, dict) or metadata.get("sha256") != hashlib.sha256(item.get("excerpt", "").encode("utf-8")).hexdigest() or metadata.get("coordinate_system", "unicode_codepoints") != "unicode_codepoints"):
            raise ValueError(tr(language, "bad_metadata"))
    for claim in report["claims"]:
        validate_exact_citations(claim, source_by_id, known_evidence, language, required=strict_citations and bool(claim.get("verdict") or claim.get("analysis")))
    for item in report["links"]:
        if item["from"] not in known_evidence or item["to"] not in known_claims:
            raise ValueError(tr(language, "bad_link"))
    for item in report["timeline"] + report["comparisons"]:
        refs(item.get("evidence_ids", []))
        validate_exact_citations(item, source_by_id, set(item["evidence_ids"]), language, required=strict_citations)
    for item in report.get("observations", []):
        refs(item.get("evidence_ids", []))
        if item.get("kind") not in ("data", "logic", "history") or not item.get("claim_ids") or any(cid not in known_claims for cid in item["claim_ids"]):
            raise ValueError(tr(language, "bad_observation"))
        validate_exact_citations(item, source_by_id, set(item["evidence_ids"]), language, required=strict_citations)
    for chart in report["charts"]:
        if chart.get("kind") not in ("bar", "line"):
            raise ValueError(tr(language, "bad_chart"))
        for point in chart.get("points", []):
            value = point.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)):
                raise ValueError(tr(language, "bad_value"))
            refs(point.get("evidence_ids", []))
            calculation = point.get("calculation")
            required = strict_citations and value is not None and not (calculation and not calculation.get("source_quotes"))
            validate_exact_citations(point, source_by_id, set(point["evidence_ids"]), language, required=required, maximum=100)
            if calculation is not None:
                quotes = calculation.get("source_quotes", [])
                excerpts = [e.get("excerpt", "") for e in report["evidence"] if e["id"] in point["evidence_ids"]]
                if calculation.get("operation") != "count" or value is None or value != len(quotes) or len(quotes) != len(set(quotes)) or len(calculation.get("description", "")) < 10 or any(not q.strip() or "[REDACTED CREDENTIAL]" in q or not any(q in excerpt for excerpt in excerpts) for q in quotes):
                    raise ValueError(tr(language, "bad_count"))
                if strict_citations and not all(any(citation["quote"] == quote for citation in point.get("citations", [])) for quote in quotes):
                    raise ValueError(tr(language, "bad_citation"))
            elif value is not None and (strict_citations or point.get("citations")):
                quoted_numbers = set().union(*(numeric_values(citation["quote"]) for citation in point.get("citations", [])))
                if Decimal(str(value)) not in quoted_numbers:
                    raise ValueError(tr(language, "bad_citation"))
    premises = set(evidence)
    premise_evidence = {eid: {eid} for eid in evidence}
    for step in report.get("reasoning", []):
        if not re.fullmatch(r"R[1-9]\d*", step["id"]) or step["id"] in premises or step.get("claim_id") not in known_claims or not step.get("premise_ids") or any(ref not in premises for ref in step["premise_ids"]):
            raise ValueError(tr(language, "bad_reasoning"))
        allowed = set().union(*(premise_evidence[premise] for premise in step["premise_ids"]))
        validate_exact_citations(step, source_by_id, allowed, language, required=strict_citations)
        premise_evidence[step["id"]] = allowed
        premises.add(step["id"])
    if "summary" in report:
        refs(report["summary"].get("evidence_ids", []))
        validate_exact_citations(report["summary"], source_by_id, set(report["summary"]["evidence_ids"]), language, required=strict_citations)
    if len(report.get("retrieval_gaps", [])) > 12 or len(report.get("search_log", [])) > 10:
        raise ValueError(tr(language, "bad_metadata"))
    for gap in report.get("retrieval_gaps", []):
        if gap.get("claim_id") not in known_claims or gap.get("reason") not in ("no_keyword_match", "limited_families") or not isinstance(gap.get("attempted"), bool) or not isinstance(gap.get("query"), str) or len(gap["query"]) > 600:
            raise ValueError(tr(language, "bad_metadata"))
    for search in report.get("search_log", []):
        if search.get("round", "initial") not in ("initial", "supplemental") or any(cid not in known_claims for cid in search.get("gap_claim_ids", [])):
            raise ValueError(tr(language, "bad_metadata"))


def esc(value, language: str = "zh-CN") -> str:
    if isinstance(value, list):
        value = "; ".join(map(str, value))
    return html.escape(str(value if value is not None else tr(language, "not_provided")), quote=True)


def citations(ids) -> str:
    return " ".join(f'<a class="ref" href="#{esc(i)}">{esc(i)}</a>' for i in ids)


def exact_citations_html(item: dict, language: str, *, legacy: bool = False) -> str:
    quotes = item.get("citations", [])
    t = lambda key, **values: esc(tr(language, key, **values))
    if not quotes:
        return f'<p class="muted">{t("citation_legacy")}</p>' if legacy else ""
    out = [f'<details class="exact-citations"><summary>{t("exact_citations", count=len(quotes))}</summary><p class="muted">{t("citation_note")}</p><ol>']
    for citation in quotes:
        locator = citation.get("locator")
        prefix = locator.get("prefix", "") if locator else ""
        suffix = locator.get("suffix", "") if locator else ""
        out.append(f'<li>{citations([citation["evidence_id"]])}<blockquote><span class="quote-context">{esc(prefix)}</span><mark>{esc(citation["quote"])}</mark><span class="quote-context">{esc(suffix)}</span></blockquote>')
        if locator:
            out.append(f'<p class="muted">{t("citation_position", start=locator["start"], end=locator["end"], count=locator["match_count"])}<br>{t("excerpt_hash")}: <code>{esc(locator["excerpt_sha256"])}</code></p>')
        else:
            out.append(f'<p class="muted">{t("citation_no_locator")}</p>')
        out.append('</li>')
    out.append('</ol></details>')
    return "".join(out)


def chart_svg(chart: dict, language: str = "zh-CN") -> str:
    points = chart.get("points", [])
    vals = [p["value"] for p in points if p.get("value") is not None]
    if not vals:
        return f'<p>{tr(language, "empty_chart")}</p>'
    lo, hi = min(0, min(vals)), max(0, max(vals))
    if lo == hi:
        hi = lo + 1
    def y(v):
        return 230 - (v - lo) / (hi - lo) * 190
    zero = y(0)
    out = [f'<svg role="img" aria-label="{esc(chart["title"])}" viewBox="0 0 720 290"><line x1="52" y1="{zero:.2f}" x2="705" y2="{zero:.2f}" stroke="#8295a0"/>']
    for val in (lo, hi):
        out.append(f'<text x="5" y="{y(val):.2f}" fill="#667681" font-size="12">{esc(round(val, 4))}</text>')
    step = 640 / max(len(points), 1)
    previous = None
    for index, point in enumerate(points):
        x, value = 65 + step * (index + .5), point.get("value")
        out.append(f'<text x="{x:.2f}" y="267" text-anchor="middle" font-size="12">{esc(point["label"])}</text>')
        if value is None:
            previous = None
            out.append(f'<text x="{x:.2f}" y="{zero-8:.2f}" text-anchor="middle" font-size="12">{tr(language, "missing")}</text>')
            continue
        py = y(value)
        if chart["kind"] == "bar":
            width = min(step * .6, 95)
            out.append(f'<rect x="{x-width/2:.2f}" y="{min(py, zero):.2f}" width="{width:.2f}" height="{abs(py-zero):.2f}" fill="#18766b"/>')
        else:
            if previous:
                out.append(f'<line x1="{previous[0]:.2f}" y1="{previous[1]:.2f}" x2="{x:.2f}" y2="{py:.2f}" stroke="#18766b" stroke-width="3"/>')
            out.append(f'<circle cx="{x:.2f}" cy="{py:.2f}" r="5" fill="#18766b"/>')
            previous = (x, py)
        out.append(f'<text x="{x:.2f}" y="{py-8 if value >= 0 else py+17:.2f}" text-anchor="middle" font-size="13">{esc(value)}</text>')
    out.append("</svg>")
    return "".join(out)


def screenshot_html(shot: dict, root: Path, capture_dir: Path | None, language: str = "zh-CN") -> str:
    filename = shot.get("path")
    if not filename and shot.get("url", "").startswith("/captures/") and capture_dir:
        filename = capture_dir.resolve() / Path(shot["url"]).name
    if not filename:
        return f'<p>{tr(language, "screenshot_missing")}</p>'
    path = Path(filename)
    path = path if path.is_absolute() else root / path
    try:
        raw = path.read_bytes()
    except OSError:
        raise ValueError(tr(language, "image_read")) from None
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError(tr(language, "image_large"))
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError(tr(language, "image_type"))
    digest = hashlib.sha256(raw).hexdigest()
    if shot.get("sha256") and shot["sha256"].lower() != digest:
        raise ValueError(tr(language, "image_hash"))
    original = safe_url(shot.get("source_url", ""), language)
    return f'<figure><a href="{esc(original)}" rel="noopener noreferrer"><img loading="lazy" src="data:{mime};base64,{base64.b64encode(raw).decode()}" alt="{tr(language, "screenshot_alt")}"/></a><figcaption>{tr(language, "captured")}: {esc(shot.get("captured_at"), language)}<br>SHA-256：{digest}<br>{tr(language, "screenshot_note")}</figcaption></figure>'


def evidence_map(report: dict, language: str) -> str:
    """Script-free overview. Source-to-claim direction and original reference IDs are preserved."""
    positions, boxes, edges = {}, [], []
    analysis = [(f"observation-{i}", row) for i, row in enumerate(report.get("observations", []))]
    if report.get("mode") == "ai-summary":
        analysis.extend((row["id"], row) for row in report.get("reasoning", []))
    groups = [(24, report["claims"], "claim"), (312, report["evidence"], "source"), (600, [dict(row, id=node_id) for node_id, row in analysis], "observations")]
    height = max(180, max(len(group[1]) for group in groups) * 64 + 60)
    for x, items, label in groups:
        boxes.append(f'<text x="{x}" y="28" font-size="13" fill="#4f5d75">{esc(tr(language, label))}</text>')
        for index, item in enumerate(items):
            y, node_id = 48 + index * 64, item["id"]
            positions[node_id] = (x, y)
            title = tr(language, item.get("kind", "unknown")) if label == "observations" else node_id
            caption = " · ".join(item.get("evidence_ids") or item.get("premise_ids") or item.get("claim_ids") or [])
            target = ("analysis-" + node_id) if node_id.startswith("observation-") else node_id
            boxes.append(f'<a href="#{esc(target)}"><rect x="{x}" y="{y}" width="248" height="48" rx="4" fill="#fff" stroke="#bfc7d3"/><text x="{x+12}" y="{y+20}" font-size="13" fill="#273242">{esc(title)}</text><text x="{x+12}" y="{y+37}" font-size="11" fill="#526075">{esc(caption[:34])}</text></a>')
    relations = {(row["from"], row["to"]) for row in report["links"]}
    relations.update((row["id"], claim_id) for row in report["evidence"] for claim_id in row.get("claim_ids", []))
    relations.update((source_id, node_id) for node_id, row in analysis for source_id in row.get("evidence_ids", row.get("premise_ids", [])))
    for source, target in sorted(relations):
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]; x2, y2 = positions[target]
        if x2 < x1:
            x2 += 248
        else:
            x1 += 248
        direction = 1 if x2 > x1 else -1
        edges.append(f'<path d="M{x1} {y1+24} C{x1+direction*20} {y1+24},{x2-direction*20} {y2+24},{x2} {y2+24}" fill="none" stroke="#9da9bb" stroke-width="1"/>')
    return f'<section><details><summary>{esc(tr(language,"map_title"))}</summary><p>{esc(tr(language,"map_note"))}</p><div style="overflow:auto;max-height:560px"><svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="evidence-map-title evidence-map-desc" viewBox="0 0 872 {height}" style="min-width:872px;width:100%;font-family:Arial,sans-serif"><title id="evidence-map-title">{esc(tr(language,"map_title"))}</title><desc id="evidence-map-desc">{esc(tr(language,"map_note"))}</desc>{"".join(edges+boxes)}</svg></div></details></section>'


def render(report: dict, root: Path, capture_dir: Path | None = None, language: str | None = None) -> str:
    language = report_language(report, language)
    t = lambda key, **values: esc(tr(language, key, **values))
    e = lambda value: esc(value, language)
    exact = lambda item: exact_citations_html(item, language, legacy=report.get("schema_version") == "1.0")
    depth = t(report.get("depth", "standard"))
    out = [f'<!doctype html><html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>No fake news · {t("title")}</title><style>{STYLE}</style><body><main><header><p class="eyebrow">NO FAKE NEWS / {t("title")}</p><h1>{e(report["topic"])}</h1><p class="mode">{t(report["mode"])} · {t("depth")}: {depth}</p><p>{e(report.get("scope", ""))}</p><small>{t("generated")}: {e(report.get("generated_at"))}</small>']
    if language != report.get("language", "zh-CN"):
        out.append(f'<p class="muted">{t("content_preserved")}</p>')
    out.append('</header>')
    if report.get("preferred_sources") or report.get("source_policy") == "preferred-only":
        out.append(f'<aside><h2>{t("source_scope")}</h2><p>{t(report.get("source_policy", "balanced"))}</p><ul>')
        for item in report.get("preferred_sources", []):
            out.append(f'<li><a href="{e(item["url"])}" rel="noopener noreferrer">{e(item.get("label") or item["url"])}</a></li>')
        out.append(f'</ul><p class="muted">{t("preferred_note")}</p></aside>')
    if report.get("limitations"):
        out.append(f'<aside><h2>{t("limits")}</h2><ul>' + "".join(f"<li>{e(text)}</li>" for text in report["limitations"]) + '</ul></aside>')
    out.append(evidence_map(report, language))
    out.append(f'<section><h2>01 / {t("claims")}</h2>')
    for claim in report["claims"]:
        linked = [link for link in report["links"] if link["to"] == claim["id"]]
        kind = "value_kind" if claim.get("kind") == "value" else claim.get("kind", "unknown")
        out.append(f'<article id="{e(claim["id"])}"><h3>{e(claim["id"])} · {e(claim["text"])}</h3><p class="muted">{t("type")}: {t(kind)}</p>')
        if "analysis" in claim:
            out.append(f'<p>{e(claim.get("verdict", ""))} {e(claim["analysis"])}</p>')
            out.append(exact(claim))
        for link in linked:
            out.append(f'<p>↳ {citations([link["from"]])} · {t(link["relation"])} {e(link.get("note", ""))}</p>')
        out.append('</article>')
    out.append(f'</section><section><h2>02 / {t("sources")}</h2>')
    for evidence in report["evidence"]:
        status = "status_retrieved" if evidence.get("status") == "retrieved" else evidence.get("status", "unknown")
        out.append(f'<article id="{e(evidence["id"])}"><p class="eyebrow">{e(evidence["id"])} · {e(evidence.get("publisher"))}</p><h3><a href="{e(evidence["url"])}" rel="noopener noreferrer">{e(evidence["title"])}</a></h3><p class="muted">{t(evidence.get("source_type", "unknown"))} / {t(evidence.get("content_kind", "unknown"))} / {t(status)}<br>{t("published")}: {e(evidence.get("published_at"))} · {t("retrieved")}: {e(evidence.get("retrieved_at"))}<br>{t("family")}: {e(evidence.get("source_family"))}</p><blockquote>{e(evidence.get("excerpt", ""))}</blockquote><p>{e(evidence.get("context", ""))}</p><p>{t("claim_refs")} {citations(evidence.get("claim_ids", []))}</p>')
        out.append(f'<p class="muted">{t("document_format")}: {t("format_" + evidence.get("document_format", "unknown"))}<br>{t("family_method")}: {t("family_" + evidence.get("source_family_method", "domain"))} {citations(evidence.get("source_family_evidence_ids", []))}<br>{t("family_note")}</p>')
        if evidence.get("content_sha256") or evidence.get("excerpt_metadata"):
            out.append('<details><summary>SHA-256</summary>')
            if evidence.get("content_sha256"):
                out.append(f'<p class="muted">{t("content_hash")}: <code>{e(evidence["content_sha256"])}</code></p>')
            if evidence.get("excerpt_metadata"):
                out.append(f'<p class="muted">{t("excerpt_hash")}: <code>{e(evidence["excerpt_metadata"]["sha256"])}</code></p>')
            out.append(f'<p class="muted">{t("hash_note")}</p></details>')
        for shot in evidence.get("screenshots", []):
            out.append(screenshot_html(shot, root, capture_dir, language))
        out.append('</article>')
    out.append('</section>')
    if report.get("observations"):
        out.append(f'<section><h2>{t("observations")}</h2><p class="muted">{t("observations_note")}</p>')
        for index, item in enumerate(report["observations"]):
            out.append(f'<article id="analysis-observation-{index}"><h3>{t(item["kind"])}</h3><p>{e(item["text"])}</p><p>{t("claim")} {citations(item["claim_ids"])} · {t("source")} {citations(item["evidence_ids"])}</p>{exact(item)}</article>')
        out.append('</section>')
    if report["charts"]:
        out.append(f'<section><h2>03 / {t("charts")}</h2>')
        for chart in report["charts"]:
            out.append(f'<article><h3>{e(chart["title"])}</h3><p>{t("unit")}: {e(chart.get("unit", ""))}</p>{chart_svg(chart, language)}<table><thead><tr><th>{t("item")}</th><th>{t("value")}</th><th>{t("source")}</th></tr></thead><tbody>')
            out.extend(f'<tr><td>{e(point["label"])}</td><td>{e(point.get("value"))}</td><td>{citations(point.get("evidence_ids", []))}{exact(point)}</td></tr>' for point in chart["points"])
            out.append(f'</tbody></table><p class="muted">{e(chart.get("note", ""))}</p>')
            for point in chart["points"]:
                if point.get("calculation"):
                    calc = point["calculation"]
                    out.append(f'<details><summary>{e(point["label"])} · {t("count_rules")}</summary><p>{e(calc["description"])}</p><p>{t("count_entries", count=len(calc["source_quotes"]))}</p><ul>' + ''.join(f'<li>{e(quote)}</li>' for quote in calc["source_quotes"]) + '</ul></details>')
            out.append('</article>')
        out.append('</section>')
    if report["timeline"]:
        out.append(f'<section><h2>04 / {t("timeline")}</h2><ol class="timeline">')
        out.extend(f'<li><time>{e(item["date"])}</time><h3>{e(item["title"])}</h3><p>{e(item["detail"])}</p>{citations(item["evidence_ids"])}{exact(item)}</li>' for item in report["timeline"])
        out.append('</ol></section>')
    if report["comparisons"]:
        out.append(f'<section><h2>05 / {t("comparisons")}</h2>')
        for comp in report["comparisons"]:
            out.append(f'<article><h3>{e(comp["case"])}</h3><p>{e(comp.get("date"))} {citations(comp["evidence_ids"])}</p><dl>')
            for key, label in (("similarities", "similarities"), ("differences", "differences"), ("limits", "inference_limits")):
                out.append(f'<dt>{t(label)}</dt><dd>{e(comp.get(key, ""))}</dd>')
            out.append('</dl>' + exact(comp) + '</article>')
        out.append('</section>')
    if "summary" in report:
        summary = report["summary"]
        if report.get("summary_language"):
            out.append(f'<p class="muted">{t("summary_language")}: {e(report["summary_language"])}</p>')
        out.append(f'<section><h2>06 / {t("summary")}</h2><article><h3>{e(summary.get("verdict"))}</h3><p>{e(summary["text"])}</p>{citations(summary["evidence_ids"])}<ul>' + "".join(f'<li>{e(text)}</li>' for text in summary.get("caveats", [])) + '</ul>' + exact(summary) + '</article>')
        for step in report.get("reasoning", []):
            out.append(f'<article id="{e(step["id"])}"><h3>{e(step["id"])} → {citations([step["claim_id"]])}</h3><p>{t("premises")} {citations(step["premise_ids"])}</p><p>{e(step["text"])}</p>{exact(step)}</article>')
        out.append('</section>')
    out.append(f'<section><h2>{t("questions")}</h2><ul>' + "".join(f'<li>{e(text)}</li>' for text in report.get("questions", [])) + f'</ul></section><details><summary>{t("search_log")}</summary>')
    out.extend(f'<p><strong>{e(item.get("query"))}</strong><br>{t("round_" + item.get("round", "initial"))} · {t("intent_" + item.get("intent", "neutral"))} · {e(item.get("provider"))} · {e(item.get("result_count"))} {t("results")} · {e(item.get("ran_at"))} {citations(item.get("gap_claim_ids", []))}</p>' for item in report["search_log"])
    out.append('</details>')
    if report.get("retrieval_gaps"):
        out.append(f'<section><h2>{t("retrieval_gaps")}</h2><p class="muted">{t("gaps_note")}</p><ul>')
        for gap in report["retrieval_gaps"]:
            out.append(f'<li>{citations([gap["claim_id"]])} · {t("gap_" + gap["reason"])} · {t("gap_attempted" if gap["attempted"] else "gap_not_attempted")}<p>{e(gap["query"])}</p></li>')
        out.append('</ul></section>')
    out.append(f'<footer>tell me truth · {t("footer")}</footer></main></body></html>')
    return "".join(out)


STYLE = """
:root{color-scheme:light;font:16px/1.8 system-ui,'Microsoft YaHei',sans-serif;color:#23333b;background:#f4f3ed}*{box-sizing:border-box}body{margin:0}main{max-width:1000px;margin:auto;padding:56px 24px}header{padding-bottom:32px;border-bottom:2px solid #213b40}h1{font-size:clamp(28px,4vw,44px);line-height:1.35}h2{font-size:21px;margin-top:36px}h3{font-size:18px;margin:8px 0}a{color:#116f65;text-underline-offset:4px}.eyebrow{letter-spacing:2px;font-size:12px;color:#58716f}.mode,.ref{display:inline-block;background:#e4eeea;padding:2px 10px;border-radius:4px}.ref{font-size:13px;margin:2px}article,aside{padding:22px 26px;background:#fffdf8;border:1px solid #dedfd5;border-radius:8px;margin:16px 0;scroll-margin-top:20px}.muted,small,figcaption{color:#607176;font-size:13px;overflow-wrap:anywhere}blockquote{margin:20px 0;padding:8px 18px;border-left:3px solid #278375;background:#f3f6f2;white-space:pre-wrap}svg{width:100%;max-height:340px;overflow:visible}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #e3e6df;text-align:left;padding:10px}figure{margin:20px 0}img{max-width:100%;border:1px solid #ddd}.timeline{border-left:2px solid #7cae9e;padding-left:28px;list-style:none}.timeline li{padding-bottom:22px}time{font:13px ui-monospace,monospace;color:#287769}dt{font-weight:600}dd{margin-left:0}details,footer{padding:20px 0}footer{margin-top:30px;color:#657778;font-size:13px}@media print{main{padding:0}article{break-inside:avoid}details{display:block}}@media(max-width:600px){main{padding:24px 16px}article,aside{padding:18px}td,th{padding:6px;font-size:13px}}
.exact-citations{padding:10px 0}.exact-citations summary{cursor:pointer;color:#176a62}.exact-citations ol{padding-left:24px}.exact-citations blockquote{font-size:14px;overflow-wrap:anywhere}.quote-context{color:#607176}mark{background:#fff0b2;color:#23333b}code{font:12px ui-monospace,monospace;overflow-wrap:anywhere}
"""


class LocalizedParser(argparse.ArgumentParser):
    def __init__(self, language: str):
        self.language = language
        super().__init__(description=tr(language, "cli_description"), add_help=False)
        self._positionals.title = tr(language, "positionals")
        self._optionals.title = tr(language, "options")

    def format_usage(self):
        return super().format_usage().replace("usage:", tr(self.language, "usage") + ":", 1)

    def format_help(self):
        return super().format_help().replace("usage:", tr(self.language, "usage") + ":", 1)

    def error(self, message):
        if "required:" in message:
            detail = tr(self.language, "required") + ": " + message.split("required:", 1)[1].strip()
        elif "unrecognized arguments:" in message:
            detail = tr(self.language, "unrecognized") + ": " + message.split("unrecognized arguments:", 1)[1].strip()
        elif "expected one argument" in message:
            detail = tr(self.language, "argument_value") + ": " + message.split(":", 1)[0].removeprefix("argument ")
        else:
            detail = tr(self.language, "invalid_arguments")
        self.print_usage(sys.stderr)
        self.exit(2, tr(self.language, "error") + ": " + detail + "\n")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cli_language = "zh-CN"
    for index, argument in enumerate(sys.argv[1:], 1):
        value = argument.split("=", 1)[1] if argument.startswith("--language=") else (sys.argv[index + 1] if argument == "--language" and index + 1 < len(sys.argv) else None)
        if value is not None:
            cli_language = value if value in LANGUAGES else "en"
    parser = LocalizedParser(cli_language)
    parser.add_argument("report", type=Path, metavar="REPORT", help=tr(cli_language, "cli_report"))
    parser.add_argument("--output", required=True, type=Path, metavar="HTML", help=tr(cli_language, "cli_output"))
    parser.add_argument("--mode", default="evidence-only", metavar="{evidence-only,ai-summary}", help=tr(cli_language, "cli_mode"))
    parser.add_argument("--language", metavar="{zh-CN,en,ja}", help=tr(cli_language, "cli_language"))
    parser.add_argument("--capture-dir", type=Path, metavar="DIR", help=tr(cli_language, "cli_capture"))
    parser.add_argument("-h", "--help", action="help", help=tr(cli_language, "cli_help"))
    args = parser.parse_args()
    try:
        if args.language is not None and args.language not in LANGUAGES:
            raise ValueError(tr(cli_language, "bad_language"))
        original = json.loads(args.report.read_text(encoding="utf-8-sig"))
        cli_language = report_language(original, args.language)
        if args.mode not in ("evidence-only", "ai-summary"):
            raise ValueError(tr(cli_language, "bad_mode"))
        report = project_report(original, args.mode)
        validate(report, cli_language)
        result = render(report, args.report.resolve().parent, args.capture_dir, cli_language)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        print(tr(cli_language, "saved", path=args.output.resolve(), mode=tr(cli_language, args.mode)))
    except json.JSONDecodeError:
        parser.exit(1, tr(cli_language, "render_failed") + ": " + tr(cli_language, "json_error") + "\n")
    except (KeyError, TypeError):
        parser.exit(1, tr(cli_language, "render_failed") + ": " + tr(cli_language, "structure_error") + "\n")
    except OSError:
        parser.exit(1, tr(cli_language, "render_failed") + ": " + tr(cli_language, "file_error") + "\n")
    except ValueError as exc:
        parser.exit(1, tr(cli_language, "render_failed") + ": " + str(exc) + "\n")


if __name__ == "__main__":
    main()

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
import sys
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
    "bad_schema": ("需要 schema_version=1.0 和 topic。", "schema_version=1.0 and topic are required.", "schema_version=1.0 と topic が必要です。"),
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
}
LANGUAGES = ("zh-CN", "en", "ja")
LOCALES = {language: {key: values[index] for key, values in _MESSAGES.items()} for index, language in enumerate(LANGUAGES)}


def tr(language: str, key: str, **values) -> str:
    if language not in LOCALES:
        raise ValueError(LOCALES["en"]["bad_language"])
    return LOCALES[language].get(key, key).format(**values)


def report_language(report: dict, override: str | None = None) -> str:
    language = override or report.get("language", "zh-CN")
    if language not in LOCALES:
        raise ValueError(tr("en", "bad_language"))
    return language


PUBLIC_FIELDS = (
    "schema_version", "topic", "scope", "generated_at", "depth", "language", "source_policy", "preferred_sources", "limitations", "claims",
    "evidence", "links", "timeline", "charts", "comparisons", "observations", "questions", "search_log",
)
FIELDS = {
    "claims": ("id", "text", "kind"),
    "evidence": ("id", "title", "url", "publisher", "published_at", "retrieved_at", "source_type", "content_kind", "excerpt", "context", "source_family", "status", "claim_ids", "screenshots"),
    "links": ("from", "to", "relation", "note"),
    "timeline": ("date", "title", "detail", "evidence_ids"),
    "charts": ("title", "unit", "kind", "points", "note"),
    "comparisons": ("case", "date", "similarities", "differences", "limits", "evidence_ids"),
    "observations": ("kind", "text", "claim_ids", "evidence_ids"),
    "search_log": ("query", "intent", "provider", "result_count", "ran_at"),
}


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
        chart["points"] = [{key: p[key] for key in ("label", "value", "evidence_ids", "calculation") if key in p} for p in chart.get("points", [])]
        for point in chart["points"]:
            if isinstance(point.get("calculation"), dict):
                point["calculation"] = {k: v for k, v in point["calculation"].items() if k in ("operation", "source_quotes", "description")}
    for evidence in result["evidence"]:
        evidence["screenshots"] = [{key: s[key] for key in ("path", "url", "captured_at", "sha256", "source_url") if key in s} for s in evidence.get("screenshots", [])]
    if mode == "ai-summary":
        if report.get("summary_language") is not None:
            result["summary_language"] = report_language(report, report["summary_language"])
        if not report.get("summary"):
            raise ValueError(tr(result["language"], "summary_required"))
        result["summary"] = {k: copy.deepcopy(v) for k, v in report["summary"].items() if k in ("text", "verdict", "caveats", "evidence_ids")}
        result["reasoning"] = [{k: copy.deepcopy(v) for k, v in row.items() if k in ("id", "premise_ids", "claim_id", "text", "kind")} for row in report.get("reasoning", [])]
        for projected, original in zip(result["claims"], report.get("claims", [])):
            for key in ("verdict", "analysis"):
                if key in original:
                    projected[key] = copy.deepcopy(original[key])
    else:
        for link in result["links"]:
            link["relation"] = "context" if link.get("relation") == "context" else "relevant_to"
            link["note"] = ""
    return result


def safe_url(value: str, language: str = "zh-CN") -> str:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        raise ValueError(tr(language, "bad_url")) from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(tr(language, "bad_url"))
    return str(value)


def validate(report: dict, language: str | None = None) -> None:
    language = report_language(report, language)
    if report.get("schema_version") != "1.0" or not report.get("topic"):
        raise ValueError(tr(language, "bad_schema"))
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
    def refs(items):
        if not items or any(i not in known_evidence for i in items):
            raise ValueError(tr(language, "missing_refs"))
    for item in report["evidence"]:
        safe_url(item["url"], language)
        if any(cid not in known_claims for cid in item.get("claim_ids", [])):
            raise ValueError(tr(language, "bad_claim_ref"))
    for item in report["links"]:
        if item["from"] not in known_evidence or item["to"] not in known_claims:
            raise ValueError(tr(language, "bad_link"))
    for item in report["timeline"] + report["comparisons"]:
        refs(item.get("evidence_ids", []))
    for item in report.get("observations", []):
        refs(item.get("evidence_ids", []))
        if item.get("kind") not in ("data", "logic", "history") or not item.get("claim_ids") or any(cid not in known_claims for cid in item["claim_ids"]):
            raise ValueError(tr(language, "bad_observation"))
    for chart in report["charts"]:
        if chart.get("kind") not in ("bar", "line"):
            raise ValueError(tr(language, "bad_chart"))
        for point in chart.get("points", []):
            value = point.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)):
                raise ValueError(tr(language, "bad_value"))
            refs(point.get("evidence_ids", []))
            calculation = point.get("calculation")
            if calculation is not None:
                quotes = calculation.get("source_quotes", [])
                excerpts = [e.get("excerpt", "") for e in report["evidence"] if e["id"] in point["evidence_ids"]]
                if calculation.get("operation") != "count" or value != len(quotes) or len(quotes) != len(set(quotes)) or len(calculation.get("description", "")) < 10 or any(not q or not any(q in excerpt for excerpt in excerpts) for q in quotes):
                    raise ValueError(tr(language, "bad_count"))
    premises = set(evidence)
    for step in report.get("reasoning", []):
        if not re.fullmatch(r"R[1-9]\d*", step["id"]) or step["id"] in premises or step.get("claim_id") not in known_claims or not step.get("premise_ids") or any(ref not in premises for ref in step["premise_ids"]):
            raise ValueError(tr(language, "bad_reasoning"))
        premises.add(step["id"])
    if "summary" in report:
        refs(report["summary"].get("evidence_ids", []))


def esc(value, language: str = "zh-CN") -> str:
    if isinstance(value, list):
        value = "; ".join(map(str, value))
    return html.escape(str(value if value is not None else tr(language, "not_provided")), quote=True)


def citations(ids) -> str:
    return " ".join(f'<a class="ref" href="#{esc(i)}">{esc(i)}</a>' for i in ids)


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
    t = lambda key, **values: tr(language, key, **values)
    e = lambda value: esc(value, language)
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
        for link in linked:
            out.append(f'<p>↳ {citations([link["from"]])} · {t(link["relation"])} {e(link.get("note", ""))}</p>')
        out.append('</article>')
    out.append(f'</section><section><h2>02 / {t("sources")}</h2>')
    for evidence in report["evidence"]:
        status = "status_retrieved" if evidence.get("status") == "retrieved" else evidence.get("status", "unknown")
        out.append(f'<article id="{e(evidence["id"])}"><p class="eyebrow">{e(evidence["id"])} · {e(evidence.get("publisher"))}</p><h3><a href="{e(evidence["url"])}" rel="noopener noreferrer">{e(evidence["title"])}</a></h3><p class="muted">{t(evidence.get("source_type", "unknown"))} / {t(evidence.get("content_kind", "unknown"))} / {t(status)}<br>{t("published")}: {e(evidence.get("published_at"))} · {t("retrieved")}: {e(evidence.get("retrieved_at"))}<br>{t("family")}: {e(evidence.get("source_family"))}</p><blockquote>{e(evidence.get("excerpt", ""))}</blockquote><p>{e(evidence.get("context", ""))}</p><p>{t("claim_refs")} {citations(evidence.get("claim_ids", []))}</p>')
        for shot in evidence.get("screenshots", []):
            out.append(screenshot_html(shot, root, capture_dir, language))
        out.append('</article>')
    out.append('</section>')
    if report.get("observations"):
        out.append(f'<section><h2>{t("observations")}</h2><p class="muted">{t("observations_note")}</p>')
        for index, item in enumerate(report["observations"]):
            out.append(f'<article id="analysis-observation-{index}"><h3>{t(item["kind"])}</h3><p>{e(item["text"])}</p><p>{t("claim")} {citations(item["claim_ids"])} · {t("source")} {citations(item["evidence_ids"])}</p></article>')
        out.append('</section>')
    if report["charts"]:
        out.append(f'<section><h2>03 / {t("charts")}</h2>')
        for chart in report["charts"]:
            out.append(f'<article><h3>{e(chart["title"])}</h3><p>{t("unit")}: {e(chart.get("unit", ""))}</p>{chart_svg(chart, language)}<table><thead><tr><th>{t("item")}</th><th>{t("value")}</th><th>{t("source")}</th></tr></thead><tbody>')
            out.extend(f'<tr><td>{e(point["label"])}</td><td>{e(point.get("value"))}</td><td>{citations(point.get("evidence_ids", []))}</td></tr>' for point in chart["points"])
            out.append(f'</tbody></table><p class="muted">{e(chart.get("note", ""))}</p>')
            for point in chart["points"]:
                if point.get("calculation"):
                    calc = point["calculation"]
                    out.append(f'<details><summary>{e(point["label"])} · {t("count_rules")}</summary><p>{e(calc["description"])}</p><p>{t("count_entries", count=len(calc["source_quotes"]))}</p><ul>' + ''.join(f'<li>{e(quote)}</li>' for quote in calc["source_quotes"]) + '</ul></details>')
            out.append('</article>')
        out.append('</section>')
    if report["timeline"]:
        out.append(f'<section><h2>04 / {t("timeline")}</h2><ol class="timeline">')
        out.extend(f'<li><time>{e(item["date"])}</time><h3>{e(item["title"])}</h3><p>{e(item["detail"])}</p>{citations(item["evidence_ids"])}</li>' for item in report["timeline"])
        out.append('</ol></section>')
    if report["comparisons"]:
        out.append(f'<section><h2>05 / {t("comparisons")}</h2>')
        for comp in report["comparisons"]:
            out.append(f'<article><h3>{e(comp["case"])}</h3><p>{e(comp.get("date"))} {citations(comp["evidence_ids"])}</p><dl>')
            for key, label in (("similarities", "similarities"), ("differences", "differences"), ("limits", "inference_limits")):
                out.append(f'<dt>{t(label)}</dt><dd>{e(comp.get(key, ""))}</dd>')
            out.append('</dl></article>')
        out.append('</section>')
    if "summary" in report:
        summary = report["summary"]
        if report.get("summary_language"):
            out.append(f'<p class="muted">{t("summary_language")}: {e(report["summary_language"])}</p>')
        out.append(f'<section><h2>06 / {t("summary")}</h2><article><h3>{e(summary.get("verdict"))}</h3><p>{e(summary["text"])}</p>{citations(summary["evidence_ids"])}<ul>' + "".join(f'<li>{e(text)}</li>' for text in summary.get("caveats", [])) + '</ul></article>')
        for step in report.get("reasoning", []):
            out.append(f'<article id="{e(step["id"])}"><h3>{e(step["id"])} → {citations([step["claim_id"]])}</h3><p>{t("premises")} {citations(step["premise_ids"])}</p><p>{e(step["text"])}</p></article>')
        out.append('</section>')
    out.append(f'<section><h2>{t("questions")}</h2><ul>' + "".join(f'<li>{e(text)}</li>' for text in report.get("questions", [])) + f'</ul></section><details><summary>{t("search_log")}</summary>')
    out.extend(f'<p><strong>{e(item.get("query"))}</strong><br>{e(item.get("intent"))} · {e(item.get("provider"))} · {e(item.get("result_count"))} {t("results")} · {e(item.get("ran_at"))}</p>' for item in report["search_log"])
    out.append(f'</details><footer>tell me truth · {t("footer")}</footer></main></body></html>')
    return "".join(out)


STYLE = """
:root{color-scheme:light;font:16px/1.8 system-ui,'Microsoft YaHei',sans-serif;color:#23333b;background:#f4f3ed}*{box-sizing:border-box}body{margin:0}main{max-width:1000px;margin:auto;padding:56px 24px}header{padding-bottom:32px;border-bottom:2px solid #213b40}h1{font-size:clamp(28px,4vw,44px);line-height:1.35}h2{font-size:21px;margin-top:36px}h3{font-size:18px;margin:8px 0}a{color:#116f65;text-underline-offset:4px}.eyebrow{letter-spacing:2px;font-size:12px;color:#58716f}.mode,.ref{display:inline-block;background:#e4eeea;padding:2px 10px;border-radius:4px}.ref{font-size:13px;margin:2px}article,aside{padding:22px 26px;background:#fffdf8;border:1px solid #dedfd5;border-radius:8px;margin:16px 0;scroll-margin-top:20px}.muted,small,figcaption{color:#607176;font-size:13px;overflow-wrap:anywhere}blockquote{margin:20px 0;padding:8px 18px;border-left:3px solid #278375;background:#f3f6f2;white-space:pre-wrap}svg{width:100%;max-height:340px;overflow:visible}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #e3e6df;text-align:left;padding:10px}figure{margin:20px 0}img{max-width:100%;border:1px solid #ddd}.timeline{border-left:2px solid #7cae9e;padding-left:28px;list-style:none}.timeline li{padding-bottom:22px}time{font:13px ui-monospace,monospace;color:#287769}dt{font-weight:600}dd{margin-left:0}details,footer{padding:20px 0}footer{margin-top:30px;color:#657778;font-size:13px}@media print{main{padding:0}article{break-inside:avoid}details{display:block}}@media(max-width:600px){main{padding:24px 16px}article,aside{padding:18px}td,th{padding:6px;font-size:13px}}
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

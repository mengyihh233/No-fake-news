from __future__ import annotations

import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from .models import Analysis, Chart, ChartPoint, Evidence, Report
from .security import ServiceError, check_url_shape
from .i18n import tr


def reject(message: str) -> None:
    raise ServiceError("invalid_evidence_reference", message)


def numeric_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in re.findall(r"(?<![\d.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.])", text):
        try:
            values.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            pass
    return values


def validate_count(point: ChartPoint, evidence: dict[str, Evidence]) -> bool:
    """Count quoted records, never infer missing records from a provider's snippet."""
    if not point.calculation:
        return False
    calculation = point.calculation
    if point.value is None:
        reject("缺失值不能附带一个计算结果；请移除 calculation 或提供可核验值。")
    quotes = calculation.source_quotes
    if any(not quote.strip() or "[REDACTED CREDENTIAL]" in quote for quote in quotes) or len(quotes) != len(set(quotes)):
        reject("派生计数必须使用非空且唯一的记录原句，不能重复计数。")
    excerpts = [evidence[eid].excerpt for eid in point.evidence_ids]
    if any(not any(quote in excerpt for excerpt in excerpts) for quote in quotes):
        reject("派生计数引用的记录原句未逐项出现在所引证据摘录中。")
    if Decimal(str(point.value)) != Decimal(len(quotes)):
        reject("派生计数数值与所列唯一记录数量不符。")
    # An empty list denotes zero observed records within the declared scope only.
    # A description is required by the schema; export always adds a completeness caveat.
    return True


def validate_references(report: Report) -> None:
    claims = {claim.id for claim in report.claims}
    evidence = {item.id: item for item in report.evidence}
    if len(claims) != len(report.claims) or len(evidence) != len(report.evidence):
        reject("报告含有重复的论断或证据 ID。")

    def check_ids(ids: list[str]) -> None:
        if not set(ids).issubset(evidence):
            reject("报告引用了未实际收集的证据 ID。")

    for item in report.evidence:
        check_url_shape(item.url)
        if not set(item.claim_ids).issubset(claims):
            reject("证据关联了不存在的论断。")
        for capture in item.screenshots:
            check_url_shape(capture.source_url)
    for link in report.links:
        if link.from_ not in evidence or link.to not in claims:
            reject("论证链接引用了不存在的证据或论断。")
    for item in [*report.timeline, *report.comparisons]:
        check_ids(item.evidence_ids)
    for observation in report.observations:
        check_ids(observation.evidence_ids)
        if not set(observation.claim_ids).issubset(claims):
            reject("资料比对观察关联了不存在的论断 ID。")
    for chart in report.charts:
        for point in chart.points:
            check_ids(point.evidence_ids)
            if validate_count(point, evidence):
                continue
            if point.value is None:
                continue
            values = set().union(*(numeric_values(evidence[eid].excerpt) for eid in point.evidence_ids))
            if Decimal(str(point.value)) not in values:
                reject("图表数值未出现在所引用的证据摘录中；拒绝生成无来源图表。")
    predecessors = set(evidence)
    for step in report.reasoning:
        if step.claim_id not in claims or step.id in predecessors or not set(step.premise_ids).issubset(predecessors):
            reject("论证链含有无效、重复或前向引用，不能构成可追溯链条。")
        predecessors.add(step.id)
    if report.summary:
        check_ids(report.summary.evidence_ids)


def validate_analysis(analysis: Analysis, report: Report) -> None:
    evidence = {item.id: item for item in report.evidence}
    claims = {claim.id for claim in report.claims}
    assessments = set()
    for assessment in analysis.claim_assessments:
        if assessment.claim_id not in claims or assessment.claim_id in assessments:
            reject("AI 评判了不存在或重复的论断 ID。")
        assessments.add(assessment.claim_id)
    annotations = set()
    for observation in analysis.observations:
        if not set(observation.claim_ids).issubset(claims) or not set(observation.evidence_ids).issubset(evidence):
            reject("资料比对观察引用了不存在的论断或证据 ID。")
    for annotation in analysis.evidence_annotations:
        if annotation.evidence_id not in evidence or annotation.evidence_id in annotations or not set(annotation.claim_ids).issubset(claims):
            reject("AI 引用了不存在或重复的证据或论断 ID。")
        annotations.add(annotation.evidence_id)
    # Evidence objects/URLs are immutable and created by the server. Even URLs embedded
    # inside prose cannot add a source that was not actually retrieved.
    known_urls = {item.url for item in report.evidence}
    for url in re.findall(r"https?://[^\s\"<>]+", analysis.model_dump_json()):
        if url.rstrip(".,，。;；)）]") not in known_urls:
            reject("AI 输出包含未检索取得的 URL，已拒绝。")
    for chart in analysis.charts:
        for point in chart.points:
            if not set(point.evidence_ids).issubset(evidence):
                reject("图表引用了不存在的证据 ID。")
            if validate_count(point, evidence):
                continue
            if point.value is None:
                continue
            quotes = [evidence[eid].excerpt for eid in point.evidence_ids]
            if "[REDACTED CREDENTIAL]" in point.source_quote or not any(point.source_quote in excerpt for excerpt in quotes):
                reject("图表所用原文引句未出现在已取得证据中。")
            if Decimal(str(point.value)) not in numeric_values(point.source_quote):
                reject("图表数值未出现在对应原文引句中。")


def apply_analysis(report: Report, analysis: Analysis, *, judgment_only: bool = False) -> Report:
    validate_analysis(analysis, report)
    result = report.model_copy(deep=True)
    result.limitations.extend(analysis.limitations)
    if not judgment_only:
        result.questions = analysis.questions
        result.links = analysis.links
        result.timeline = analysis.timeline
        result.comparisons = analysis.comparisons
        result.observations = analysis.observations
        result.charts = [Chart.model_validate(chart.model_dump(exclude={"points": {"__all__": {"source_quote"}}})) for chart in analysis.charts]
    if result.mode == "ai-summary":
        for assessment in analysis.claim_assessments:
            claim = next(claim for claim in result.claims if claim.id == assessment.claim_id)
            claim.verdict, claim.analysis = assessment.verdict, assessment.analysis
        result.reasoning = analysis.reasoning
        result.summary = analysis.summary
        if not result.summary:
            raise ServiceError("invalid_model_output", "AI 总结模式未返回带证据引用的 summary。")
    for annotation in ([] if judgment_only else analysis.evidence_annotations):
        item = next(item for item in result.evidence if item.id == annotation.evidence_id)
        item.claim_ids = annotation.claim_ids
        # Source classifications are tentative, never a truth score.
        item.source_type = annotation.source_type
        if result.mode == "ai-summary" and annotation.context:
            item.context += tr(" 来源识别/语境提示（AI，待核实）：", " Source/context note (AI-generated, unverified): ", " 情報源・文脈メモ（AI による未検証の記述）：", report.language) + annotation.context
    validate_references(result)
    return result


def public_report(report: Report | dict, mode: str | None = None) -> dict:
    """Allowlist export: evidence-only never carries a hidden verdict payload."""
    data = report.model_dump(by_alias=True) if isinstance(report, Report) else deepcopy(report)
    effective_mode = mode or data["mode"]
    data["mode"] = effective_mode
    language = data.get("language", "zh-CN")
    if any(point.get("calculation") for chart in data.get("charts", []) for point in chart["points"]):
        caveat = tr("派生计数只统计所引摘录中列明且唯一的记录。空清单的 0 表示该口径下没有列出的记录；口径描述或图表注释不能证明资料覆盖全集，请另行核查清单完整性。", "Derived counts include only the unique records quoted in the cited extracts. An empty-list zero means no records are listed within that scope; a description or chart note does not prove complete coverage. Verify the completeness of the list separately.", "派生件数は引用抜粋に明示された一意の記録のみを数えます。空リストの 0 は、その範囲で記録が列挙されていないという意味です。説明や注記で全件の網羅性は証明できません。別途、リストの完全性を確認してください。", language)
        if caveat not in data["limitations"]:
            data["limitations"].append(caveat)
    if effective_mode == "ai-summary":
        if data.get("summary") is None:
            data.pop("summary", None)
        return data
    allowed = {
        "schema_version", "topic", "mode", "depth", "language", "source_policy", "preferred_sources", "generated_at", "scope", "limitations", "claims", "evidence",
        "links", "timeline", "charts", "comparisons", "observations", "questions", "search_log",
    }
    data = {key: value for key, value in data.items() if key in allowed}
    data["claims"] = [{key: claim[key] for key in ("id", "text", "kind")} for claim in data["claims"]]
    data["links"] = [{
        "from": link["from"], "to": link["to"],
        "relation": "context" if link["relation"] == "context" else "relevant_to",
        "note": tr("背景材料，需自行核查。", "Background material; review independently.", "背景資料です。各自で確認してください。", language) if link["relation"] == "context" else tr("检索关联；不表示支持、反对或真实性裁决。", "Search relevance only; this is not a supporting, opposing, or truth judgment.", "検索上の関連性のみを示します。支持、反対、真偽の判断ではありません。", language),
    } for link in data["links"]]
    return data

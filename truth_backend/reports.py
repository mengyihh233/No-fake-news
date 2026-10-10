from __future__ import annotations

import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from .models import (Analysis, Chart, ChartPoint, Comparison, Evidence, Observation,
                     QuoteCitation, Reasoning, Report, Summary, TimelineItem)
from .citations import excerpt_metadata, locate_quote, validate_citations
from .quote_catalog import iter_analysis_quote_references
from .review_targets import reject_review, validate_citation_review
from .security import ServiceError, check_url_shape
from .i18n import tr


def reject(message: str) -> None:
    raise ServiceError("invalid_evidence_reference", message)


def numeric_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in re.findall(r"(?<![\d.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d|\.\d)", text):
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
    strict_citations = report.schema_version in {"1.1", "1.2"}
    claims = {claim.id for claim in report.claims}
    evidence = {item.id: item for item in report.evidence}
    if len(claims) != len(report.claims) or len(evidence) != len(report.evidence):
        reject("报告含有重复的论断或证据 ID。")

    def check_ids(ids: list[str]) -> None:
        if not set(ids).issubset(evidence):
            reject("报告引用了未实际收集的证据 ID。")

    for item in report.evidence:
        check_url_shape(item.url)
        if item.excerpt_metadata is not None and item.excerpt_metadata != excerpt_metadata(item.excerpt):
            reject("证据摘录摘要与提交文本不一致。")
        if not set(item.source_family_evidence_ids).issubset(evidence):
            reject("来源谱系引用了不存在的证据 ID。")
        if not set(item.claim_ids).issubset(claims):
            reject("证据关联了不存在的论断。")
        for capture in item.screenshots:
            check_url_shape(capture.source_url)
    for link in report.links:
        if link.from_ not in evidence or link.to not in claims:
            reject("论证链接引用了不存在的证据或论断。")
    for item in [*report.timeline, *report.comparisons]:
        check_ids(item.evidence_ids)
        validate_citations(item.citations, evidence, allowed_ids=item.evidence_ids, required=strict_citations, stored=True)
    for observation in report.observations:
        check_ids(observation.evidence_ids)
        if not set(observation.claim_ids).issubset(claims):
            reject("资料比对观察关联了不存在的论断 ID。")
        validate_citations(observation.citations, evidence, allowed_ids=observation.evidence_ids, required=strict_citations, stored=True)
    for claim in report.claims:
        validate_citations(claim.citations, evidence, required=strict_citations and bool(claim.verdict or claim.analysis), stored=True)
    for chart in report.charts:
        for point in chart.points:
            check_ids(point.evidence_ids)
            citation_required = strict_citations and point.value is not None and not (point.calculation and not point.calculation.source_quotes)
            validate_citations(point.citations, evidence, allowed_ids=point.evidence_ids, required=citation_required, stored=True)
            if validate_count(point, evidence):
                if strict_citations and point.calculation.source_quotes and not all(
                    any(citation.quote == quote for citation in point.citations)
                    for quote in point.calculation.source_quotes
                ):
                    reject("派生计数的每条原句都必须保留精确引文定位。")
                continue
            if point.value is None:
                continue
            values = set().union(*(numeric_values(evidence[eid].excerpt) for eid in point.evidence_ids))
            if Decimal(str(point.value)) not in values:
                reject("图表数值未出现在所引用的证据摘录中；拒绝生成无来源图表。")
            if point.citations and Decimal(str(point.value)) not in set().union(*(numeric_values(citation.quote) for citation in point.citations)):
                reject("图表数值未出现在保留的精确引文中。")
    predecessors = set(evidence)
    premise_evidence = {eid: {eid} for eid in evidence}
    for step in report.reasoning:
        if step.claim_id not in claims or step.id in predecessors or not set(step.premise_ids).issubset(predecessors):
            reject("论证链含有无效、重复或前向引用，不能构成可追溯链条。")
        allowed = set().union(*(premise_evidence[premise] for premise in step.premise_ids))
        validate_citations(step.citations, evidence, allowed_ids=allowed, required=strict_citations, stored=True)
        premise_evidence[step.id] = allowed
        predecessors.add(step.id)
    if report.summary:
        check_ids(report.summary.evidence_ids)
        validate_citations(report.summary.citations, evidence, allowed_ids=report.summary.evidence_ids, required=strict_citations, stored=True)
    for gap in report.retrieval_gaps:
        if gap.claim_id not in claims:
            reject("检索缺口关联了不存在的论断 ID。")
    for search in report.search_log:
        if not set(search.gap_claim_ids).issubset(claims):
            reject("补充搜索关联了不存在的论断 ID。")
    validate_citation_review(report)


def validate_analysis(analysis: Analysis, report: Report, *, require_citations: bool | None = None) -> None:
    if any(reference.quote_id is not None for reference in iter_analysis_quote_references(analysis)):
        reject("引文目录 ID 尚未由服务器解析，不能直接生成报告。")
    evidence = {item.id: item for item in report.evidence}
    claims = {claim.id for claim in report.claims}
    strict_citations = report.schema_version in {"1.1", "1.2"} if require_citations is None else require_citations
    assessments = set()
    for assessment in analysis.claim_assessments:
        if assessment.claim_id not in claims or assessment.claim_id in assessments:
            reject("AI 评判了不存在或重复的论断 ID。")
        assessments.add(assessment.claim_id)
        validate_citations(assessment.citations, evidence, required=strict_citations)
    annotations = set()
    for observation in analysis.observations:
        if not set(observation.claim_ids).issubset(claims) or not set(observation.evidence_ids).issubset(evidence):
            reject("资料比对观察引用了不存在的论断或证据 ID。")
        validate_citations(observation.citations, evidence, allowed_ids=observation.evidence_ids, required=strict_citations)
    for item in [*analysis.timeline, *analysis.comparisons, *([analysis.summary] if analysis.summary else [])]:
        if not set(item.evidence_ids).issubset(evidence):
            reject("分析引用了不存在的证据 ID。")
        validate_citations(item.citations, evidence, allowed_ids=item.evidence_ids, required=strict_citations)
    predecessors = {eid: {eid} for eid in evidence}
    for step in analysis.reasoning:
        if step.claim_id not in claims or step.id in predecessors or not set(step.premise_ids).issubset(predecessors):
            reject("论证链含有无效、重复或前向引用，不能构成可追溯链条。")
        allowed = set().union(*(predecessors[premise] for premise in step.premise_ids))
        validate_citations(step.citations, evidence, allowed_ids=allowed, required=strict_citations)
        predecessors[step.id] = allowed
    for annotation in analysis.evidence_annotations:
        if annotation.evidence_id not in evidence or annotation.evidence_id in annotations or not set(annotation.claim_ids).issubset(claims):
            reject("AI 引用了不存在或重复的证据或论断 ID。")
        annotations.add(annotation.evidence_id)
    # Evidence objects/URLs are immutable and created by the server. Narrative URLs
    # cannot add a source. Verbatim quotation fields may contain links printed in
    # the original extract: they remain plain source text, and every excluded field
    # is checked against that extract above or in the chart validation below.
    known_urls = {item.url for item in report.evidence}
    narrative = analysis.model_dump(by_alias=True)
    quoted_items = [*narrative["claim_assessments"], *narrative["observations"], *narrative["timeline"],
                    *narrative["comparisons"], *narrative["reasoning"],
                    *([narrative["summary"]] if narrative["summary"] is not None else [])]
    for chart in narrative["charts"]:
        for point in chart["points"]:
            quoted_items.append(point)
            if point["calculation"] is not None:
                point["calculation"].pop("source_quotes", None)
            elif point["value"] is not None:
                point.pop("source_quote", None)
            # Unused source_quote on a null/count point is not exact-checked;
            # leave it in the narrative URL scan rather than granting an exemption.
    for item in quoted_items:
        for citation in item["citations"]:
            citation.pop("quote", None)
    for url in re.findall(r"https?://[^\s\"<>]+", json.dumps(narrative, ensure_ascii=False)):
        if url.rstrip(".,，。;；)）]") not in known_urls:
            reject("AI 输出包含未检索取得的 URL，已拒绝。")
    for chart in analysis.charts:
        for point in chart.points:
            if not set(point.evidence_ids).issubset(evidence):
                reject("图表引用了不存在的证据 ID。")
            validate_citations(point.citations, evidence, allowed_ids=point.evidence_ids)
            if validate_count(point, evidence):
                if strict_citations and any(len(quote) > 2000 for quote in point.calculation.source_quotes):
                    reject("新分析的单条精确计数引句不能超过 2000 字符。")
                continue
            if point.value is None:
                continue
            quotes = [evidence[eid].excerpt for eid in point.evidence_ids]
            if "[REDACTED CREDENTIAL]" in point.source_quote or not any(point.source_quote in excerpt for excerpt in quotes):
                reject("图表所用原文引句未出现在已取得证据中。")
            if Decimal(str(point.value)) not in numeric_values(point.source_quote):
                reject("图表数值未出现在对应原文引句中。")


def apply_analysis(report: Report, analysis: Analysis, *, judgment_only: bool = False,
                   require_citations: bool | None = None) -> Report:
    validate_analysis(analysis, report, require_citations=require_citations)
    strict_citations = report.schema_version in {"1.1", "1.2"} if require_citations is None else require_citations
    result = report.model_copy(deep=True)
    # A new analysis changes statements or judgments and invalidates prior advice.
    result.citation_review = None
    evidence = {item.id: item for item in result.evidence}
    if not judgment_only:
        for item in result.evidence:
            item.excerpt_metadata = excerpt_metadata(item.excerpt)

    def hydrate(item, target):
        data = item.model_dump(by_alias=True)
        data["citations"] = [locate_quote(citation, evidence).model_dump() for citation in item.citations]
        return target.model_validate(data)

    def hydrate_chart(chart):
        data = chart.model_dump()
        for raw, point in zip(data["points"], chart.points):
            quotes = list(point.citations)
            originals = point.calculation.source_quotes if point.calculation else ([point.source_quote] if point.source_quote and point.value is not None else [])
            for quote in originals:
                # Long quotes were legal in 1.0 count records; preserve the record
                # without inventing a locator that exceeds the new citation schema.
                if len(quote) > 2000 and not strict_citations:
                    continue
                eid = next((eid for eid in point.evidence_ids if quote in evidence[eid].excerpt), None)
                if eid is not None and (eid, quote) not in {(citation.evidence_id, citation.quote) for citation in quotes}:
                    quotes.append(QuoteCitation(evidence_id=eid, quote=quote))
            if len(quotes) > 100:
                reject("图表精确引文超过单点 100 条的上限。")
            raw.pop("source_quote", None)
            raw["citations"] = [locate_quote(citation, evidence).model_dump() for citation in quotes]
        return Chart.model_validate(data)
    result.limitations.extend(analysis.limitations)
    if not judgment_only:
        result.questions = analysis.questions
        result.links = analysis.links
        result.timeline = [hydrate(item, TimelineItem) for item in analysis.timeline]
        result.comparisons = [hydrate(item, Comparison) for item in analysis.comparisons]
        result.observations = [hydrate(item, Observation) for item in analysis.observations]
        result.charts = [hydrate_chart(chart) for chart in analysis.charts]
    if result.mode == "ai-summary":
        for assessment in analysis.claim_assessments:
            claim = next(claim for claim in result.claims if claim.id == assessment.claim_id)
            claim.verdict, claim.analysis = assessment.verdict, assessment.analysis
            claim.citations = [locate_quote(citation, evidence) for citation in assessment.citations]
        result.reasoning = [hydrate(item, Reasoning) for item in analysis.reasoning]
        result.summary = hydrate(analysis.summary, Summary) if analysis.summary else None
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
    if data.get("citation_review") is not None:
        try:
            validated = report if isinstance(report, Report) else Report.model_validate(data)
        except ValidationError:
            reject_review(data.get("language", "zh-CN"))
        validate_references(validated)
    effective_mode = mode or data["mode"]
    data["mode"] = effective_mode
    language = data.get("language", "zh-CN")
    def omit_empty_citations(value):
        if isinstance(value, dict):
            for key in list(value):
                if key == "citations" and not value[key]:
                    value.pop(key)
                else:
                    omit_empty_citations(value[key])
        elif isinstance(value, list):
            for item in value:
                omit_empty_citations(item)

    omit_empty_citations(data)
    visible_citations = [citation for section in ("timeline", "comparisons", "observations")
                         for item in data.get(section, []) for citation in item.get("citations", [])]
    visible_citations += [citation for chart in data.get("charts", []) for point in chart["points"] for citation in point.get("citations", [])]
    if effective_mode == "ai-summary":
        visible_citations += [citation for item in [*data.get("claims", []), *data.get("reasoning", []), *([data["summary"]] if data.get("summary") else [])]
                              for citation in item.get("citations", [])]
    if visible_citations:
        caveat = tr("精确引文校验只确认原句在所展示摘录中原样出现；定位与摘要针对该摘录，不代表已定位原网页、重新取得导入资料、证实资料真实或验证引文足以支持论断。重复原句定位首处并记录匹配次数，语义支持关系仍需复核。", "Exact citation checks establish only that a quotation occurs verbatim in the displayed extract. Positions and hashes refer to that extract, not to a live webpage. They do not re-retrieve imported sources, establish authenticity, or validate semantic support for a claim. Repeated quotations use the first occurrence and expose the match count; review the support relationship independently.", "精確引用の検証は、表示された抜粋に引用文がそのまま存在することのみを確認します。位置とハッシュは抜粋に対するもので、元ページの位置、読み込んだ資料の再取得、真正性や主張への意味的な裏付けを証明しません。複数一致の場合は最初の位置と一致件数を示します。裏付けの関係は別途確認してください。", language)
        if caveat not in data["limitations"]:
            data["limitations"].append(caveat)
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
        "retrieval_gaps",
    }
    data = {key: value for key, value in data.items() if key in allowed}
    data["claims"] = [{key: claim[key] for key in ("id", "text", "kind")} for claim in data["claims"]]
    data["links"] = [{
        "from": link["from"], "to": link["to"],
        "relation": "context" if link["relation"] == "context" else "relevant_to",
        "note": tr("背景材料，需自行核查。", "Background material; review independently.", "背景資料です。各自で確認してください。", language) if link["relation"] == "context" else tr("检索关联；不表示支持、反对或真实性裁决。", "Search relevance only; this is not a supporting, opposing, or truth judgment.", "検索上の関連性のみを示します。支持、反対、真偽の判断ではありません。", language),
    } for link in data["links"]]
    return data

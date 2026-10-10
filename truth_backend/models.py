from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


Mode = Literal["evidence-only", "ai-summary"]
Depth = Literal["brief", "standard", "deep"]
Language = Literal["zh-CN", "en", "ja"]
Text = str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AIConfig(StrictModel):
    base_url: str = Field(default="", max_length=2000)
    api_key: SecretStr = SecretStr("")
    model: str = Field(default="", max_length=200)


class SearchConfig(StrictModel):
    provider: Literal["tavily", "brave", "deepseek"] = "tavily"
    api_key: SecretStr = SecretStr("")


class PreferredSource(StrictModel):
    url: str = Field(min_length=1, max_length=4000)
    label: str = Field(default="", max_length=300)


class SourceCredential(StrictModel):
    # Passwords/tokens are opaque values: never trim or normalize them.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    origin: str = Field(min_length=1, max_length=2000)
    kind: Literal["basic", "cookie", "bearer"]
    username: str = Field(default="", max_length=300)
    password: SecretStr = SecretStr("")
    token: SecretStr = SecretStr("")


class ResearchRequest(StrictModel):
    topic: str = Field(min_length=3, max_length=6000)
    mode: Mode = "evidence-only"
    depth: Depth = "standard"
    language: Language = "zh-CN"
    ai: AIConfig = Field(default_factory=AIConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    include_screenshots: bool = False
    adaptive_search: bool = False
    sources: list[PreferredSource] = Field(default_factory=list, max_length=6)
    source_policy: Literal["balanced", "preferred-only"] = "balanced"
    source_credentials: list[SourceCredential] = Field(default_factory=list, max_length=6)


class QuoteCitation(StrictModel):
    # A quotation is an opaque substring: whitespace normalization would change it.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    evidence_id: str = Field(pattern=r"^E[1-9]\d*$")
    quote: str = Field(min_length=1, max_length=2000)


class AnalysisQuoteReference(QuoteCitation):
    """Model input may select a server-issued passage instead of recopying it."""
    quote: str = Field(default="", max_length=2000)
    quote_id: str | None = Field(default=None, pattern=r"^E[1-9]\d*Q[1-9]\d*$", max_length=100)


class QuoteLocator(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    start: int = Field(ge=0, le=5000)
    end: int = Field(ge=1, le=5000)
    prefix: str = Field(max_length=80)
    suffix: str = Field(max_length=80)
    excerpt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    match_count: int = Field(ge=1, le=5000)
    coordinate_system: Literal["unicode_codepoints"] = "unicode_codepoints"


class Citation(QuoteCitation):
    locator: QuoteLocator | None = None
    verification: Literal["exact_match"] | None = None
    semantic_support: Literal["unverified"] = "unverified"


class ExcerptMetadata(StrictModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    coordinate_system: Literal["unicode_codepoints"] = "unicode_codepoints"


class Claim(StrictModel):
    id: str = Field(pattern=r"^C[1-9]\d*$")
    text: str = Field(min_length=1, max_length=1600)
    kind: Literal["fact", "causal", "prediction", "value", "mixed"]
    verdict: str | None = Field(default=None, max_length=1000)
    analysis: str | None = Field(default=None, max_length=5000)
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class Screenshot(StrictModel):
    url: str = Field(pattern=r"^/captures/[a-f0-9]{32}\.(?:png|jpg|webp)$")
    captured_at: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_url: str


class Evidence(StrictModel):
    id: str = Field(pattern=r"^E[1-9]\d*$")
    title: str = Field(max_length=1000)
    url: str = Field(max_length=4000)
    publisher: str = Field(max_length=300)
    published_at: str | None = Field(default=None, max_length=100)
    retrieved_at: str
    source_type: Literal["primary", "secondary", "unknown"] = "unknown"
    content_kind: Literal["full_text", "search_extract", "snippet"]
    excerpt: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(max_length=5000)
    context: str = Field(default="", max_length=6000)
    source_family: str = Field(max_length=400)
    status: Literal["retrieved", "snippet_only", "unavailable"]
    claim_ids: list[str] = Field(default_factory=list, max_length=12)
    screenshots: list[Screenshot] = Field(default_factory=list, max_length=3)
    excerpt_metadata: ExcerptMetadata | None = None
    document_format: Literal["unknown", "html", "text", "pdf", "csv", "tsv"] = "unknown"
    source_family_method: Literal["domain", "exact_content", "exact_excerpt", "near_duplicate"] = "domain"
    source_family_evidence_ids: list[str] = Field(default_factory=list, max_length=24)
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class Link(StrictModel):
    from_: str = Field(alias="from", description="An existing evidence ID (E#); source of the evidence-to-claim link.")
    to: str = Field(description="An existing claim ID (C#); target of the evidence-to-claim link.")
    relation: Literal["relevant_to", "supports", "contradicts", "qualifies", "context"]
    note: str = Field(default="", max_length=3000)


class TimelineItem(StrictModel):
    date: str = Field(max_length=100)
    title: str = Field(max_length=300)
    detail: str = Field(max_length=3000)
    evidence_ids: list[str] = Field(min_length=1, max_length=24)
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class Calculation(StrictModel):
    operation: Literal["count"]
    source_quotes: list[Annotated[str, StringConstraints(strip_whitespace=False)]] = Field(max_length=100)
    description: str = Field(min_length=10, max_length=3000)


class ChartPoint(StrictModel):
    label: str = Field(max_length=200)
    value: float | None = Field(allow_inf_nan=False)
    evidence_ids: list[str] = Field(min_length=1, max_length=24)
    calculation: Calculation | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=100)


class Chart(StrictModel):
    title: str = Field(max_length=300)
    unit: str = Field(max_length=100)
    kind: Literal["bar", "line"]
    points: list[ChartPoint] = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=3000)


class Comparison(StrictModel):
    case: str = Field(max_length=300)
    date: str = Field(max_length=100)
    similarities: str = Field(max_length=3000)
    differences: str = Field(max_length=3000)
    limits: str = Field(max_length=3000)
    evidence_ids: list[str] = Field(min_length=1, max_length=24)
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class Observation(StrictModel):
    kind: Literal["data", "logic", "history"]
    text: str = Field(min_length=1, max_length=5000)
    claim_ids: list[str] = Field(min_length=1, max_length=12)
    evidence_ids: list[str] = Field(min_length=1, max_length=24)
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class Reasoning(StrictModel):
    id: str = Field(pattern=r"^R[1-9]\d*$")
    premise_ids: list[str] = Field(min_length=1, max_length=48)
    claim_id: str
    text: str = Field(max_length=5000)
    kind: Literal["data", "logic", "history"]
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class Summary(StrictModel):
    text: str = Field(max_length=8000)
    verdict: str = Field(max_length=1000)
    caveats: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(min_length=1, max_length=24)
    citations: list[Citation] = Field(default_factory=list, max_length=24)


class SearchLog(StrictModel):
    query: str = Field(max_length=600)
    intent: str = Field(max_length=300)
    provider: str = Field(max_length=30)
    result_count: int = Field(ge=0, le=20)
    ran_at: str
    round: Literal["initial", "supplemental"] = "initial"
    gap_claim_ids: list[str] = Field(default_factory=list, max_length=12)


class RetrievalGap(StrictModel):
    claim_id: str = Field(pattern=r"^C[1-9]\d*$")
    reason: Literal["no_keyword_match", "limited_families"]
    query: str = Field(max_length=600)
    attempted: bool


class Report(StrictModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    topic: str = Field(min_length=1, max_length=6000)
    mode: Mode
    depth: Depth = "standard"
    language: Language = "zh-CN"
    source_policy: Literal["balanced", "preferred-only"] = "balanced"
    preferred_sources: list[PreferredSource] = Field(default_factory=list, max_length=6)
    generated_at: str
    scope: str = Field(max_length=4000)
    limitations: list[str] = Field(default_factory=list, max_length=80)
    claims: list[Claim] = Field(min_length=1, max_length=12)
    evidence: list[Evidence] = Field(max_length=24)
    links: list[Link] = Field(default_factory=list, max_length=120)
    timeline: list[TimelineItem] = Field(default_factory=list, max_length=30)
    charts: list[Chart] = Field(default_factory=list, max_length=5)
    comparisons: list[Comparison] = Field(default_factory=list, max_length=10)
    observations: list[Observation] = Field(default_factory=list, max_length=40)
    reasoning: list[Reasoning] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=20)
    summary: Summary | None = None
    summary_language: Language | None = None
    search_log: list[SearchLog] = Field(default_factory=list, max_length=10)
    retrieval_gaps: list[RetrievalGap] = Field(default_factory=list, max_length=12)


class SummarizeRequest(StrictModel):
    report: Report
    ai: AIConfig = Field(default_factory=AIConfig)
    language: Language = "zh-CN"


class PlanClaim(StrictModel):
    text: str = Field(min_length=1, max_length=1600)
    kind: Literal["fact", "causal", "prediction", "value", "mixed"]


class Query(StrictModel):
    query: str = Field(min_length=1, max_length=600)
    intent: Literal["neutral", "support", "counter", "actor_history"]


class Plan(StrictModel):
    claims: list[PlanClaim] = Field(min_length=1, max_length=12)
    queries: list[Query] = Field(min_length=1, max_length=8)
    scope: str = Field(max_length=4000)


class Assessment(StrictModel):
    claim_id: str
    verdict: str = Field(max_length=1000)
    analysis: str = Field(max_length=5000)
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class EvidenceAnnotation(StrictModel):
    evidence_id: str
    claim_ids: list[str] = Field(max_length=12)
    source_type: Literal["primary", "secondary", "unknown"] = "unknown"
    context: str = Field(default="", max_length=3000)


class VerifiedChartPoint(ChartPoint):
    source_quote: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(default="", max_length=1000)
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=100)


class VerifiedChart(Chart):
    points: list[VerifiedChartPoint] = Field(min_length=1, max_length=40)


class AnalysisTimelineItem(TimelineItem):
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class AnalysisComparison(Comparison):
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class AnalysisObservation(Observation):
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class AnalysisReasoning(Reasoning):
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class AnalysisSummary(Summary):
    citations: list[AnalysisQuoteReference] = Field(default_factory=list, max_length=24)


class Analysis(StrictModel):
    limitations: list[str] = Field(default_factory=list, max_length=20)
    evidence_annotations: list[EvidenceAnnotation] = Field(default_factory=list, max_length=24)
    claim_assessments: list[Assessment] = Field(default_factory=list, max_length=12)
    links: list[Link] = Field(default_factory=list, max_length=120)
    timeline: list[AnalysisTimelineItem] = Field(default_factory=list, max_length=30)
    charts: list[VerifiedChart] = Field(default_factory=list, max_length=5)
    comparisons: list[AnalysisComparison] = Field(default_factory=list, max_length=10)
    observations: list[AnalysisObservation] = Field(default_factory=list, max_length=40)
    reasoning: list[AnalysisReasoning] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=20)
    summary: AnalysisSummary | None = None

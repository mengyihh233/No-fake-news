"""Budgets are execution limits, never evidence quality scores."""

DEPTH_BUDGETS = {
    "brief": {"max_queries": 4, "max_supplemental_queries": 1, "max_sources": 6, "max_claims": 4, "excerpt_chars": 1800, "timeout_seconds": 150},
    "standard": {"max_queries": 4, "max_supplemental_queries": 2, "max_sources": 12, "max_claims": 8, "excerpt_chars": 3000, "timeout_seconds": 180},
    "deep": {"max_queries": 8, "max_supplemental_queries": 2, "max_sources": 24, "max_claims": 12, "excerpt_chars": 4500, "timeout_seconds": 360},
}

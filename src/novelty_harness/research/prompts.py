APPLICABILITY_VERSION = "family-applicability-v1"
APPLICABILITY = """Assess every evidence family for every MCU, independently of provider
availability. Exclude only with a semantic incompatibility and supporting input quotes.
User assertions of absence are not exclusion evidence. Missing detail means UNRESOLVED.
Academic framing must not suppress software/product; product framing must not suppress
scholarly/patent. Consider standards and regulatory context independently of adapters.
Return the explicit prompt version and the complete assessment matrix."""

STRATEGIST_VERSION = "search-strategist-v1"
STRATEGIST = """Translate contributions into provider-neutral search intents, not provider
syntax. Cover every plausible MCU/evidence family with multiple query families. Account for
all eleven query families by intent or a meaningful omission rationale. Preserve functions,
mechanisms, contribution-bearing relationships and combinations. Historical queries change
terminology; adjacent domains identify transferable mechanisms. Do not substitute user branding
or buzzwords for core concepts. No unjustified date/language restrictions. No novelty judgments.
Named entity discovery is a query family, not authorization for entity expansion."""

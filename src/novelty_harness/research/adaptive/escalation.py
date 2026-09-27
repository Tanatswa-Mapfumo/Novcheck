from novelty_harness.research.adaptive.models import BranchState, ResearchAction
from novelty_harness.research.retrieval.models import RetrievalStrategy

FALSIFICATION_STRATEGIES = frozenset(
    {
        RetrievalStrategy.SEMANTIC,
        RetrievalStrategy.CITATION_BACKWARD,
        RetrievalStrategy.CITATION_FORWARD,
        RetrievalStrategy.RELATED_WORK,
        RetrievalStrategy.ENTITY_LINEAGE,
        RetrievalStrategy.HISTORICAL_TERM,
        RetrievalStrategy.ADJACENT_DOMAIN,
        RetrievalStrategy.RELATIONAL,
    }
)


def multilingual_hook(state: BranchState, *, supported: bool) -> ResearchAction:
    return ResearchAction(
        action_type="MULTILINGUAL_HOOK" if supported else "MULTILINGUAL_UNAVAILABLE",
        mcu_id=state.mcu_id,
        evidence_family=state.evidence_family,
        rationale="Explicit translated intent required"
        if supported
        else "No translated intent/provider hook configured; multilingual coverage unavailable",
    )

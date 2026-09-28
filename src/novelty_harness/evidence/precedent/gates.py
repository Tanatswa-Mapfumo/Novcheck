"""Deterministic, constrained precedent classification over verified mappings.

Classification is a *local* source/MCU comparison. It consumes the mapping's
dimension comparison and the independent verification's commitment states; it
never sees quality tiers, retrieval ranks, provider scores or any novelty
verdict. A direct precedent always requires one eligible source/version whose
verified support covers every material commitment, including the
contribution-bearing relationships and configuration.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import MCUId, SourceId, SourceVersionId, SupportClaimId
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    EvidenceProposition,
    SourceMCUMapping,
)
from novelty_harness.evidence.precedent.models import PrecedentClassification
from novelty_harness.evidence.verification.models import (
    ChronologyState,
    SupportVerification,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

CLASSIFIER_VERSION = "precedent-classifier-v1"

FUNCTIONAL_DIMENSIONS = frozenset(
    {
        ComparisonDimension.PURPOSE,
        ComparisonDimension.PROBLEM,
        ComparisonDimension.TARGET,
        ComparisonDimension.INTENDED_OUTCOME,
        ComparisonDimension.EVALUATION_TARGET,
    }
)
RELATIONSHIP_DIMENSIONS = frozenset(
    {ComparisonDimension.RELATIONSHIPS, ComparisonDimension.CONTROL_FLOW}
)
CONFIGURATION_DIMENSIONS = frozenset({ComparisonDimension.ARCHITECTURE})
INGREDIENT_DIMENSIONS = frozenset({ComparisonDimension.MECHANISM, ComparisonDimension.FEATURES})
STRUCTURAL_DIMENSIONS = frozenset(
    {
        ComparisonDimension.MECHANISM,
        ComparisonDimension.ARCHITECTURE,
        ComparisonDimension.FEATURES,
        ComparisonDimension.RELATIONSHIPS,
        ComparisonDimension.CONTROL_FLOW,
        ComparisonDimension.CONSTRAINTS,
    }
)


class ClassificationFacts(ContractModel):
    """Everything the classifier may consider; no quality/rank/verdict."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["classification-facts-v1"] = "classification-facts-v1"

    proposition: EvidenceProposition
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    mapping: SourceMCUMapping | None = None
    verification: SupportVerification | None = None
    claim_id: SupportClaimId | None = None
    decisive: bool = False
    chronology_state: ChronologyState = "UNCERTAIN"
    selection_failure: NonBlankText | None = None


class MultiSourceAssessment(ContractModel):
    """Local multi-source summary; stitching is structurally forbidden."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["multi-source-assessment-v1"] = "multi-source-assessment-v1"

    mcu_id: MCUId
    combination_context: Literal["NONE", "MULTI_SOURCE_COMBINATION_ONLY"]
    single_source_direct_eligible: bool
    independent_roots: int = Field(ge=0)
    contributing_roots: int = Field(ge=0)
    stitched_direct_forbidden: Literal[True] = True
    summary: tuple[NonBlankText, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_consistent(self) -> Self:
        if self.contributing_roots > self.independent_roots:
            raise ValueError("Contributing roots cannot exceed independent roots")
        if self.combination_context == "MULTI_SOURCE_COMBINATION_ONLY" and (
            self.single_source_direct_eligible or self.contributing_roots < 2
        ):
            raise ValueError("Combination-only context requires multiple contributing roots")
        return self


def _classification(
    facts: ClassificationFacts,
    *,
    relation: PrecedentState,
    basis: Sequence[str],
    clock: Callable[[], datetime],
    provenance: ArtifactProvenance | None,
    covered_elements: Sequence[str] = (),
    covered_relationships: Sequence[str] = (),
    missing_elements: Sequence[str] = (),
    missing_relationships: Sequence[str] = (),
    configuration_gap: str | None = None,
    functional_similarity: Sequence[ComparisonDimension] = (),
    contradictions: Sequence[str] = (),
    unresolved: Sequence[str] = (),
    unassessable_reason: str | None = None,
    decisive: bool = False,
) -> PrecedentClassification:
    identity = canonical_hash(
        {
            "source_id": facts.source_id,
            "source_version_id": facts.source_version_id,
            "mcu_id": facts.proposition.mcu_id,
            "mapping_id": facts.mapping.mapping_id if facts.mapping else None,
            "verification_id": facts.verification.verification_id if facts.verification else None,
            "relation": relation.value,
            "classifier_version": CLASSIFIER_VERSION,
        }
    )
    return PrecedentClassification(
        classification_id="cls_" + identity,
        source_id=facts.source_id,
        source_version_id=facts.source_version_id,
        mcu_id=facts.proposition.mcu_id,
        mapping_id=facts.mapping.mapping_id if facts.mapping else "map_unavailable",
        verification_id=facts.verification.verification_id if facts.verification else None,
        relation=relation,
        decisive=decisive and relation == PrecedentState.DIRECT_PRECEDENT,
        basis=tuple(basis),
        covered_elements=tuple(covered_elements),
        covered_relationships=tuple(covered_relationships),
        missing_elements=tuple(missing_elements),
        missing_relationships=tuple(missing_relationships),
        configuration_gap=configuration_gap,
        functional_similarity=tuple(functional_similarity),
        contradictions=tuple(contradictions),
        unresolved=tuple(unresolved),
        unassessable_reason=unassessable_reason,
        classifier_version=CLASSIFIER_VERSION,
        observed_at=clock(),
        provenance=provenance
        or ArtifactProvenance(
            kind="implemented",
            component="precedent_classifier",
            detail="Local source/MCU comparison; no global absence claim.",
        ),
    )


def classify_precedent(
    facts: ClassificationFacts,
    *,
    clock: Callable[[], datetime] = utc_now,
    provenance: ArtifactProvenance | None = None,
) -> PrecedentClassification:
    """Classify one source/version against one MCU proposition."""

    mapping = facts.mapping
    verification = facts.verification
    if facts.selection_failure is not None or mapping is None or verification is None:
        reason = facts.selection_failure or "No verified mapping is available for this source"
        return _classification(
            facts,
            relation=PrecedentState.UNASSESSABLE,
            basis=(reason,),
            unassessable_reason=reason,
            clock=clock,
            provenance=provenance,
        )
    proposition = facts.proposition
    if (
        mapping.source_id != facts.source_id
        or mapping.source_version_id != facts.source_version_id
        or mapping.mcu_id != proposition.mcu_id
        or mapping.proposition_id != proposition.proposition_id
    ):
        raise ValueError("Mapping identity does not match the classified source/proposition")
    if (
        verification.source_id != facts.source_id
        or verification.source_version_id != facts.source_version_id
        or verification.mcu_id != proposition.mcu_id
        or verification.mapping_id != mapping.mapping_id
    ):
        raise ValueError("Verification identity does not match the classified mapping")
    if facts.claim_id is not None and verification.claim_id != facts.claim_id:
        raise ValueError("Verification does not answer the declared support claim")

    commitments = {item.commitment_id: item for item in facts.proposition.commitments}
    ordered_ids = [item.commitment_id for item in facts.proposition.commitments]
    states = {record.commitment_id: record.state for record in verification.commitment_states}
    if set(states) != set(commitments):
        raise ValueError("Verification must cover every material commitment exactly")

    supported = {identity for identity, state in states.items() if state == "SUPPORTED"}

    def texts(identities: set[str], *, relationships: bool) -> tuple[str, ...]:
        return tuple(
            commitments[identity].text
            for identity in ordered_ids
            if identity in identities
            and (commitments[identity].dimension in RELATIONSHIP_DIMENSIONS) is relationships
        )

    covered_elements = texts(supported, relationships=False)
    covered_relationships = texts(supported, relationships=True)
    missing_elements = texts(set(ordered_ids) - supported, relationships=False)
    missing_relationships = texts(set(ordered_ids) - supported, relationships=True)

    configuration_ids = {
        identity
        for identity in ordered_ids
        if commitments[identity].dimension in CONFIGURATION_DIMENSIONS | RELATIONSHIP_DIMENSIONS
    }
    ingredient_ids = {
        identity
        for identity in ordered_ids
        if commitments[identity].dimension in INGREDIENT_DIMENSIONS
    }
    mechanism_ids = {
        identity
        for identity in ordered_ids
        if commitments[identity].dimension == ComparisonDimension.MECHANISM
    }
    configuration_supported = bool(configuration_ids) and configuration_ids <= supported
    ingredients_supported = bool(ingredient_ids & supported)
    mechanism_supported = bool(mechanism_ids) and mechanism_ids <= supported
    supported_ratio = len(supported) / len(ordered_ids)
    functional_matched = tuple(
        dict.fromkeys(
            dimension.dimension
            for dimension in mapping.dimensions
            if dimension.matching and dimension.dimension in FUNCTIONAL_DIMENSIONS
        )
    )
    mapping_matching = any(dimension.matching for dimension in mapping.dimensions)

    if verification.state == SupportVerificationState.CONTRADICTED:
        return _classification(
            facts,
            relation=PrecedentState.CONTRADICTORY_EVIDENCE,
            basis=("Verified contradiction of the claimed proposition",),
            contradictions=verification.contradictions,
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT:
        return _classification(
            facts,
            relation=PrecedentState.UNRESOLVED,
            basis=("Material ambiguity remains after bounded same-source context expansion",),
            unresolved=verification.context_needed,
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if verification.state == SupportVerificationState.NOT_SUPPORTED:
        relation = (
            PrecedentState.SUPERFICIAL_SIMILARITY
            if mapping_matching or functional_matched
            else PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED
        )
        return _classification(
            facts,
            relation=relation,
            basis=(
                "No material commitment is supported by the cited passages",
                "Shared vocabulary or domain labels do not establish a mechanism"
                if relation == PrecedentState.SUPERFICIAL_SIMILARITY
                else "This source does not address the claimed proposition",
            ),
            functional_similarity=functional_matched,
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if supported == set(ordered_ids):
        if facts.decisive:
            return _classification(
                facts,
                relation=PrecedentState.DIRECT_PRECEDENT,
                basis=(
                    "One eligible source/version supports every material commitment, "
                    "including relationships and configuration",
                ),
                covered_elements=covered_elements,
                covered_relationships=covered_relationships,
                decisive=True,
                clock=clock,
                provenance=provenance,
            )
        return _classification(
            facts,
            relation=PrecedentState.UNRESOLVED,
            basis=(
                "Every material commitment is supported but the source is not "
                "temporally eligible as decisive precedent",
            ),
            unresolved=(
                "Chronology state is "
                + facts.chronology_state
                + "; post-cutoff or uncertain evidence cannot be decisive",
            ),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            clock=clock,
            provenance=provenance,
        )

    # Partial support: configuration-first, then functional analogy, then coverage.
    configuration_claimed = bool(configuration_ids)
    if functional_matched and not mechanism_supported and not configuration_supported:
        return _classification(
            facts,
            relation=PrecedentState.ANALOGOUS_PRECEDENT,
            basis=(
                "A relevant functional principle is shared while the claimed mechanism "
                "and configuration are not verified",
            ),
            functional_similarity=functional_matched,
            configuration_gap=(
                "Claimed configuration not established by this source"
                if configuration_claimed
                else None
            ),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if configuration_claimed and not configuration_supported and ingredients_supported:
        gap_details = "; ".join(
            (*missing_relationships, *texts(configuration_ids, relationships=False))
        )
        return _classification(
            facts,
            relation=PrecedentState.COMPONENT_PRECEDENT_ONLY,
            basis=(
                "Ingredients exist but the meaningful configuration has not been "
                "identified in this source",
            ),
            configuration_gap=(
                "Missing contribution-bearing relationships/configuration: " + gap_details
            ),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if supported_ratio > 0.5:
        return _classification(
            facts,
            relation=PrecedentState.STRONG_PARTIAL_PRECEDENT,
            basis=(
                "Most material aspects are supported but a substantive "
                "contribution-bearing element or relationship differs",
            ),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if functional_matched:
        return _classification(
            facts,
            relation=PrecedentState.ANALOGOUS_PRECEDENT,
            basis=("A functional principle is shared but the mechanism materially differs",),
            functional_similarity=functional_matched,
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    structural_supported = any(
        commitments[identity].dimension in STRUCTURAL_DIMENSIONS for identity in supported
    )
    if structural_supported:
        gap_details = "; ".join(
            (*missing_relationships, *texts(configuration_ids, relationships=False))
        )
        return _classification(
            facts,
            relation=PrecedentState.COMPONENT_PRECEDENT_ONLY,
            basis=(
                "Structural material is partially present but the claimed combination "
                "is not established by this source",
            ),
            configuration_gap=(
                "Missing contribution-bearing relationships/configuration: " + gap_details
                if configuration_claimed and not configuration_supported and gap_details
                else None
            ),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    if mapping_matching:
        return _classification(
            facts,
            relation=PrecedentState.SUPERFICIAL_SIMILARITY,
            basis=("Surface overlap without verified material support",),
            covered_elements=covered_elements,
            covered_relationships=covered_relationships,
            missing_elements=missing_elements,
            missing_relationships=missing_relationships,
            clock=clock,
            provenance=provenance,
        )
    return _classification(
        facts,
        relation=PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
        basis=("This source does not address the claimed proposition",),
        covered_elements=covered_elements,
        covered_relationships=covered_relationships,
        missing_elements=missing_elements,
        missing_relationships=missing_relationships,
        clock=clock,
        provenance=provenance,
    )


CONTRIBUTING_RELATIONS = frozenset(
    {
        PrecedentState.DIRECT_PRECEDENT,
        PrecedentState.STRONG_PARTIAL_PRECEDENT,
        PrecedentState.COMPONENT_PRECEDENT_ONLY,
        PrecedentState.ANALOGOUS_PRECEDENT,
    }
)


def summarize_multi_source(
    classifications: Sequence[PrecedentClassification],
    *,
    mcu_id: MCUId,
    independent_root_of: Mapping[SourceId, SourceId] | None = None,
) -> MultiSourceAssessment:
    """Summarize local classifications without ever stitching a direct precedent.

    Sources that share one lineage root (versions, mirrors, family duplicates)
    count as one contributing lineage.
    """

    roots = independent_root_of or {}
    contributing = [
        classification
        for classification in classifications
        if classification.relation in CONTRIBUTING_RELATIONS
    ]
    root_ids = {roots.get(item.source_id, item.source_id) for item in contributing}
    direct = any(
        classification.relation == PrecedentState.DIRECT_PRECEDENT
        for classification in classifications
    )
    combination = len(root_ids) >= 2 and not direct
    if direct:
        summary = (
            "One eligible source/version establishes local direct precedent; "
            "other sources are not required for that local comparison"
        )
    elif combination:
        summary = (
            "Multiple independent lineage roots contribute components; this is "
            "combination context only and can never constitute one-source direct precedent"
        )
    elif contributing:
        summary = "One lineage contributes partial/component context; no direct precedent"
    else:
        summary = "No contributing component or configuration context was found locally"
    return MultiSourceAssessment(
        mcu_id=mcu_id,
        combination_context=("MULTI_SOURCE_COMBINATION_ONLY" if combination else "NONE"),
        single_source_direct_eligible=direct,
        independent_roots=len(
            {roots.get(item.source_id, item.source_id) for item in classifications}
        ),
        contributing_roots=len(root_ids),
        summary=(summary,),
    )

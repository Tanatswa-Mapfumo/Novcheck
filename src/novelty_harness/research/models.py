from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import AssessmentId, MCUId, QueryId
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.runtime.tracing.hashing import canonical_hash


class FamilyApplicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    POSSIBLY_APPLICABLE = "POSSIBLY_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


class EvidenceFamilyAssessment(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    applicability: FamilyApplicability
    rationale: NonBlankText
    exclusion_reason: NonBlankText | None = None
    limitations: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def exclusion_is_explicit(self) -> Self:
        if (self.applicability == FamilyApplicability.NOT_APPLICABLE) != (
            self.exclusion_reason is not None
        ):
            raise ValueError("exclusion is required only for NOT_APPLICABLE")
        return self


class SearchIntent(ContractModel):
    model_config = ConfigDict(frozen=True)
    query_id: QueryId
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    query_family: QueryFamily
    text: NonBlankText
    rationale: NonBlankText
    concepts: tuple[NonBlankText, ...] = Field(min_length=1)
    relationship_terms: tuple[NonBlankText, ...] = ()
    historical_terms: tuple[NonBlankText, ...] = ()
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    combination_id: NonBlankText | None = None


class QueryOmission(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    query_family: QueryFamily
    rationale: NonBlankText


class SearchPlanIssueCategory(StrEnum):
    QUESTION_TRANSLATION = "QUESTION_TRANSLATION"
    CONCEPT_COVERAGE = "CONCEPT_COVERAGE"
    QUERY_FAMILY_GAP = "QUERY_FAMILY_GAP"
    TERMINOLOGY_GAP = "TERMINOLOGY_GAP"
    RELATIONSHIP_GAP = "RELATIONSHIP_GAP"
    HISTORICAL_GAP = "HISTORICAL_GAP"
    ADJACENT_DOMAIN_GAP = "ADJACENT_DOMAIN_GAP"
    BOOLEAN_OR_PROXIMITY = "BOOLEAN_OR_PROXIMITY"
    SPELLING_OR_SYNTAX = "SPELLING_OR_SYNTAX"
    LIMIT_OR_FILTER = "LIMIT_OR_FILTER"
    FAMILY_OMISSION = "FAMILY_OMISSION"
    OVERRELIANCE_ON_USER_TERMS = "OVERRELIANCE_ON_USER_TERMS"
    OVERCONSTRAINT = "OVERCONSTRAINT"


class SearchPlanIssue(ContractModel):
    model_config = ConfigDict(frozen=True)
    issue_id: NonBlankText
    category: SearchPlanIssueCategory
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    mcu_id: MCUId | None = None
    evidence_family: EvidenceFamily | None = None
    query_ids: tuple[QueryId, ...] = ()
    explanation: NonBlankText
    required_correction: NonBlankText | None = None


class SearchPlanReview(ContractModel):
    model_config = ConfigDict(frozen=True)
    review_id: NonBlankText
    plan_hash: NonBlankText
    status: Literal["PASS", "REVISE", "BLOCKED"]
    issues: tuple[SearchPlanIssue, ...]
    critic_prompt_version: NonBlankText

    @model_validator(mode="after")
    def no_false_pass(self) -> Self:
        if self.status == "PASS" and any(i.severity == "MATERIAL" for i in self.issues):
            raise ValueError("material issues prohibit PASS")
        if len({i.issue_id for i in self.issues}) != len(self.issues):
            raise ValueError("duplicate review issue IDs")
        return self


class ResearchPlan(ContractModel):
    """Rich Phase 3 artifact, distinct from the accepted domain SearchPlan projection."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["research-plan-v1"] = "research-plan-v1"
    assessment_id: AssessmentId
    as_of: date
    mcu_ids: tuple[MCUId, ...]
    combination_ids: tuple[NonBlankText, ...] = ()
    family_assessments: tuple[EvidenceFamilyAssessment, ...]
    intents: tuple[SearchIntent, ...]
    omissions: tuple[QueryOmission, ...] = ()
    reviewed: bool = False
    review_id: NonBlankText | None = None
    review: SearchPlanReview | None = None
    limitations: tuple[NonBlankText, ...] = ()

    def content_hash(self) -> str:
        return canonical_hash(
            self.model_dump(mode="json", exclude={"reviewed", "review_id", "review"})
        )

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        if len(set(self.mcu_ids)) != len(self.mcu_ids):
            raise ValueError("duplicate MCU IDs")
        branches = {(a.mcu_id, a.evidence_family): a for a in self.family_assessments}
        if len(branches) != len(self.family_assessments):
            raise ValueError("duplicate applicability branch")
        if any(a.mcu_id not in self.mcu_ids for a in self.family_assessments):
            raise ValueError("unknown applicability MCU")
        if len({q.query_id for q in self.intents}) != len(self.intents):
            raise ValueError("duplicate query IDs")
        identities = {
            (q.mcu_id, q.evidence_family, q.query_family, " ".join(q.text.casefold().split()))
            for q in self.intents
        }
        if len(identities) != len(self.intents):
            raise ValueError("duplicate normalized intent")
        for query in self.intents:
            branch = branches.get((query.mcu_id, query.evidence_family))
            if branch is None or branch.applicability == FamilyApplicability.NOT_APPLICABLE:
                raise ValueError("intent targets unknown or excluded branch")
            if (
                query.combination_id is not None
                and query.combination_id not in self.combination_ids
            ):
                raise ValueError("unknown combination reference")
        for omission in self.omissions:
            if (omission.mcu_id, omission.evidence_family) not in branches:
                raise ValueError("unknown omission branch")
        if self.reviewed and (self.review is None or self.review.status != "PASS"):
            raise ValueError("actual PASS review artifact required")
        if self.review is not None and (
            self.review.plan_hash != self.content_hash() or self.review_id != self.review.review_id
        ):
            raise ValueError("review does not bind this plan")
        if self.review is None and self.review_id is not None:
            raise ValueError("orphan review reference")
        return self

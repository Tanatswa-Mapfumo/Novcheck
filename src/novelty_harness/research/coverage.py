from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId, QueryId
from novelty_harness.research.models import FamilyApplicability, ResearchPlan
from novelty_harness.research.query_taxonomy import QueryFamily


class CoverageFloor(ContractModel):
    model_config = ConfigDict(frozen=True)
    min_distinct_query_families: int = Field(ge=2, le=len(QueryFamily))
    min_configured_providers: int = Field(ge=1)
    required_query_families: frozenset[QueryFamily] = frozenset()
    min_results_inspected_per_query: int | None = Field(default=None, ge=0)


class CoveragePolicy(ContractModel):
    model_config = ConfigDict(frozen=True)
    by_family: dict[EvidenceFamily, CoverageFloor]
    profile_version: NonBlankText = "standard-screening-v1"

    @model_validator(mode="after")
    def complete(self) -> Self:
        if set(self.by_family) != set(EvidenceFamily):
            raise ValueError("coverage policy must configure every family")
        return self

    @classmethod
    def standard(cls) -> Self:
        return cls(
            by_family={
                f: CoverageFloor(
                    min_distinct_query_families=2,
                    min_configured_providers=1,
                )
                for f in EvidenceFamily
            }
        )


class CoverageState(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXCLUDED_WITH_RATIONALE = "EXCLUDED_WITH_RATIONALE"
    PLANNED = "PLANNED"
    READY_FOR_SCREENING = "READY_FOR_SCREENING"
    SCREENED = "SCREENED"
    DEGRADED = "DEGRADED"
    BLOCKED_NO_PROVIDER = "BLOCKED_NO_PROVIDER"
    BLOCKED_PLAN_DEFECT = "BLOCKED_PLAN_DEFECT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class QueryScreeningOutcome(ContractModel):
    model_config = ConfigDict(frozen=True)
    query_id: QueryId
    provider_name: NonBlankText
    success: bool
    inspected_results: int = Field(ge=0)
    had_failed_attempts: bool = False
    complete: bool = True
    limitations: tuple[str, ...] = ()


class CoverageCell(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    state: CoverageState
    planned_query_families: frozenset[QueryFamily]
    configured_providers: tuple[NonBlankText, ...]
    successful_providers: tuple[NonBlankText, ...] = ()
    inspected_results: int = Field(default=0, ge=0)
    limitations: tuple[NonBlankText, ...] = ()


def evaluate_coverage(
    plan: ResearchPlan,
    policy: CoveragePolicy,
    providers: Mapping[EvidenceFamily, Sequence[str]],
    outcomes: Sequence[QueryScreeningOutcome] | None = None,
) -> tuple[CoverageCell, ...]:
    cells: list[CoverageCell] = []
    known = {q.query_id: q for q in plan.intents}
    if outcomes is not None:
        identities = [(o.query_id, o.provider_name) for o in outcomes]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate screening outcomes")
        for o in outcomes:
            if o.query_id not in known or o.provider_name not in providers.get(
                known[o.query_id].evidence_family, ()
            ):
                raise ValueError("unknown query/provider screening outcome")
    for branch in plan.family_assessments:
        queries = [
            q
            for q in plan.intents
            if (q.mcu_id, q.evidence_family) == (branch.mcu_id, branch.evidence_family)
        ]
        families = frozenset(q.query_family for q in queries)
        names = tuple(dict.fromkeys(providers.get(branch.evidence_family, ())))
        floor = policy.by_family[branch.evidence_family]
        completed = [o for o in outcomes or () if o.query_id in {q.query_id for q in queries}]
        successes = [o for o in completed if o.success]
        success_names = tuple(sorted({o.provider_name for o in successes}))
        notes = list(branch.limitations)
        notes.extend(n for o in completed for n in o.limitations)
        if branch.applicability == FamilyApplicability.NOT_APPLICABLE:
            state = CoverageState.EXCLUDED_WITH_RATIONALE
            notes.append(branch.exclusion_reason or "Explicit semantic exclusion")
        elif len(names) < floor.min_configured_providers:
            state = CoverageState.BLOCKED_NO_PROVIDER
            notes.append("Insufficient configured providers; family remains semantically plausible")
        elif (
            len(families) < floor.min_distinct_query_families
            or not floor.required_query_families <= families
        ):
            state = CoverageState.BLOCKED_PLAN_DEFECT
            notes.append("Planned query-diversity floor not met")
        elif not plan.reviewed:
            state = CoverageState.PLANNED
        elif outcomes is None:
            state = CoverageState.READY_FOR_SCREENING
        else:
            succeeded_families = {known[o.query_id].query_family for o in successes}
            enough = (
                len(succeeded_families) >= floor.min_distinct_query_families
                and floor.required_query_families <= succeeded_families
                and len(success_names) >= floor.min_configured_providers
                and {(q.query_id, n) for q in queries for n in names}
                <= {(o.query_id, o.provider_name) for o in successes}
                and (
                    floor.min_results_inspected_per_query is None
                    or all(
                        o.inspected_results >= floor.min_results_inspected_per_query
                        for o in successes
                    )
                )
            )
            failed = any(
                not o.success or o.had_failed_attempts or not o.complete for o in completed
            )
            state = (
                CoverageState.PROVIDER_FAILURE
                if completed and not successes
                else CoverageState.DEGRADED
                if failed or not enough
                else CoverageState.SCREENED
            )
            if state != CoverageState.SCREENED:
                notes.append("Failures or incomplete screening prevent clean coverage")
            if not any(o.inspected_results for o in successes):
                notes.append("Zero results are not evidence of absence of prior art")
        cells.append(
            CoverageCell(
                mcu_id=branch.mcu_id,
                evidence_family=branch.evidence_family,
                state=state,
                planned_query_families=families,
                configured_providers=names,
                successful_providers=success_names,
                inspected_results=sum(o.inspected_results for o in successes),
                limitations=tuple(notes),
            )
        )
    return tuple(cells)

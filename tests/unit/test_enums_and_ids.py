import json

import pytest
from pydantic import TypeAdapter, ValidationError

from novelty_harness.domain import enums

EXPECTED = {
    "AssessmentStage": (
        "RECEIVED NORMALIZED SUFFICIENCY_ASSESSED MCU_DECOMPOSED MCU_RECONCILED "
        "SEARCH_PLANNED SEARCH_PLAN_REVIEWED SCREENING ADAPTIVE_RESEARCH "
        "EVIDENCE_NORMALIZED EVIDENCE_MAPPED EVIDENCE_VERIFIED ADVERSARIAL_CHALLENGE "
        "DEFENCE_REVIEW PRELIMINARY_ADJUDICATION ROBUSTNESS_REVIEW FINDINGS_FROZEN "
        "REPORTED"
    ),
    "AssessmentStatus": "ACTIVE PARTIAL ABSTAINED BLOCKED FAILED COMPLETED",
    "SufficiencyState": "INSUFFICIENT EXPLORATORY ASSESSABLE HIGH_RESOLUTION",
    "ResearchDepth": (
        "INACTIVE SCREENING STANDARD DEEP ESCALATED SATURATED BUDGET_STOPPED ACCESS_BLOCKED"
    ),
    "ResearchMode": "QUICK STANDARD DEEP MAXIMUM",
    "EvidenceFamily": (
        "SCHOLARLY PATENT SOFTWARE PRODUCT GENERAL_WEB STANDARDS REGULATORY_GOVERNMENT "
        "GREY_LITERATURE HISTORICAL_ARCHIVAL"
    ),
    "EvidenceTier": "A B C D",
    "ValueMaturity": "CLAIMED PLAUSIBLE SUPPORTED DEMONSTRATED",
    "PrecedentState": (
        "DIRECT_PRECEDENT STRONG_PARTIAL_PRECEDENT COMPONENT_PRECEDENT_ONLY "
        "ANALOGOUS_PRECEDENT SUPERFICIAL_SIMILARITY NO_DIRECT_PRECEDENT_IDENTIFIED "
        "CONTRADICTORY_EVIDENCE UNRESOLVED UNASSESSABLE"
    ),
    "SupportVerificationState": (
        "SUPPORTED PARTIALLY_SUPPORTED NOT_SUPPORTED INSUFFICIENT_CONTEXT CONTRADICTED"
    ),
    "VerdictState": (
        "STRONG_EVIDENCE_OF_NOVELTY POTENTIALLY_NOVEL MIXED_CONTRIBUTION_SPECIFIC "
        "NOT_NOVEL_AT_CLAIMED_LEVEL UNASSESSABLE"
    ),
    "TraceStatus": "SUCCESS FAILURE SKIPPED DEGRADED",
    "FailureClass": (
        "INPUT_SPECIFICATION_FAILURE MCU_DECOMPOSITION_INSTABILITY "
        "QUERY_GENERATION_FAILURE SEARCH_PLAN_REVIEW_FAILURE SOURCE_ACCESS_FAILURE "
        "PROVIDER_FAILURE SOURCE_COVERAGE_FAILURE LANGUAGE_COVERAGE_FAILURE "
        "TEMPORAL_COVERAGE_FAILURE DOMAIN_TERMINOLOGY_FAILURE "
        "EVIDENCE_EXTRACTION_FAILURE EVIDENCE_SUPPORT_FAILURE PROVENANCE_AMBIGUITY "
        "CONFLICTING_EVIDENCE LOW_SOURCE_QUALITY SEARCH_NON_SATURATION "
        "BUDGET_EXHAUSTION ADJUDICATION_INSTABILITY ROBUSTNESS_TEST_FAILURE"
    ),
}


@pytest.mark.parametrize("name, values", EXPECTED.items())
def test_enum_json_values_are_canonical(name: str, values: str) -> None:
    enum_type = getattr(enums, name)
    expected = values.split()
    assert [member.value for member in enum_type] == expected
    adapter = TypeAdapter(enum_type)
    for value in expected:
        assert json.loads(adapter.dump_json(adapter.validate_python(value))) == value
        assert adapter.validate_json(json.dumps(value)) == enum_type(value)
    with pytest.raises(ValidationError):
        adapter.validate_python("UNKNOWN")


@pytest.mark.parametrize(
    "alias, factory, prefix",
    [
        ("AssessmentId", "new_assessment_id", "asm_"),
        ("IdeaId", "new_idea_id", "idea_"),
        ("MCUId", "new_mcu_id", "mcu_"),
        ("SourceId", "new_source_id", "src_"),
        ("PassageId", "new_passage_id", "pass_"),
        ("EvidenceEdgeId", "new_evidence_edge_id", "edge_"),
        ("QueryId", "new_query_id", "qry_"),
        ("SearchRunId", "new_search_run_id", "run_"),
        ("TraceEventId", "new_trace_event_id", "trace_"),
        ("LifecycleEventId", "new_lifecycle_event_id", "life_"),
    ],
)
def test_identifiers_validate_and_serialize(alias: str, factory: str, prefix: str) -> None:
    from novelty_harness.domain import ids

    adapter = TypeAdapter(getattr(ids, alias))
    make_id = getattr(ids, factory)
    first, second = make_id(), make_id()
    assert first.startswith(prefix)
    assert first != second
    assert json.loads(adapter.dump_json(adapter.validate_python(first))) == first
    assert adapter.validate_json(json.dumps(first)) == first
    for invalid in ("wrong_value", prefix, "", prefix + "\n"):
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid)

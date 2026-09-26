from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.enums import (
    EvidenceFamily,
    PrecedentState,
    SufficiencyState,
    SupportVerificationState,
    VerdictState,
)
from novelty_harness.domain.evidence import (
    EvidenceComparison,
    EvidenceEdge,
    SourceDates,
    SourcePassage,
    SourceRecord,
)
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    ClaimedAdvantage,
    IdeaContext,
    ProblemDescription,
    SufficiencyAssessment,
)
from novelty_harness.domain.mcu import MCU, MCUCombination, MCUFeature, MCUGraph, MCURelationship
from novelty_harness.domain.reporting import CompiledReport, ReportAnswers
from novelty_harness.domain.research import PlannedQuery, SearchPlan, SearchPlanReview


def provenance():
    return ArtifactProvenance(kind="fixture", component="fixture", detail="Synthetic data")


def idea():
    return CanonicalIdeaRepresentation(
        idea_id="idea_test",
        original_input="  Exact user input\nwith whitespace.  ",
        original_input_ref="request.json#/input_text",
        problem=ProblemDescription(statement="An explicitly supplied problem"),
        context=IdeaContext(temporal_cutoff=date(2026, 9, 26)),
        provenance=provenance(),
    )


def mcu():
    return MCU(
        mcu_id="mcu_one", label="First", statement="Fixture contribution", provenance=provenance()
    )


def query():
    return PlannedQuery(
        query_id="qry_one",
        mcu_id="mcu_one",
        family="RELATIONAL",
        evidence_family=EvidenceFamily.SOFTWARE,
        text="fixture query",
        rationale="Exercise the transport",
        generated_by="fixture",
        provenance=provenance(),
    )


def edge():
    return EvidenceEdge(
        edge_id="edge_one",
        source_id="src_one",
        mcu_id="mcu_one",
        proposition="Fixture proposition",
        passage_ids=("pass_one",),
        comparison=EvidenceComparison(),
        relation_type=PrecedentState.UNRESOLVED,
        support_verification=SupportVerificationState.SUPPORTED,
        provenance=provenance(),
    )


def adjudication():
    return FrozenAdjudication(
        assessment_id="asm_one",
        as_of=date(2026, 9, 26),
        frozen_at=datetime(2026, 9, 26, tzinfo=UTC),
        overall_state=VerdictState.UNASSESSABLE,
        mcus=(
            MCUFinding(
                mcu_id="mcu_one",
                precedent_state=PrecedentState.UNRESOLVED,
                verdict=VerdictState.UNASSESSABLE,
            ),
        ),
        provenance=provenance(),
    )


def contracts():
    answers = ReportAnswers(**{f"q{i}": f"Frozen answer {i}" for i in range(1, 10)})
    return [
        provenance(),
        idea().problem,
        idea().context,
        idea(),
        ClaimedAdvantage(dimension="cost", statement="Claimed cost saving"),
        SufficiencyAssessment(
            idea_id="idea_test", state=SufficiencyState.ASSESSABLE, provenance=provenance()
        ),
        MCUFeature(feature_id="F1", concept="Input"),
        MCURelationship(subject="F1", relation="PRODUCES", object="F2"),
        mcu(),
        MCUCombination(
            combination_id="C1",
            label="Combined",
            statement="Fixture combination",
            member_ids=("mcu_one", "mcu_two"),
            provenance=provenance(),
        ),
        MCUGraph(idea_id="idea_test", mcus=(mcu(),), provenance=provenance()),
        query(),
        SearchPlan(idea_id="idea_test", queries=(query(),), provenance=provenance()),
        SearchPlanReview(plan_hash="hash", approved=True, provenance=provenance()),
        SourceDates(publication_date=date(2025, 1, 1)),
        SourceRecord(
            source_id="src_one",
            source_type="report",
            provider_name="fixture",
            provider_source_id="one",
            access_state="full_text",
            content_hash="hash",
            provenance=provenance(),
        ),
        SourcePassage(
            passage_id="pass_one",
            source_id="src_one",
            text="Synthetic passage",
            content_hash="hash",
            provenance=provenance(),
        ),
        EvidenceComparison(),
        edge(),
        adjudication().mcus[0],
        adjudication(),
        answers,
        CompiledReport(
            assessment_id="asm_one",
            adjudication_hash="hash",
            overall_verdict=VerdictState.UNASSESSABLE,
            answers=answers,
            markdown="Synthetic report",
            provenance=provenance(),
        ),
    ]


@pytest.mark.parametrize("index", range(23))
def test_phase1_contracts_round_trip_and_forbid_extra_fields(index):
    value = contracts()[index]
    assert type(value).model_validate_json(value.model_dump_json()) == value
    assert value.schema_version == "0.1"
    with pytest.raises(ValidationError):
        type(value).model_validate({**value.model_dump(), "unexpected": True})


def test_original_input_preserved_without_inventing_mechanism():
    assert idea().original_input == "  Exact user input\nwith whitespace.  "
    assert idea().mcu_ids == ()
    assert idea().combination_ids == ()
    assert mcu().mechanism is None
    assert idea().claimed_advantages == ()


@pytest.mark.parametrize("blank", ["", " ", "\n\t"])
def test_problem_statement_cannot_be_blank(blank):
    with pytest.raises(ValidationError):
        ProblemDescription(statement=blank)


@pytest.mark.parametrize("field", ["mcu_id", "label", "statement"])
def test_mcu_required_identity_and_text_cannot_be_blank(field):
    with pytest.raises(ValidationError):
        MCU.model_validate({**mcu().model_dump(), field: " "})


@pytest.mark.parametrize("members", [(), ("mcu_one",), ("mcu_one", "mcu_one")])
def test_combination_requires_two_distinct_members(members):
    with pytest.raises(ValidationError):
        MCUCombination(
            combination_id="C1",
            label="Combination",
            statement="Fixture",
            member_ids=members,
            provenance=provenance(),
        )


@pytest.mark.parametrize("field", ["text", "rationale"])
def test_query_requires_nonblank_text_and_rationale(field):
    with pytest.raises(ValidationError):
        PlannedQuery.model_validate({**query().model_dump(), field: " "})


def test_search_plan_requires_queries():
    with pytest.raises(ValidationError):
        SearchPlan(idea_id="idea_test", queries=(), provenance=provenance())


def test_edge_requires_passages():
    with pytest.raises(ValidationError):
        EvidenceEdge.model_validate({**edge().model_dump(), "passage_ids": []})


def test_findings_are_deeply_frozen_and_do_not_invent_verdicts():
    value = adjudication()
    assert value.overall_state == VerdictState.UNASSESSABLE
    with pytest.raises(ValidationError):
        value.overall_state = VerdictState.POTENTIALLY_NOVEL
    with pytest.raises(ValidationError):
        value.mcus[0].verdict = VerdictState.POTENTIALLY_NOVEL
    assert isinstance(value.mcus, tuple)


@pytest.mark.parametrize("missing", range(1, 10))
def test_report_requires_every_canonical_answer(missing):
    values = {f"q{i}": f"Answer {i}" for i in range(1, 10) if i != missing}
    with pytest.raises(ValidationError):
        ReportAnswers.model_validate(values)

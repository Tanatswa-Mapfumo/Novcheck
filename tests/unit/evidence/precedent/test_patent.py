from datetime import UTC, date, datetime

from novelty_harness.domain.enums import PrecedentState
from novelty_harness.evidence.mapping.models import ComparisonDimension
from novelty_harness.evidence.passages.models import PassageLocator, PassageLocatorKind
from novelty_harness.evidence.precedent.models import (
    PatentScreeningDateRecord,
    PrecedentClassification,
)
from novelty_harness.evidence.precedent.patent import (
    PatentEvidenceEntry,
    patent_locator_from_passage,
    screen_patent_references,
)
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 28)
ORIGIN = phase5_provenance("patent-test")


def classification(
    source_id: str,
    relation: PrecedentState,
    *,
    decisive: bool = False,
    covered_elements: tuple[str, ...] = ("sensor",),
    covered_relationships: tuple[str, ...] = ("sensor controls relay",),
) -> PrecedentClassification:
    values: dict[str, object] = {
        "classification_id": "cls_" + source_id,
        "source_id": source_id,
        "mcu_id": "mcu_1",
        "mapping_id": "map_" + source_id,
        "verification_id": "ver_" + source_id,
        "relation": relation,
        "decisive": decisive,
        "basis": ("patent screening fixture",),
        "covered_elements": covered_elements,
        "covered_relationships": covered_relationships,
        "classifier_version": "precedent-classifier-v1",
        "observed_at": NOW,
        "provenance": ORIGIN,
    }
    if relation == PrecedentState.STRONG_PARTIAL_PRECEDENT:
        values["missing_elements"] = ("relay",)
    elif relation == PrecedentState.COMPONENT_PRECEDENT_ONLY:
        values["covered_relationships"] = ()
        values["missing_relationships"] = ("sensor controls relay",)
        values["configuration_gap"] = "claim configuration not identified"
    elif relation == PrecedentState.ANALOGOUS_PRECEDENT:
        values["functional_similarity"] = (ComparisonDimension.PURPOSE,)
        values["covered_relationships"] = ()
        values["missing_relationships"] = ("sensor controls relay",)
    return PrecedentClassification.model_validate(values)


def entry(
    source_id: str,
    relation: PrecedentState = PrecedentState.STRONG_PARTIAL_PRECEDENT,
    *,
    decisive: bool = False,
    is_patent: bool = True,
    priority: date | None = date(2018, 1, 1),
    publication: date | None = date(2020, 1, 1),
    locators: tuple = (),
) -> PatentEvidenceEntry:
    return PatentEvidenceEntry(
        source_id=source_id,
        mcu_id="mcu_1",
        is_patent=is_patent,
        classification=classification(source_id, relation, decisive=decisive),
        priority_date=priority,
        publication_date=publication,
        locators=locators,
    )


def test_one_decisive_patent_is_single_reference_anticipation_like() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_a",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                locators=(
                    patent_locator_from_passage(
                        "src_patent_a",
                        "pass_claim",
                        PassageLocator(kind=PassageLocatorKind.SECTION, section="Claims 1-5"),
                    ),
                ),
            ),
            entry("src_patent_b", PrecedentState.COMPONENT_PRECEDENT_ONLY),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "SINGLE_REFERENCE_ANTICIPATION_LIKE"
    assert result.single_reference_id == "src_patent_a"
    assert result.reference_source_ids == ("src_patent_a",)
    assert result.missing_elements == () and result.missing_relationships == ()
    assert result.locators[0].section == "CLAIMS"
    assert result.dates[0].priority_date == date(2018, 1, 1)
    assert result.dates[0].publication_date == date(2020, 1, 1)
    assert result.disclaimer == "patent-screening-not-legal-advice-v1"


def test_two_partial_patents_stay_multi_reference_combination_context() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry("src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT),
            entry("src_patent_b", PrecedentState.COMPONENT_PRECEDENT_ONLY),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "MULTI_REFERENCE_COMBINATION_LIKE"
    assert result.single_reference_id is None
    assert set(result.reference_source_ids) == {"src_patent_a", "src_patent_b"}
    assert any("never one-reference anticipation" in item for item in result.limitations)
    assert result.missing_elements or result.missing_relationships


def test_two_stitched_patents_never_become_anticipation() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry("src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT),
            entry("src_patent_b", PrecedentState.STRONG_PARTIAL_PRECEDENT),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "MULTI_REFERENCE_COMBINATION_LIKE"
    assert result.single_reference_id is None


def test_single_partial_patent_is_limited_not_anticipation() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(entry("src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT),),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert result.single_reference_id is None


def test_no_patent_evidence_is_limited_not_absence() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_paper",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                is_patent=False,
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert any("not a finding of absence" in item for item in result.limitations)
    empty = screen_patent_references(
        mcu_id="mcu_1", entries=(), as_of=AS_OF, observed_at=NOW, clock=lambda: NOW
    )
    assert empty.mode == "UNASSESSABLE"
    assert any("not a finding of absence" in item for item in empty.limitations)


def test_earliest_decisive_patent_is_chosen_deterministically() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_late",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                priority=date(2019, 1, 1),
                publication=date(2021, 1, 1),
            ),
            entry(
                "src_patent_early",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                priority=date(2017, 1, 1),
                publication=date(2019, 1, 1),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.single_reference_id == "src_patent_early"
    repeat = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_early",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                priority=date(2017, 1, 1),
                publication=date(2019, 1, 1),
            ),
            entry(
                "src_patent_late",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                priority=date(2019, 1, 1),
                publication=date(2021, 1, 1),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert repeat.screening_id == result.screening_id


def test_locator_classification_retains_claims_and_specification() -> None:
    claims = patent_locator_from_passage(
        "src_patent_a",
        "pass_1",
        PassageLocator(kind=PassageLocatorKind.SECTION, section="CLAIMS 1-4"),
    )
    specification = patent_locator_from_passage(
        "src_patent_a",
        "pass_2",
        PassageLocator(kind=PassageLocatorKind.BLOCK, label="Description paragraph 12"),
    )
    other = patent_locator_from_passage(
        "src_patent_a",
        "pass_3",
        PassageLocator(kind=PassageLocatorKind.RESOLVED_CONTENT),
    )
    assert claims.section == "CLAIMS"
    assert specification.section == "SPECIFICATION"
    assert other.section == "OTHER"


def test_date_records_keep_priority_and_publication_separate() -> None:
    record = PatentScreeningDateRecord(
        source_id="src_patent_a",
        priority_date=date(2018, 1, 1),
        publication_date=date(2020, 1, 1),
    )
    assert record.priority_date != record.publication_date

from datetime import UTC, date, datetime

import pytest

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
from novelty_harness.evidence.verification.models import ChronologyAssessment
from tests.fixtures.phase5 import phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 28)
ORIGIN = phase5_provenance("patent-test")


def classification(
    source_id: str,
    relation: PrecedentState,
    *,
    decisive: bool = False,
    source_version_id: str | None = None,
    covered_elements: tuple[str, ...] = ("sensor",),
    covered_relationships: tuple[str, ...] = ("sensor controls relay",),
) -> PrecedentClassification:
    values: dict[str, object] = {
        "classification_id": "cls_" + source_id,
        "source_id": source_id,
        "source_version_id": source_version_id,
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
    source_version_id: str | None = None,
    chronology: ChronologyAssessment | None = None,
    locators: tuple = (),
    authenticated: bool = True,
) -> PatentEvidenceEntry:
    if authenticated:
        from novelty_harness.domain.enums import SupportVerificationState
        from novelty_harness.domain.evidence import SourceDates
        from novelty_harness.evidence.context.selection import SupportEvidenceBundle
        from novelty_harness.evidence.normalization.models import SourceType
        from novelty_harness.evidence.passages.extraction import (
            extract_resolved_content,
            resolve_version_content,
        )
        from novelty_harness.evidence.passages.hashing import text_hash
        from novelty_harness.evidence.precedent.gates import (
            ClassifiedComparison,
            classify_verified_comparison,
        )
        from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
        from novelty_harness.evidence.verification.integrity import (
            VerifiedEvidenceChain,
            verified_comparison,
        )
        from tests.fixtures.phase5 import make_source, make_version
        from tests.unit.evidence.verification.test_eligibility import (
            PASSAGE_TEXT,
        )
        from tests.unit.evidence.verification.test_eligibility import (
            bundle as eligibility_bundle,
        )
        from tests.unit.evidence.verification.test_eligibility import (
            mapping as eligibility_mapping,
        )
        from tests.unit.evidence.verification.test_eligibility import (
            proposition as eligibility_proposition,
        )
        from tests.unit.evidence.verification.test_eligibility import (
            verification as eligibility_verification,
        )

        record = make_source(
            source_id,
            source_type=SourceType.PATENT if is_patent else SourceType.PAPER,
            content_hash=text_hash(PASSAGE_TEXT),
            dates=SourceDates(
                patent_priority_date=priority,
                patent_publication_date=publication,
                publication_date=publication,
            ),
        )
        cited_date = chronology.decisive_date if chronology is not None else None
        version = (
            make_version(
                source_id,
                version_id=source_version_id,
                content_hash=text_hash(PASSAGE_TEXT),
                published_date=cited_date,
            )
            if source_version_id is not None
            else None
        )
        resolved = resolve_version_content(
            source=record,
            version=version,
            text=PASSAGE_TEXT,
        )
        passage = extract_resolved_content(
            resolved,
            observed_at=NOW,
            provenance=ORIGIN,
        ).model_copy(update={"passage_id": "pass_1"})
        base_bundle = eligibility_bundle()
        claim = base_bundle.claim.model_copy(
            update={
                "source_id": source_id,
                "source_version_id": source_version_id,
            }
        )
        evidence_bundle = SupportEvidenceBundle(claim=claim, passages=(passage,))
        mapped = eligibility_mapping().model_copy(
            update={
                "source_id": source_id,
                "source_version_id": source_version_id,
            }
        )
        support_state = (
            SupportVerificationState.SUPPORTED
            if decisive
            else SupportVerificationState.PARTIALLY_SUPPORTED
        )
        verified = eligibility_verification(support_state).model_copy(
            update={
                "source_id": source_id,
                "source_version_id": source_version_id,
            }
        )
        cutoff = chronology.as_of if chronology is not None else AS_OF
        edge = build_verified_evidence_edge(
            mapping=mapped,
            verification=verified,
            proposition=eligibility_proposition(),
            source=record,
            bundle=evidence_bundle,
            version=version,
            as_of=cutoff,
            observed_at=NOW,
            assessment_id="asm_" + source_id,
        )
        chain = VerifiedEvidenceChain(
            assessment_id="asm_" + source_id,
            source=record,
            version=version,
            proposition=eligibility_proposition(),
            mapping=mapped,
            bundle=evidence_bundle,
            verification=verified,
            edge=edge,
        )
        comparison = verified_comparison(chain)
        classified = ClassifiedComparison(
            comparison=comparison,
            classification=classify_verified_comparison(comparison, clock=lambda: NOW),
        )
        return PatentEvidenceEntry(
            source_id=source_id,
            source_version_id=source_version_id,
            mcu_id="mcu_1",
            is_patent=is_patent,
            classification=classified.classification,
            priority_date=priority,
            publication_date=publication,
            chronology=edge.chronology,
            comparison=classified,
            locators=locators,
        )
    values: dict[str, object] = {
        "source_id": source_id,
        "source_version_id": source_version_id,
        "mcu_id": "mcu_1",
        "is_patent": is_patent,
        "classification": classification(
            source_id, relation, decisive=decisive, source_version_id=source_version_id
        ),
        "priority_date": priority,
        "publication_date": publication,
        "locators": locators,
    }
    if chronology is not None:
        values["chronology"] = chronology
    return PatentEvidenceEntry.model_validate(values)


def cited_chronology(
    published: date | None,
    *,
    as_of: date = AS_OF,
) -> ChronologyAssessment:
    if published is None:
        return ChronologyAssessment(as_of=as_of, state="UNCERTAIN")
    return ChronologyAssessment(
        as_of=as_of,
        state="PREDATES_CUTOFF" if published <= as_of else "POST_CUTOFF",
        decisive_date_field="version_published_date",
        decisive_date=published,
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


def test_post_cutoff_revisions_of_old_patents_cannot_form_combination_context() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_a",
                source_version_id="srcv_patent_a_revision",
                chronology=cited_chronology(date(2027, 1, 1)),
            ),
            entry(
                "src_patent_b",
                source_version_id="srcv_patent_b_revision",
                chronology=cited_chronology(date(2027, 2, 1)),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert result.reference_source_ids == ()
    assert result.single_reference_id is None
    assert any("post-cutoff" in limitation for limitation in result.limitations)


def test_one_eligible_and_one_future_partial_version_is_not_multi_reference() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_a",
                source_version_id="srcv_patent_a_old",
                chronology=cited_chronology(date(2020, 1, 1)),
            ),
            entry(
                "src_patent_b",
                source_version_id="srcv_patent_b_new",
                chronology=cited_chronology(date(2027, 1, 1)),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert result.reference_source_ids == ("src_patent_a",)


def test_two_eligible_cited_versions_need_distinct_lineage_roots() -> None:
    entries = (
        entry(
            "src_patent_a",
            source_version_id="srcv_patent_a_old",
            chronology=cited_chronology(date(2020, 1, 1)),
        ),
        entry(
            "src_patent_b",
            source_version_id="srcv_patent_b_old",
            chronology=cited_chronology(date(2021, 1, 1)),
        ),
    )
    independent = screen_patent_references(
        mcu_id="mcu_1",
        entries=entries,
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert independent.mode == "MULTI_REFERENCE_COMBINATION_LIKE"
    assert independent.single_reference_id is None
    same_family = screen_patent_references(
        mcu_id="mcu_1",
        entries=entries,
        as_of=AS_OF,
        observed_at=NOW,
        independent_root_of={"src_patent_b": "src_patent_a"},
        clock=lambda: NOW,
    )
    assert same_family.mode == "LIMITED"
    assert same_family.single_reference_id is None


def test_eligible_direct_version_wins_over_unrelated_partial_references() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_direct",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                source_version_id="srcv_patent_direct_old",
                chronology=cited_chronology(date(2020, 1, 1)),
            ),
            entry("src_patent_partial"),
            entry(
                "src_patent_future",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                source_version_id="srcv_patent_future_new",
                chronology=cited_chronology(date(2027, 1, 1)),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "SINGLE_REFERENCE_ANTICIPATION_LIKE"
    assert result.reference_source_ids == ("src_patent_direct",)
    assert result.single_reference_id == "src_patent_direct"


def test_cited_version_date_controls_when_parent_date_is_later() -> None:
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(
            entry(
                "src_patent_old_version",
                PrecedentState.DIRECT_PRECEDENT,
                decisive=True,
                publication=date(2027, 1, 1),
                source_version_id="srcv_patent_old_version",
                chronology=cited_chronology(date(2020, 1, 1)),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "SINGLE_REFERENCE_ANTICIPATION_LIKE"
    assert result.dates[0].publication_date == date(2020, 1, 1)


def test_missing_or_unknown_cited_version_chronology_cannot_inherit_parent_date() -> None:
    for version_chronology in (None, cited_chronology(None)):
        result = screen_patent_references(
            mcu_id="mcu_1",
            entries=(
                entry(
                    "src_patent_a",
                    source_version_id="srcv_patent_a",
                    chronology=version_chronology,
                ),
                entry("src_patent_b"),
            ),
            as_of=AS_OF,
            observed_at=NOW,
            clock=lambda: NOW,
        )
        assert result.mode == "LIMITED"
        assert result.reference_source_ids == ("src_patent_b",)
        assert any("unknown" in limitation for limitation in result.limitations)


def test_cited_chronology_must_use_screening_cutoff() -> None:
    with pytest.raises(ValueError, match="cutoff"):
        screen_patent_references(
            mcu_id="mcu_1",
            entries=(
                entry(
                    "src_patent_a",
                    source_version_id="srcv_patent_a",
                    chronology=cited_chronology(date(2020, 1, 1), as_of=date(2024, 1, 1)),
                ),
            ),
            as_of=AS_OF,
            observed_at=NOW,
            clock=lambda: NOW,
        )


def test_versioned_entry_rejects_parent_only_chronology() -> None:
    parent_chronology = ChronologyAssessment(
        as_of=AS_OF,
        state="PREDATES_CUTOFF",
        decisive_date_field="patent_publication_date",
        decisive_date=date(2020, 1, 1),
    )
    with pytest.raises(ValueError, match="cited version"):
        entry(
            "src_patent_a",
            source_version_id="srcv_patent_a_new",
            chronology=parent_chronology,
            authenticated=False,
        )


def test_cited_version_patent_entry_has_versioned_contract() -> None:
    assert entry("src_patent_a").contract_kind == "patent-evidence-entry-v2"

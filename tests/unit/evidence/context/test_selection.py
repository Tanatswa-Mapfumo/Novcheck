from datetime import UTC, datetime

from novelty_harness.domain.mcu import MCU, MCUFeature, MCURelationship
from novelty_harness.evidence.context.selection import (
    PassageSelectionError,
    select_support_passages,
)
from novelty_harness.evidence.mapping.dimensions import (
    build_mcu_comparison_profile,
    build_proposition,
)
from novelty_harness.evidence.mapping.mapper import build_mapping
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    DirectedRelationship,
)
from novelty_harness.evidence.mapping.prompts import (
    MAPPER_PROMPT_VERSION,
    MapperDimensionResult,
    MapperProposal,
    MapperStatement,
)
from novelty_harness.evidence.passages.models import PassageLocator, PassageLocatorKind
from tests.fixtures.phase5 import make_passage, make_source, make_version, phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("selection-test")


def proposition():
    mcu = MCU(
        mcu_id="mcu_control",
        label="Sensor control",
        statement="A sensor controls a relay",
        mechanism="threshold drives a relay coil",
        features=(MCUFeature(feature_id="F1", concept="sensor"),),
        relationships=(MCURelationship(subject="sensor", relation="controls", object="relay"),),
        provenance=ORIGIN,
    )
    return build_proposition(build_mcu_comparison_profile(mcu))


def statement(text: str, passage_id: str, relationship=None) -> MapperStatement:
    values: dict[str, object] = {"statement": text, "passage_ids": (passage_id,)}
    if relationship is not None:
        values["relationship"] = relationship
    return MapperStatement.model_validate(values)


def make_mapping(*, source_id: str = "src_1", passage_id: str = "pass_1", dimension=None):
    dims = dimension or (
        MapperDimensionResult(
            dimension=ComparisonDimension.MECHANISM,
            matching=(statement("threshold drives a coil", passage_id),),
        ),
        MapperDimensionResult(
            dimension=ComparisonDimension.RELATIONSHIPS,
            matching=(
                statement(
                    "sensor controls relay",
                    passage_id,
                    relationship=DirectedRelationship(
                        subject="sensor", relation="controls", object="relay"
                    ),
                ),
            ),
        ),
    )
    return build_mapping(
        source=make_source(source_id),
        version=make_version(source_id),
        proposition=proposition(),
        passages=(
            make_passage(
                source_id,
                text="A threshold drives a coil.",
                passage_id=passage_id,
                source_version_id=make_version(source_id).version_id,
            ),
        ),
        proposal=MapperProposal(prompt_version=MAPPER_PROMPT_VERSION, dimensions=tuple(dims)),
        observed_at=NOW,
    )


def test_selection_uses_only_exact_mapped_passages() -> None:
    source = make_source("src_1")
    version = make_version("src_1")
    mapped = make_passage(
        "src_1",
        text="A threshold drives a coil.",
        passage_id="pass_1",
        source_version_id="srcv_1_v1",
    )
    noise = make_passage(
        "src_1",
        text="Unrelated marketing text.",
        passage_id="pass_2",
        source_version_id="srcv_1_v1",
    )
    mapping = make_mapping()
    bundle = select_support_passages(
        mapping=mapping,
        proposition=proposition(),
        source=source,
        version=version,
        passages=(mapped, noise),
    )
    assert [passage.passage_id for passage in bundle.passages] == ["pass_1"]
    assert bundle.claim.passage_ids == ("pass_1",)
    assert bundle.claim.claimed_dimensions == (
        ComparisonDimension.MECHANISM,
        ComparisonDimension.RELATIONSHIPS,
    )
    assert bundle.claim.relationship_claims[0].describe() == "sensor controls relay"


def test_selection_rejects_missing_passages_and_wrong_source_version() -> None:
    source = make_source("src_1")
    version = make_version("src_1")
    mapping = make_mapping()
    try:
        select_support_passages(
            mapping=mapping,
            proposition=proposition(),
            source=source,
            version=version,
            passages=(),
        )
    except PassageSelectionError as error:
        assert "pass_1" in str(error)
    else:
        raise AssertionError("missing passage must be rejected")

    other_version = make_version("src_1", version_id="srcv_other", version_label="v2")
    foreign_version_passage = make_passage(
        "src_1",
        text="A threshold drives a coil.",
        passage_id="pass_1",
        source_version_id="srcv_other",
    )
    try:
        select_support_passages(
            mapping=mapping,
            proposition=proposition(),
            source=source,
            version=version,
            passages=(foreign_version_passage,),
        )
    except PassageSelectionError:
        pass
    else:
        raise AssertionError("passage from another version must be rejected")
    assert other_version.version_id == "srcv_other"


def test_selection_requires_at_least_one_grounded_passage() -> None:
    mapping = make_mapping(
        dimension=(
            MapperDimensionResult(
                dimension=ComparisonDimension.MECHANISM,
                missing=("no mechanism stated",),
            ),
        )
    )
    try:
        select_support_passages(
            mapping=mapping,
            proposition=proposition(),
            source=make_source("src_1"),
            version=make_version("src_1"),
            passages=(),
        )
    except PassageSelectionError as error:
        assert "no exact passage" in str(error)
    else:
        raise AssertionError("mapping without passages must not produce a claim")


def test_abstract_only_selection_records_limitations() -> None:
    source = make_source("src_1", access_state="ABSTRACT_ONLY")
    mapping = make_mapping()
    abstract = make_passage(
        "src_1",
        text="Abstract: a threshold drives a coil, so the sensor controls a relay.",
        passage_id="pass_1",
        access_state="ABSTRACT_ONLY",
        source_version_id="srcv_1_v1",
        locator=PassageLocator(kind=PassageLocatorKind.ABSTRACT, label="Abstract"),
    )
    bundle = select_support_passages(
        mapping=mapping,
        proposition=proposition(),
        source=source,
        version=make_version("src_1", access_state="ABSTRACT_ONLY"),
        passages=(abstract,),
    )
    assert any("Abstract-only" in item for item in bundle.limitations)

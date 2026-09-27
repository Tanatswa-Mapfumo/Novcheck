import unicodedata
from datetime import UTC, date, datetime

from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.normalization.models import (
    SourceAccessState,
    VersionKind,
)
from novelty_harness.evidence.normalization.versions import (
    build_version_record,
    compare_versions,
    version_id_for,
)
from novelty_harness.evidence.passages.hashing import normalize_text, text_hash

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = ArtifactProvenance(kind="implemented", component="versions-test", detail="test")


def build(
    *,
    source_id: str = "src_source",
    content: str,
    kind: VersionKind = VersionKind.PREPRINT,
    label: str | None = None,
    published: date | None = None,
    observed_at: datetime = NOW,
):
    return build_version_record(
        source_id=source_id,
        content_hash=text_hash(content),
        access_state=SourceAccessState.FULL_TEXT,
        observed_at=observed_at,
        provenance=ORIGIN,
        version_kind=kind,
        version_label=label,
        published_date=published,
    )


def test_newline_and_unicode_normalization_is_stable_but_not_lossy() -> None:
    assert normalize_text("line one\r\nline two\rline three") == "line one\nline two\nline three"
    assert normalize_text("trailing   \nspaces\t\n") == "trailing\nspaces"
    assert normalize_text("\ufeffhello") == "hello"
    composed = unicodedata.normalize("NFC", "café")
    decomposed = unicodedata.normalize("NFD", "café")
    assert composed != decomposed
    assert text_hash(composed) == text_hash(decomposed)
    assert text_hash("interior  spaces") != text_hash("interior spaces")
    assert text_hash("Case") != text_hash("case")


def test_identical_normalized_text_yields_identical_version() -> None:
    first = build(content="Shared text\r\n")
    second = build(content="Shared text\n")
    assert first.content_hash == second.content_hash
    comparison = compare_versions((first,), second)
    assert comparison.relation == "SAME_CONTENT"
    assert comparison.predecessor_version_id == first.version_id


def test_changed_content_creates_a_new_version_not_an_overwrite() -> None:
    first = build(content="version one", published=date(2020, 1, 1))
    second = build(content="version two", published=date(2020, 6, 1))
    assert first.version_id != second.version_id
    assert first.content_hash != second.content_hash
    comparison = compare_versions((first,), second)
    assert comparison.relation == "CONTENT_CHANGED"
    assert comparison.predecessor_version_id == first.version_id
    assert comparison.chronology_certain
    third = compare_versions((first, second), second.model_copy(update={"version_id": "srcv_x"}))
    assert third.relation == "SAME_CONTENT"


def test_first_version_is_explicit() -> None:
    comparison = compare_versions((), build(content="first"))
    assert comparison.relation == "FIRST_VERSION"
    assert comparison.predecessor_version_id is None
    assert comparison.chronology_certain


def test_arxiv_versions_are_linked_not_independent_evidence() -> None:
    v1 = build(content="draft", kind=VersionKind.PREPRINT, label="v1", published=date(2020, 1, 1))
    v3 = build(
        content="revised draft", kind=VersionKind.PREPRINT, label="v3", published=date(2020, 3, 1)
    )
    assert v1.source_id == v3.source_id
    assert v1.version_label == "v1" and v3.version_label == "v3"
    comparison = compare_versions((v1,), v3)
    assert comparison.relation == "CONTENT_CHANGED"
    assert comparison.predecessor_version_id == v1.version_id


def test_preprint_to_journal_is_a_version_aware_change() -> None:
    preprint = build(
        content="preprint body",
        kind=VersionKind.PREPRINT,
        label="preprint",
        published=date(2020, 1, 1),
    )
    journal = build(
        content="journal body with revisions",
        kind=VersionKind.JOURNAL,
        label="journal",
        published=date(2021, 2, 2),
    )
    comparison = compare_versions((preprint,), journal)
    assert comparison.relation == "CONTENT_CHANGED"
    assert comparison.predecessor_version_id == preprint.version_id
    assert comparison.chronology_certain


def test_repository_releases_are_versioned() -> None:
    release_one = build(
        content="def main(): pass",
        kind=VersionKind.REPOSITORY_RELEASE,
        label="v1.0",
        published=date(2019, 1, 1),
    )
    release_two = build(
        content="def main(): return 1",
        kind=VersionKind.REPOSITORY_RELEASE,
        label="v2.0",
        published=date(2019, 8, 1),
    )
    comparison = compare_versions((release_one,), release_two)
    assert comparison.predecessor_version_id == release_one.version_id
    assert comparison.chronology_certain


def test_missing_or_tied_chronology_stays_uncertain() -> None:
    undated = build(content="a")
    comparison = compare_versions((undated,), build(content="b"))
    assert comparison.relation == "CONTENT_CHANGED"
    assert not comparison.chronology_certain
    assert any("publication date" in item for item in comparison.rationale)

    tied_first = build(content="a", published=date(2020, 1, 1))
    tied_second = build(content="b", published=date(2020, 1, 1))
    comparison = compare_versions(
        (tied_first, tied_second), build(content="c", published=date(2021, 1, 1))
    )
    assert not comparison.chronology_certain
    assert any("share the latest publication date" in item for item in comparison.rationale)

    older_candidate = build(content="c", published=date(2018, 1, 1))
    comparison = compare_versions(
        (build(content="a", published=date(2020, 1, 1)),), older_candidate
    )
    assert not comparison.chronology_certain
    assert any("precedes an existing version" in item for item in comparison.rationale)


def test_hash_equality_across_distinct_sources_does_not_merge_them() -> None:
    left = build(source_id="src_left", content="identical words")
    right = build(source_id="src_right", content="identical words")
    assert left.content_hash == right.content_hash
    assert left.version_id != right.version_id
    assert version_id_for("src_left", "preprint", left.content_hash) == left.version_id

"""Citations preserve native ancestry and never certify an assertion's meaning."""

import pytest

from novelty_harness.reporting.models import ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


@pytest.fixture(scope="module")
def citation_sections(report_case, compilation):
    from tests.unit.reporting.test_fallback import sections_for

    return sections_for(report_case.bundle, compilation)


def test_citations_bind_exact_claim_source_version_passage_and_commitment(
    report_case, citation_sections
):
    from novelty_harness.reporting.citations import (
        build_citation_registry,
        validate_citation_registry,
    )

    bundle = report_case.bundle
    registry = build_citation_registry(citation_sections, bundle)
    assert registry.citations
    validate_citation_registry(registry, citation_sections, bundle)
    for citation in registry.citations:
        comparison = next(
            c
            for c in bundle.eligible_comparisons
            if c.comparison.classification.classification_id == citation.comparison_id
        )
        chain = comparison.comparison.comparison.chain
        cited = next(
            p for p in comparison.cited_passages if p.passage.passage_id == citation.passage_id
        )
        assert citation.source_id == chain.source.source_id
        assert citation.source_version_id == (chain.version.version_id if chain.version else None)
        assert citation.locator == cited.passage.locator
        assert citation.commit_id == comparison.commit_id
        assert citation.commitment_ids == tuple(sorted(cited.commitment_ids))
        assert citation.source_metadata.source == chain.source
        assert citation.source_metadata.version == chain.version
        assert citation.as_of == bundle.as_of
        assert citation.claim_ids
        assert any(
            r.kind == "PASSAGE" and r.native_id == citation.passage_id for r in citation.basis_refs
        )
        for claim_id in citation.claim_ids:
            assert any(link.claim_id == claim_id for link in registry.claim_basis_links)
    assert not hasattr(registry, "supported") and not hasattr(registry, "accepted")


@pytest.mark.parametrize("field", ["title", "version", "locator"])
def test_wrong_title_version_or_locator_cannot_rescue_claim(report_case, citation_sections, field):
    from novelty_harness.reporting.citations import (
        build_citation_registry,
        report_citation_id,
        validate_citation_registry,
    )

    registry = build_citation_registry(citation_sections, report_case.bundle)
    citation = registry.citations[0]
    if field == "title":
        source = citation.source_metadata.source.model_copy(
            update={"canonical_title": "A plausible different title"}
        )
        changed = citation.model_copy(
            update={
                "source_metadata": citation.source_metadata.model_copy(update={"source": source})
            }
        )
    elif field == "version":
        changed = citation.model_copy(update={"source_version_id": "sourceversion_foreign"})
    else:
        changed = citation.model_copy(
            update={"locator": citation.locator.model_copy(update={"label": "Another section"})}
        )
    changed = changed.model_copy(update={"citation_id": report_citation_id(changed)})
    with pytest.raises(ReportProposalError):
        validate_citation_registry(
            registry.model_copy(update={"citations": (changed, *registry.citations[1:])}),
            citation_sections,
            report_case.bundle,
        )


def test_citation_numbers_do_not_depend_on_prose_order(report_case, citation_sections):
    from novelty_harness.reporting.citations import build_citation_registry

    first = build_citation_registry(citation_sections, report_case.bundle)
    reordered = tuple(
        s.model_copy(
            update={
                "draft": s.draft.model_copy(update={"blocks": tuple(reversed(s.draft.blocks))}),
                "claims": tuple(reversed(s.claims)),
                "basis_links": tuple(reversed(s.basis_links)),
            }
        )
        for s in reversed(citation_sections)
    )
    second = build_citation_registry(reordered, report_case.bundle)
    assert first.citations == second.citations
    assert tuple(c.display_number for c in first.citations) == tuple(
        range(1, len(first.citations) + 1)
    )


def test_unknown_identifier_and_unsafe_scheme_render_plain_text(report_case, citation_sections):
    from novelty_harness.evidence.normalization.models import CanonicalIdentifiers
    from novelty_harness.reporting.citations import build_citation_registry, resolve_citation_link

    citation = build_citation_registry(citation_sections, report_case.bundle).citations[0]
    for url in (
        None,
        "javascript:alert(1)",
        "data:text/html,bad",
        "https://user:secret@example.org/x",
        "https://example.org/\nunsafe",
    ):
        source = citation.source_metadata.source.model_copy(
            update={
                "canonical_url": url,
                "identifiers": CanonicalIdentifiers(other={"unknown": "plain-recorded-identifier"}),
            }
        )
        version = citation.source_metadata.version
        if version:
            version = version.model_copy(update={"identifiers": CanonicalIdentifiers()})
        changed = citation.model_copy(
            update={
                "source_metadata": citation.source_metadata.model_copy(
                    update={"source": source, "version": version}
                )
            }
        )
        assert resolve_citation_link(changed) is None
        assert (
            changed.source_metadata.source.identifiers.other["unknown"]
            == "plain-recorded-identifier"
        )


def test_stored_doi_uses_pinned_encoded_resolver(report_case, citation_sections):
    from novelty_harness.evidence.normalization.models import CanonicalIdentifiers
    from novelty_harness.reporting.citations import build_citation_registry, resolve_citation_link

    citation = build_citation_registry(citation_sections, report_case.bundle).citations[0]
    source = citation.source_metadata.source.model_copy(
        update={
            "canonical_url": None,
            "identifiers": CanonicalIdentifiers(doi="10.1234/a(b)?x#fragment"),
        }
    )
    version = citation.source_metadata.version
    if version:
        version = version.model_copy(update={"identifiers": CanonicalIdentifiers()})
    changed = citation.model_copy(
        update={
            "source_metadata": citation.source_metadata.model_copy(
                update={"source": source, "version": version}
            )
        }
    )
    assert resolve_citation_link(changed) == "https://doi.org/10.1234/a%28b%29%3Fx%23fragment"


def test_related_versions_do_not_become_independent_evidence(report_case, citation_sections):
    from novelty_harness.reporting.citations import build_citation_registry, report_citation_id

    registry = build_citation_registry(citation_sections, report_case.bundle)
    citation = registry.citations[0]
    # Pure identity variant; this caller shape is not repository evidence.
    related = citation.model_copy(update={"source_version_id": "sourceversion_related"})
    assert related.source_id == citation.source_id
    assert report_citation_id(related) != citation.citation_id
    assert len({c.citation_id for c in registry.citations}) == len(registry.citations)
    # Repeated citation of the same source/version keeps its native ancestry;
    # registry carries no independent-evidence count or novelty conclusion.
    assert not hasattr(registry, "independent_evidence_count")
    assert not hasattr(registry, "novelty_score")
    for citation in registry.citations:
        assert citation.source_metadata.source.source_id == citation.source_id
        if citation.source_metadata.version:
            assert citation.source_metadata.version.source_id == citation.source_id


def test_source_url_not_in_draft_cannot_be_fabricated(report_case, citation_sections):
    from novelty_harness.reporting.citations import (
        build_citation_registry,
        validate_citation_registry,
    )

    registry = build_citation_registry(citation_sections, report_case.bundle)
    changed = registry.citations[0].model_copy(
        update={"external_link": "https://invented.example/source"}
    )
    with pytest.raises(ReportProposalError):
        validate_citation_registry(
            registry.model_copy(update={"citations": (changed, *registry.citations[1:])}),
            citation_sections,
            report_case.bundle,
        )


def test_same_source_wrong_proposition_is_not_supported(report_case, citation_sections):
    from novelty_harness.reporting.citations import (
        build_citation_registry,
        validate_citation_registry,
    )
    from novelty_harness.reporting.claims import report_claim_id

    registry = build_citation_registry(citation_sections, report_case.bundle)
    section = citation_sections[1]
    victim = next(c for c in section.claims if c.citation_candidates)
    changed = victim.model_copy(
        update={"normalized_assertion": "This source establishes all components in combination"}
    )
    changed = changed.model_copy(update={"claim_id": report_claim_id(changed)})
    replacement = section.model_copy(
        update={
            "claims": tuple(changed if c == victim else c for c in section.claims),
            "basis_links": tuple(
                link.model_copy(
                    update={
                        "claim_id": changed.claim_id,
                        "proposition": changed.normalized_assertion,
                    }
                )
                if link.claim_id == victim.claim_id
                else link
                for link in section.basis_links
            ),
        }
    )
    with pytest.raises(ReportProposalError):
        validate_citation_registry(
            registry,
            (citation_sections[0], replacement, *citation_sections[2:]),
            report_case.bundle,
        )


def test_internal_input_gate_gap_recommendation_refs_need_no_fake_external_cite(
    report_case, citation_sections
):
    from novelty_harness.reporting.citations import build_citation_registry

    registry = build_citation_registry(
        (citation_sections[0], citation_sections[6]), report_case.bundle
    )
    assert not registry.citations
    assert registry.claim_basis_links
    assert any(link.authority_ref.kind == "CIR" for link in registry.claim_basis_links)


def test_metadata_only_basis_cannot_create_passage_citation(report_case, citation_sections):
    from novelty_harness.reporting.citations import build_citation_registry

    section = citation_sections[1]
    metadata_ref = report_case.bundle.source_metadata[0].source_ref
    claim = next(c for c in section.claims if c.citation_candidates)
    changed = claim.model_copy(update={"citation_candidates": (metadata_ref,)})
    from novelty_harness.reporting.claims import report_claim_id

    changed = changed.model_copy(update={"claim_id": report_claim_id(changed)})
    section = section.model_copy(
        update={
            "claims": tuple(changed if c == claim else c for c in section.claims),
            "basis_links": tuple(
                link.model_copy(update={"claim_id": changed.claim_id})
                if link.claim_id == claim.claim_id
                else link
                for link in section.basis_links
            ),
        }
    )
    with pytest.raises(ReportProposalError, match="metadata or foreign"):
        build_citation_registry((section,), report_case.bundle)


def test_citation_observations_are_separate_from_publication_and_identity(
    report_case, citation_sections
):
    from datetime import UTC, datetime

    from novelty_harness.reporting.citations import build_citation_registry, report_citation_id

    registry = build_citation_registry(citation_sections, report_case.bundle)
    for citation in registry.citations:
        comparison = next(
            c
            for c in report_case.bundle.eligible_comparisons
            if c.comparison.classification.classification_id == citation.comparison_id
        )
        passage = next(
            p.passage
            for p in comparison.cited_passages
            if p.passage.passage_id == citation.passage_id
        )
        assert citation.retrieved_at == (
            passage.attestation.parent.retrieved_at if passage.attestation else None
        )
        assert (
            citation.source_metadata.source.dates
            == comparison.comparison.comparison.chain.source.dates
        )
        if citation.source_metadata.version:
            assert (
                citation.source_metadata.version.published_date
                == comparison.comparison.comparison.chain.version.published_date
            )
        assert citation.canonical_page_is_versionless == (
            citation.source_metadata.source.canonical_url is not None
        )
        changed = citation.model_copy(update={"retrieved_at": datetime(2040, 1, 1, tzinfo=UTC)})
        assert report_citation_id(changed) == citation.citation_id

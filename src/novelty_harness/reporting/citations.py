"""Deterministic passage ancestry and inert links; citations do not prove meaning."""

from datetime import date
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import Field, JsonValue

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.ids import ClassificationId, PassageId, SourceId, SourceVersionId
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages.models import PassageLocator
from novelty_harness.reporting.bundle import ReportInputBundle, SourceMetadataObservation
from novelty_harness.reporting.claims import ClaimBasisLink, validate_claim_extraction
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    NonBlank,
    ReportProposalError,
    ReportScoped,
)
from novelty_harness.reporting.verification import VerifiedSection, section_extraction
from novelty_harness.runtime.tracing.hashing import canonical_hash


class ReportCitation(ReportScoped):
    contract_kind: Literal["phase8-report-citation-v1"] = "phase8-report-citation-v1"
    citation_id: NonBlank
    display_number: int = Field(ge=1, strict=True)
    source_id: SourceId
    source_version_id: SourceVersionId | None
    passage_id: PassageId
    locator: PassageLocator
    comparison_id: ClassificationId
    commit_id: NonBlank
    commitment_ids: tuple[NonBlank, ...] = Field(min_length=1)
    source_metadata: SourceMetadataObservation
    claim_ids: tuple[NonBlank, ...] = Field(min_length=1)
    basis_refs: tuple[AuthorityRef, ...]
    as_of: date
    retrieved_at: UTCDateTime | None
    passage_access_state: SourceAccessState
    limitations: tuple[str, ...]
    external_link: str | None
    canonical_page_is_versionless: bool
    unversioned_authority: bool


class CitationRegistry(ReportScoped):
    contract_kind: Literal["phase8-citation-registry-v1"] = "phase8-citation-registry-v1"
    method_version: Literal["p8-citations-v1"] = "p8-citations-v1"
    citations: tuple[ReportCitation, ...]
    claim_basis_links: tuple[ClaimBasisLink, ...]


def report_citation_id(citation: ReportCitation) -> str:
    """Native supporting identity, independent of prose, numbering and observations."""
    payload: dict[str, JsonValue] = {
        "source_id": citation.source_id,
        "source_version_id": citation.source_version_id,
        "passage_id": citation.passage_id,
        "locator": citation.locator.model_dump(mode="json"),
        "comparison_id": citation.comparison_id,
        "commit_id": citation.commit_id,
        "commitment_ids": list(citation.commitment_ids),
    }
    return "p8cite_" + canonical_hash(payload)


def _safe_url(value: str | None) -> str | None:
    if value is None or any(ord(char) < 33 or ord(char) == 127 for char in value):
        return None
    if "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme.lower() not in {"https", "http"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            return None
        # Reading the port rejects malformed bracket/port syntax without fetching.
        _ = parts.port
    except ValueError:
        return None
    return quote(value, safe="%:/?&=+#@!$,;~.-_")


def resolve_citation_link(citation: ReportCitation) -> str | None:
    """Pinned resolver v1: an admitted canonical URL or a stored DOI, never a lookup."""
    metadata = citation.source_metadata
    canonical = _safe_url(metadata.source.canonical_url)
    if canonical is not None:
        return canonical
    doi = (
        metadata.version.identifiers.doi if metadata.version else None
    ) or metadata.source.identifiers.doi
    if (
        doi is not None
        and doi.startswith("10.")
        and "/" in doi
        and not any(ord(c) < 33 for c in doi)
    ):
        return "https://doi.org/" + quote(doi, safe="/.-_")
    return None


def build_citation_registry(
    sections: tuple[VerifiedSection, ...], bundle: ReportInputBundle
) -> CitationRegistry:
    if not sections:
        raise ReportProposalError("citations require actual public sections")
    run = sections[0].compilation_id
    eligible = tuple(
        d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None
    )
    links: list[ClaimBasisLink] = []
    records: dict[str, ReportCitation] = {}
    claim_ids: set[str] = set()
    for section in sections:
        if (
            section.scope,
            section.compilation_id,
            section.draft.scope,
            section.draft.compilation_id,
        ) != (bundle.scope, run, bundle.scope, run):
            raise ReportProposalError("citation section scope differs")
        extraction = validate_claim_extraction(section.draft, section_extraction(section))
        for link in extraction.basis_links:
            if link.authority_ref not in eligible:
                raise ReportProposalError("citation basis is not admitted")
            links.append(link)
        for claim in extraction.claims:
            if claim.claim_id in claim_ids:
                raise ReportProposalError("citation registry repeats an actual claim")
            claim_ids.add(claim.claim_id)
            bases = tuple(
                link.authority_ref
                for link in extraction.basis_links
                if link.claim_id == claim.claim_id
            )
            passages = tuple(
                dict.fromkeys(
                    (
                        *claim.citation_candidates,
                        *(r for r in bases if r.kind == AuthorityKind.PASSAGE),
                    )
                )
            )
            for ref in passages:
                if ref not in eligible or ref.kind != AuthorityKind.PASSAGE:
                    raise ReportProposalError(
                        "metadata or foreign reference cannot become passage support"
                    )
                matches = tuple(
                    (comparison, cited)
                    for comparison in bundle.eligible_comparisons
                    for cited in comparison.cited_passages
                    if ref.path
                    == (
                        "comparisons",
                        comparison.commit_id,
                        comparison.comparison.classification.classification_id,
                        "cited_passages",
                        cited.passage.passage_id,
                    )
                    and ref.native_id == cited.passage.passage_id
                    and ref.digest == canonical_hash(cited)
                )
                if len(matches) != 1:
                    raise ReportProposalError("citation lacks exact passage/comparison ancestry")
                comparison, cited = matches[0]
                chain = comparison.comparison.comparison.chain
                observations = tuple(
                    o
                    for o in bundle.source_metadata
                    if o.source == chain.source
                    and o.version == chain.version
                    and any(
                        r.native_id == comparison.comparison.classification.classification_id
                        and r.digest == canonical_hash(comparison)
                        for r in o.comparison_refs
                    )
                )
                if len(observations) != 1:
                    raise ReportProposalError(
                        "citation metadata does not match committed observation"
                    )
                metadata = observations[0]
                comparison_ref = next(
                    r
                    for r in metadata.comparison_refs
                    if r.native_id == comparison.comparison.classification.classification_id
                )
                commits = tuple(
                    r
                    for r in eligible
                    if r.kind == AuthorityKind.COMMIT
                    and r.native_id == comparison.commit_id
                    and r.digest == canonical_hash(comparison)
                )
                if len(commits) != 1 or not any(
                    r in (ref, comparison_ref, commits[0]) for r in bases
                ):
                    raise ReportProposalError(
                        "citation candidate has no exact claim-basis ancestry"
                    )
                passage = cited.passage
                if (passage.source_id, passage.source_version_id) != (
                    chain.source.source_id,
                    chain.version.version_id if chain.version else None,
                ) or ref.target != comparison_ref.target:
                    raise ReportProposalError("citation source/version or target differs")
                ancestry = (
                    ref,
                    comparison_ref,
                    commits[0],
                    metadata.source_ref,
                    *(() if metadata.version_ref is None else (metadata.version_ref,)),
                )
                if any(r not in eligible for r in ancestry):
                    raise ReportProposalError("citation omits admitted source/version ancestry")
                record = ReportCitation(
                    scope=bundle.scope,
                    compilation_id=run,
                    citation_id="pending",
                    display_number=1,
                    source_id=passage.source_id,
                    source_version_id=passage.source_version_id,
                    passage_id=passage.passage_id,
                    locator=passage.locator,
                    comparison_id=comparison_ref.native_id,
                    commit_id=comparison.commit_id,
                    commitment_ids=tuple(sorted(cited.commitment_ids)),
                    source_metadata=metadata,
                    claim_ids=(claim.claim_id,),
                    basis_refs=ancestry,
                    as_of=bundle.as_of,
                    retrieved_at=passage.attestation.parent.retrieved_at
                    if passage.attestation
                    else None,
                    passage_access_state=passage.access_state,
                    limitations=tuple(
                        dict.fromkeys(
                            (
                                *chain.source.limitations,
                                *(chain.version.limitations if chain.version else ()),
                                *passage.limitations,
                            )
                        )
                    ),
                    external_link=None,
                    canonical_page_is_versionless=_safe_url(chain.source.canonical_url) is not None,
                    unversioned_authority=passage.source_version_id is None,
                )
                record = record.model_copy(
                    update={
                        "citation_id": report_citation_id(record),
                        "external_link": resolve_citation_link(record),
                    }
                )
                previous = records.get(record.citation_id)
                if previous is not None:
                    if previous.model_dump(exclude={"claim_ids"}) != record.model_dump(
                        exclude={"claim_ids"}
                    ):
                        raise ReportProposalError(
                            "citation identity conflicts across metadata observations"
                        )
                    record = record.model_copy(
                        update={
                            "claim_ids": tuple(sorted(set((*previous.claim_ids, claim.claim_id))))
                        }
                    )
                records[record.citation_id] = record
        for block in section.draft.blocks:
            for token in block.citation_tokens:
                if not any(
                    c.block_id == block.block_id and token.authority_ref in c.citation_candidates
                    for c in extraction.claims
                ):
                    raise ReportProposalError("public citation token has no actual claim candidate")
    ordered = sorted(
        records.values(),
        key=lambda c: (
            c.source_id,
            c.source_version_id or "",
            c.passage_id,
            c.comparison_id,
            c.commit_id,
            c.commitment_ids,
        ),
    )
    return CitationRegistry(
        scope=bundle.scope,
        compilation_id=run,
        citations=tuple(
            c.model_copy(update={"display_number": number}) for number, c in enumerate(ordered, 1)
        ),
        claim_basis_links=tuple(
            sorted(links, key=lambda link: (link.claim_id, canonical_hash(link)))
        ),
    )


def validate_citation_registry(
    registry: CitationRegistry, sections: tuple[VerifiedSection, ...], bundle: ReportInputBundle
) -> None:
    try:
        registry = CitationRegistry.model_validate_json(registry.model_dump_json(), strict=True)
    except ValueError as error:
        raise ReportProposalError("citation registry fails serialized validation") from error
    if registry != build_citation_registry(sections, bundle):
        raise ReportProposalError("citation registry differs from exact accepted claim ancestry")

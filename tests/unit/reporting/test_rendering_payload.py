"""Exact structured rendition projection with bounded duplicate text retention."""

import gc
import json
import tracemalloc

from novelty_harness.runtime.tracing.hashing import canonical_json
from tests.unit.reporting.test_compiled_revalidation import proposed_report


def test_structured_rendition_payload_does_not_duplicate_complete_text(record_property):
    from novelty_harness.reporting.rendering import _rendition_payload

    report = proposed_report()
    wire = canonical_json(report)
    peaks, values = [], []
    for function in (lambda value, text: json.loads(text), _rendition_payload):
        gc.collect()
        tracemalloc.start()
        try:
            values.append(function(report, wire))
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("parsed_rendition_payload_peak_bytes", peaks[0])
    record_property("projected_rendition_payload_peak_bytes", peaks[1])
    assert canonical_json(values[0]) == canonical_json(values[1])
    assert peaks[1] < peaks[0] * 0.25, peaks


def test_structured_rendition_projection_preserves_yaml_bytes_and_private_containers():
    import yaml

    from novelty_harness.reporting.rendering import _rendition_payload

    report = proposed_report()
    wire = canonical_json(report)
    original = json.loads(wire)
    projected = _rendition_payload(report, wire)
    assert canonical_json(projected) == wire
    assert yaml.safe_dump(
        projected, allow_unicode=True, sort_keys=True, default_flow_style=False
    ) == yaml.safe_dump(original, allow_unicode=True, sort_keys=True, default_flow_style=False)
    projected["ir"]["sections"][0]["blocks"][0]["origin"] = "GENERATIVE_ACCEPTED"
    assert report.ir.sections[0].blocks[0].origin == "DETERMINISTIC_FALLBACK"
    assert canonical_json(report) == wire


def test_structured_projection_preserves_citation_dates_enums_and_sampling_floats():
    from datetime import UTC, date, datetime, timedelta, timezone

    import yaml

    from novelty_harness.domain.evidence import SourceDates
    from novelty_harness.domain.idea import ArtifactProvenance
    from novelty_harness.evidence.normalization.models import SourceRecord, SourceVersionRecord
    from novelty_harness.evidence.passages.models import PassageLocator
    from novelty_harness.reporting.bundle import SourceMetadataObservation
    from novelty_harness.reporting.citations import ReportCitation
    from novelty_harness.reporting.execution import ReportSamplingSettings
    from novelty_harness.reporting.rendering import _rendition_payload

    report = proposed_report()
    scope = report.scope
    provenance = ArtifactProvenance(
        kind="fixture", component="projection-control", detail="Shape only, no native authority"
    )
    observed = datetime(2026, 10, 6, 3, 0, tzinfo=timezone(timedelta(hours=3)))
    source = SourceRecord(
        source_id="src_projection",
        canonical_title='Dates é雪 and "quotes"',
        source_type="PAPER",
        access_state="METADATA_ONLY",
        dates=SourceDates(publication_date=date(2001, 2, 3)),
        provenance=provenance,
    )
    version = SourceVersionRecord(
        version_id="srcv_projection",
        source_id=source.source_id,
        version_label="v1",
        version_kind="JOURNAL",
        content_hash="shape-hash",
        access_state="METADATA_ONLY",
        published_date=date(2002, 3, 4),
        observed_at=observed,
        provenance=provenance,
    )
    source_ref = report.ir.claim_basis_links[0].authority_ref.model_copy(
        update={"kind": "SOURCE", "native_id": source.source_id}
    )
    version_ref = source_ref.model_copy(
        update={"kind": "SOURCE_VERSION", "native_id": version.version_id}
    )
    metadata = SourceMetadataObservation(
        scope=scope,
        source=source,
        version=version,
        source_ref=source_ref,
        version_ref=version_ref,
        comparison_refs=(),
    )
    citation = ReportCitation(
        scope=scope,
        compilation_id=report.compilation_id,
        citation_id="shape-citation",
        display_number=1,
        source_id=source.source_id,
        source_version_id=version.version_id,
        passage_id="pass_projection",
        locator=PassageLocator(kind="SECTION", section="Section 1"),
        comparison_id="cls_projection",
        commit_id="shape-commit",
        commitment_ids=("shape-commitment",),
        source_metadata=metadata,
        claim_ids=("shape-claim",),
        basis_refs=(source_ref, version_ref),
        as_of=date(2026, 10, 5),
        retrieved_at=observed,
        passage_access_state="METADATA_ONLY",
        limitations=("Shape only",),
        external_link=None,
        canonical_page_is_versionless=False,
        unversioned_authority=False,
    )
    registry = report.ir.citation_registry.model_copy(update={"citations": (citation,)})
    generation = report.ir.generation_provenance
    roles = tuple(
        role.model_copy(
            update={
                "port": role.port.model_copy(
                    update={
                        "sampling": ReportSamplingSettings(
                            temperature=-0.0, top_p=0.625, seed=-7, max_output_tokens=23
                        )
                    }
                )
            }
        )
        for role in generation.configuration.roles
    )
    generation = generation.model_copy(
        update={"configuration": generation.configuration.model_copy(update={"roles": roles})}
    )
    report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={"citation_registry": registry, "generation_provenance": generation}
            )
        }
    )
    wire = canonical_json(report)
    original, projected = json.loads(wire), _rendition_payload(report, wire)
    assert canonical_json(projected) == wire
    assert projected["ir"]["citation_registry"]["citations"][0]["retrieved_at"] == datetime(
        2026, 10, 6, tzinfo=UTC
    ).isoformat().replace("+00:00", "Z")
    assert yaml.safe_dump(
        projected, allow_unicode=True, sort_keys=True, default_flow_style=False
    ) == yaml.safe_dump(original, allow_unicode=True, sort_keys=True, default_flow_style=False)

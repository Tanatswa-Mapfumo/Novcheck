"""Mandatory content is derived from accepted records, never presentation limits."""

import pytest

from tests.fixtures.phase8 import make_report_case


@pytest.fixture(scope="module")
def report_case(tmp_path_factory):
    case = make_report_case(tmp_path_factory.mktemp("report-obligations"))
    try:
        yield case
    finally:
        case.repository.close()


def test_obligations_preserve_every_target_and_material_limit(report_case):
    bundle = report_case.bundle
    assert bundle.coverage_obligations, "mandatory coverage derivation is absent"
    targets = {f.target_id for f in bundle.target_findings}
    represented = {
        o.target.id
        for o in bundle.coverage_obligations
        if o.requirement_kind == "TARGET_REPRESENTATION"
    }
    assert targets == represented
    kinds = {o.requirement_kind for o in bundle.coverage_obligations}
    assert {
        "DECISIVE_PRECEDENT",
        "SCOPED_NEGATIVE",
        "LANGUAGE_CEILING",
        "ACTUAL_LIMITATION",
        "MISSING_ASSESSED_VALUE",
        "COVERAGE_STATE",
    } <= kinds
    from novelty_harness.reporting.uncertainty import project_uncertainty

    for item in project_uncertainty(bundle):
        matches = [
            o
            for o in bundle.coverage_obligations
            if set(item.authority_refs) <= set(o.authority_refs)
        ]
        assert matches, item
        if item.target is not None:
            assert any(9 in o.question_ids and any(q != 9 for q in o.question_ids) for o in matches)
    origins = {r.native_id for o in bundle.coverage_obligations for r in o.authority_refs}
    assert {g.gate_id for g in bundle.gate_findings} <= origins
    assert set(bundle.frozen_adjudication.judge_resolution_ids) <= origins
    decisive = {i for f in bundle.target_findings for i in f.decisive_phase6_ids}
    assert decisive <= origins
    catalog = {d.authority_ref for d in bundle.dependency_manifest}
    assert all(set(o.authority_refs) <= catalog for o in bundle.coverage_obligations)


def test_display_limit_cannot_drop_obligation(report_case):
    from novelty_harness.reporting.models import ReportGenerationLimits, ReportOptions
    from novelty_harness.reporting.obligations import derive_coverage_obligations

    options = ReportOptions(limits=ReportGenerationLimits(max_context_chars=0, max_calls=0))
    assert options.limits.max_calls == 0
    bundle = report_case.bundle
    assert derive_coverage_obligations(bundle) == bundle.coverage_obligations
    assert (
        derive_coverage_obligations(bundle.model_copy(update={"coverage_obligations": ()}))
        == bundle.coverage_obligations
    )


def test_overall_permission_union_does_not_authorize_each_target(report_case):
    from novelty_harness.reporting.bundle import derive_language_envelopes

    bundle = report_case.bundle
    envelopes = derive_language_envelopes(bundle)
    assert len(envelopes) == len(bundle.target_findings)
    for envelope in envelopes:
        target = next(f for f in bundle.target_findings if f.target_id == envelope.target.id)
        assert envelope.verdict == target.verdict
        assert envelope.claim_scope == target.claim_scope
        assert envelope.permitted_classes == target.language_permission
        assert set(target.limiting_factors) <= set(envelope.required_limitations)
    assert len({e.permitted_classes for e in envelopes}) > 1

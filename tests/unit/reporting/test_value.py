"""CIR claims, including high maturity labels, do not establish assessed value."""

from novelty_harness.domain.enums import ValueMaturity, VerdictState
from novelty_harness.domain.idea import ClaimedAdvantage
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


def claimed_bundle(bundle):
    # Pure projection variant; this caller shape cannot seed repository authority.
    cir = bundle.cir.model_copy(
        update={
            "claimed_advantages": (
                ClaimedAdvantage(
                    dimension="latency",
                    statement="Halves latency",
                    maturity=ValueMaturity.DEMONSTRATED,
                ),
            )
        }
    )
    return bundle.model_copy(update={"cir": cir})


def test_cir_high_maturity_is_attributed_not_assessed_value(report_case):
    from novelty_harness.reporting.value import project_value

    projections = project_value(claimed_bundle(report_case.bundle))
    attributed = next(p for p in projections if p.kind == "ATTRIBUTED_INPUT_CLAIM")
    assert attributed.claim == "Halves latency"
    assert attributed.attributed_maturity_label == ValueMaturity.DEMONSTRATED
    assert attributed.maturity is None
    assert any(p.kind == "NO_VALUE_ASSESSMENT" for p in projections)
    assert not any(p.kind == "AUTHORITATIVE_VALUE_FINDING" for p in projections)


def test_empty_value_and_significance_use_retained_gate_d_only(report_case):
    from novelty_harness.reporting.value import project_value

    bundle = report_case.bundle
    assert bundle.frozen_adjudication.value_findings == ()
    assert bundle.frozen_adjudication.novelty_significance == ()
    assert any(p.kind == "NO_VALUE_ASSESSMENT" for p in project_value(bundle))
    assert {f.gate_d_id for f in bundle.target_findings} <= {
        g.gate_id for g in bundle.gate_findings
    }
    assert bundle.frozen_adjudication == report_case.frozen


def test_high_value_direct_stays_negative_in_projection(report_case):
    from novelty_harness.reporting.bundle import derive_language_envelopes
    from novelty_harness.reporting.value import project_value

    bundle = claimed_bundle(report_case.bundle)
    assert project_value(bundle)
    envelopes = derive_language_envelopes(bundle)
    assert any(e.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL for e in envelopes)
    assert bundle.target_findings == report_case.frozen.target_findings


def test_missing_value_target_binding_stays_assessment_scoped(report_case):
    from novelty_harness.reporting.value import project_value

    attributed = [
        p
        for p in project_value(claimed_bundle(report_case.bundle))
        if p.kind == "ATTRIBUTED_INPUT_CLAIM"
    ]
    assert attributed and all(p.target is None for p in attributed)
    assert all(p.basis_refs and p.basis_refs[0].kind == "CIR" for p in attributed)

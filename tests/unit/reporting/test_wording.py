"""Native target ceilings bind public wording, including examples to avoid."""

import pytest

from novelty_harness.reporting.models import ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


def test_q8_respects_per_target_ceiling_and_unsupported_examples(report_case):
    from novelty_harness.reporting.wording import (
        ClaimWording,
        safe_claim_wording,
        validate_claim_wording,
    )

    wordings = safe_claim_wording(report_case.bundle)
    assert {w.target.id for w in wordings} == {
        f.target_id for f in report_case.bundle.target_findings
    }
    assert all(validate_claim_wording(w, report_case.bundle) == w for w in wordings)
    safe = wordings[0]
    example = ClaimWording.model_validate(
        safe.model_dump(mode="json")
        | {
            "use": "UNSUPPORTED_EXAMPLE",
            "wording_text": "Unsupported example to avoid: no prior art exists anywhere",
            "violation_reason_codes": ("UNIVERSAL_ABSENCE",),
        }
    )
    assert validate_claim_wording(example, report_case.bundle).use == "UNSUPPORTED_EXAMPLE"
    assert example not in wordings


def test_valid_whole_configuration_wording_requires_frozen_whole_target(report_case):
    from novelty_harness.reporting.wording import safe_claim_wording, validate_claim_wording

    component = next(w for w in safe_claim_wording(report_case.bundle) if w.target.kind == "MCU")
    with pytest.raises(ReportProposalError):
        validate_claim_wording(
            component.model_copy(update={"claim_scope": "the entire project"}), report_case.bundle
        )
    combination = next(
        w for w in safe_claim_wording(report_case.bundle) if w.target.kind == "COMBINATION"
    )
    native = next(
        f for f in report_case.bundle.target_findings if f.target_id == combination.target.id
    )
    assert combination.claim_scope == native.claim_scope
    assert validate_claim_wording(combination, report_case.bundle).target.kind == "COMBINATION"


def test_unassessable_wording_never_becomes_novelty(report_case):
    from novelty_harness.adjudication.frozen import LanguagePermissionClass
    from novelty_harness.reporting.wording import safe_claim_wording, validate_claim_wording

    words = safe_claim_wording(report_case.bundle)
    unknown = next(w for w in words if w.language_class == LanguagePermissionClass.ABSTENTION)
    assert "unassessable" in unknown.wording_text.lower()
    with pytest.raises(ReportProposalError):
        validate_claim_wording(
            unknown.model_copy(update={"language_class": LanguagePermissionClass.SCOPED_POTENTIAL}),
            report_case.bundle,
        )


def test_q8_union_class_cannot_be_rebound(report_case):
    from novelty_harness.adjudication.frozen import LanguagePermissionClass
    from novelty_harness.reporting.wording import safe_claim_wording, validate_claim_wording

    unknown = next(
        w
        for w in safe_claim_wording(report_case.bundle)
        if w.language_class == LanguagePermissionClass.ABSTENTION
    )
    with pytest.raises(ReportProposalError):
        validate_claim_wording(
            unknown.model_copy(
                update={"language_class": LanguagePermissionClass.CLAIM_SPECIFIC_NEGATIVE}
            ),
            report_case.bundle,
        )


def test_q8_universal_absence_example_requires_visible_label(report_case):
    from novelty_harness.reporting.wording import (
        ClaimWording,
        safe_claim_wording,
        validate_claim_wording,
    )

    safe = safe_claim_wording(report_case.bundle)[0]
    example = ClaimWording.model_validate(
        safe.model_dump(mode="json")
        | {
            "use": "UNSUPPORTED_EXAMPLE",
            "wording_text": "no prior art exists anywhere",
            "violation_reason_codes": ("UNIVERSAL_ABSENCE",),
        }
    )
    with pytest.raises(ReportProposalError):
        validate_claim_wording(example, report_case.bundle)


@pytest.mark.parametrize("mutation", ["permission", "basis", "limitations", "scope", "target"])
def test_wording_exact_permissions_and_limitations_are_required(report_case, mutation):
    from novelty_harness.adjudication.models import TargetRef
    from novelty_harness.reporting.wording import safe_claim_wording, validate_claim_wording

    safe = safe_claim_wording(report_case.bundle)[0]
    changes = {
        "permission": {"permission_refs": ()},
        "basis": {"basis_refs": ()},
        "limitations": {"necessary_limitations": ()},
        "scope": {"scope": safe.scope.model_copy(update={"adjudication_id": "other"})},
        "target": {"target": TargetRef(kind="MCU", id="foreign")},
    }
    with pytest.raises(ReportProposalError):
        validate_claim_wording(safe.model_copy(update=changes[mutation]), report_case.bundle)

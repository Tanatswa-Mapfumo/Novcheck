"""Mechanical closure lifetime; toy loaders never establish native authority."""

import weakref
from types import SimpleNamespace

import pytest

from novelty_harness.evidence.graph import report_store, report_validation
from novelty_harness.reporting.artifacts import ReportStatusEvent
from novelty_harness.reporting.repository import ReportAuthorityError
from tests.unit.reporting.test_rendering_digest import shape_report


class Closure:
    def __init__(self, **values):
        self.__dict__.update(values)


def controlled_validation(monkeypatch, *, corrupt=None):
    report = shape_report()
    provenance = report.ir.generation_provenance
    report = report.model_copy(
        update={
            "approved_versions": provenance.approved_versions,
            "configuration_refs": provenance.configuration_refs,
            "execution_refs": provenance.execution_refs,
            "dependencies": (
                *report.ir.source_dependency_manifest,
                *report.ir.report_artifact_dependencies,
            ),
        }
    )
    status = ReportStatusEvent(
        scope=report.scope,
        compilation_id=report.compilation_id,
        event_id="mechanical-verified",
        predecessor_id="mechanical-drafted",
        expected_state="DRAFTED",
        next_state="FAILED" if corrupt == "state" else "VERIFIED",
        reason="toy closure only",
        observed_at=report.accepted_at,
    )
    references, calls = {}, []
    compilation = SimpleNamespace(
        scope=report.scope, options=SimpleNamespace(render_policy_version="p8-render-v1")
    )

    def load_bundle(*_):
        calls.append("native_bundle")
        bundle = Closure(padding=bytearray(1_000_000))
        references["bundle"] = weakref.ref(bundle)
        return bundle

    def load_artifacts(*_):
        calls.append("native_artifacts")
        artifact = Closure(document=status, padding=bytearray(1_000_000))
        references["artifact"] = weakref.ref(artifact)
        return (artifact,)

    def validate_ir(*_):
        calls.append("IR_recomputation")
        assert all(ref() is not None for ref in references.values())
        if corrupt == "IR":
            raise ValueError("controlled corrupted IR")

    def render(*_, **__):
        calls.append("render")
        assert all(ref() is None for ref in references.values()), (
            "native closure retained after its complete checks",
            {name: ref() is not None for name, ref in references.items()},
        )
        return "toy rendition"

    monkeypatch.setattr(report_validation, "_revalidate_proposal", lambda value: value)
    monkeypatch.setattr(report_validation, "report_id", lambda _: report.report_id)
    monkeypatch.setattr(report_store, "load_report_compilation_in_session", lambda *_: compilation)
    monkeypatch.setattr(report_store, "revalidate_report_bundle_in_session", load_bundle)
    monkeypatch.setattr(report_store, "load_report_artifacts_in_session", load_artifacts)
    monkeypatch.setattr(report_store, "report_attempt_state", lambda _: status)
    monkeypatch.setattr(report_validation, "validate_report_ir", validate_ir)
    monkeypatch.setattr(report_validation, "render_compiled_report", render)
    monkeypatch.setattr(
        report_validation, "validate_rendition_parity", lambda *_: calls.append("parity")
    )
    if corrupt == "dependency":
        report = report.model_copy(update={"dependencies": ("controlled-extra-dependency",)})
    elif corrupt == "provenance":
        report = report.model_copy(update={"approved_versions": ("foreign-version",)})
    elif corrupt == "scope":
        report = report.model_copy(
            update={"scope": report.scope.model_copy(update={"adjudication_id": "foreign"})}
        )
    return report, status, calls


def test_checked_native_closure_is_released_before_rendition_allocation(monkeypatch):
    report, status, calls = controlled_validation(monkeypatch)
    result = report_validation.validate_compiled_report_in_session(
        None, None, report.compilation_id, report
    )
    assert result == status
    assert calls == ["native_bundle", "native_artifacts", "IR_recomputation", "render", "parity"]


@pytest.mark.parametrize("corrupt", ["IR", "dependency", "provenance", "scope", "state"])
def test_release_does_not_remove_checks_or_render_corrupt_proposals(monkeypatch, corrupt):
    report, _, calls = controlled_validation(monkeypatch, corrupt=corrupt)
    with pytest.raises(ReportAuthorityError):
        report_validation.validate_compiled_report_in_session(
            None, None, report.compilation_id, report
        )
    assert "render" not in calls and "parity" not in calls

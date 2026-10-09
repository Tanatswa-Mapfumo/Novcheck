"""Version selection controls; an approved policy pin is never native authority."""

import pytest

from novelty_harness.reporting.execution import (
    DETERMINISTIC_VERSIONS,
    ReportCompilationConfiguration,
)


def _policy(versions):
    from novelty_harness.reporting.execution import bundle_policy_version

    return bundle_policy_version(ReportCompilationConfiguration(deterministic_versions=versions))


def test_default_bundle_policy_is_v2():
    assert _policy(DETERMINISTIC_VERSIONS) == "p8-bundle-v2"


def test_original_v1_configuration_remains_explicitly_supported():
    legacy = tuple(
        "p8-bundle-v1" if v.startswith("p8-bundle-") else v for v in DETERMINISTIC_VERSIONS
    )
    assert _policy(legacy) == "p8-bundle-v1"


@pytest.mark.parametrize("change", ["missing", "ambiguous", "unknown", "incomplete", "extra"])
def test_bundle_policy_rejects_missing_ambiguous_or_unapproved_registry(change):
    versions = tuple(v for v in DETERMINISTIC_VERSIONS if not v.startswith("p8-bundle-"))
    if change == "ambiguous":
        versions += ("p8-bundle-v1", "p8-bundle-v2")
    elif change == "unknown":
        versions += ("p8-bundle-v99",)
    elif change == "incomplete":
        versions = versions[1:] + ("p8-bundle-v2",)
    elif change == "extra":
        versions += ("p8-bundle-v2", "unapproved-policy")
    with pytest.raises(ValueError, match="polic"):
        _policy(versions)


@pytest.fixture(scope="module")
def native_case(tmp_path_factory):
    from tests.fixtures.phase8 import make_report_scenario

    case = make_report_scenario(tmp_path_factory.mktemp("bundle-policy"), "POTENTIAL")
    try:
        yield case
    finally:
        case.repository.close()


def test_native_v1_and_v2_preserve_full_projection_and_original_v1_algorithm(native_case):
    from novelty_harness.reporting.bundle import report_bundle_digest
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    bundles = []
    for version in ("p8-bundle-v1", "p8-bundle-v2"):
        bundle = native_case.repository.load_report_input_bundle(
            native_case.frozen.assessment_id,
            adjudication_id=native_case.frozen.adjudication_id,
            bundle_version=version,
        )
        assert bundle.bundle_version == version
        assert bundle.frozen_adjudication == native_case.frozen
        assert bundle.bundle_digest == report_bundle_digest(bundle)
        bundles.append(bundle)
    v1, v2 = bundles
    assert v1.bundle_digest == canonical_hash(v1.model_dump(mode="json", exclude={"bundle_digest"}))
    assert v2.bundle_digest == canonical_hash(
        v2.model_dump(mode="python", exclude={"bundle_digest"})
    )
    assert v1.bundle_digest != v2.bundle_digest
    excluded = {"bundle_digest", "bundle_version", "contract_kind"}
    assert canonical_hash(v1.model_dump(mode="python", exclude=excluded)) == canonical_hash(
        v2.model_dump(mode="python", exclude=excluded)
    )
    assert v1.dependency_manifest == v2.dependency_manifest


def test_v2_digest_preserves_order_and_rejects_contract_version_mismatch(native_case):
    from pydantic import ValidationError

    from novelty_harness.reporting.bundle import ReportInputBundle, report_bundle_digest

    original = native_case.bundle
    first = original.model_copy(update={"audit_refs": ("ordered-one", "ordered-two")})
    second = original.model_copy(update={"audit_refs": ("ordered-two", "ordered-one")})
    assert report_bundle_digest(first) != report_bundle_digest(second)
    with pytest.raises(ValidationError, match="contract and policy"):
        ReportInputBundle.model_validate(
            {**original.model_dump(mode="json"), "contract_kind": "phase8-report-input-bundle-v1"}
        )


def test_native_attempts_pin_legacy_and_v2_and_refuse_wrong_status_policy(native_case):
    from novelty_harness.reporting.artifacts import (
        ReportArtifactKind,
        ReportStatusEvent,
        make_report_artifact,
        report_status_event_id,
    )
    from novelty_harness.reporting.models import ReportOptions
    from novelty_harness.reporting.repository import ReportAuthorityError
    from tests.fixtures.phase8 import OBSERVED
    from tests.unit.evidence.graph.test_report_store import _upstream_rows

    upstream = _upstream_rows(native_case.repository)
    records = []
    for version in ("p8-bundle-v1", "p8-bundle-v2"):
        config = ReportCompilationConfiguration(
            deterministic_versions=tuple(
                version if v.startswith("p8-bundle-") else v for v in DETERMINISTIC_VERSIONS
            )
        )
        record = native_case.repository.begin_report_compilation(
            native_case.frozen.assessment_id,
            adjudication_id=native_case.frozen.adjudication_id,
            options=ReportOptions(),
            configuration=config,
            attempt_token="versioned-policy",
        )
        artifacts = native_case.repository.load_report_artifacts(record.compilation_id)
        assert len(artifacts) == 1 and artifacts[0].method_version == version
        start = artifacts[0].document
        assert isinstance(start, ReportStatusEvent)
        failed = ReportStatusEvent(
            scope=record.scope,
            compilation_id=record.compilation_id,
            event_id="pending",
            predecessor_id=start.event_id,
            expected_state="STARTED",
            next_state="FAILED",
            reason="Recorded operational failure",
            observed_at=OBSERVED,
        )
        failed = failed.model_copy(update={"event_id": report_status_event_id(failed)})
        wrong = "p8-bundle-v2" if version == "p8-bundle-v1" else "p8-bundle-v1"
        with pytest.raises(ReportAuthorityError, match="status identity or method"):
            native_case.repository.record_report_artifact(
                record.compilation_id,
                make_report_artifact(
                    record, ReportArtifactKind.STATUS, failed, method_version=wrong
                ),
            )
        assert native_case.repository.load_report_artifacts(record.compilation_id) == artifacts
        assert (
            native_case.repository.begin_report_compilation(
                native_case.frozen.assessment_id,
                adjudication_id=native_case.frozen.adjudication_id,
                options=record.options,
                configuration=record.configuration,
                attempt_token=record.attempt_token,
            )
            == record
        )
        records.append(record)
    assert records[0].compilation_key != records[1].compilation_key
    assert records[0].compilation_id != records[1].compilation_id
    assert _upstream_rows(native_case.repository) == upstream


def test_application_configuration_selects_the_native_bundle_policy(native_case):
    from novelty_harness.application.phase8 import _configuration
    from novelty_harness.ports.reporting import ReportPorts
    from novelty_harness.reporting.execution import bundle_policy_version

    for version in ("p8-bundle-v1", "p8-bundle-v2"):
        bundle = native_case.repository.load_report_input_bundle(
            native_case.frozen.assessment_id,
            adjudication_id=native_case.frozen.adjudication_id,
            bundle_version=version,
        )
        assert bundle_policy_version(_configuration(bundle, ReportPorts())) == version

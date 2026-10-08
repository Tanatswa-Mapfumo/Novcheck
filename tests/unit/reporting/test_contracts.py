"""Report shape and identity invariants, without asserting repository authority."""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from novelty_harness.adjudication.models import TargetRef
from tests.fixtures.phase8 import OBSERVED, report_configuration, report_scope


def test_report_contracts_are_strict_scoped_and_distinct():
    from novelty_harness.reporting.artifacts import ReportCompilationRecord
    from novelty_harness.reporting.execution import ReportExecutionRecord
    from novelty_harness.reporting.models import (
        AuthorityRef,
        ReportLens,
        ReportOptions,
        ReportScope,
        validate_authority_refs,
    )

    scope = report_scope()
    assert ReportScope.model_config["frozen"] is True
    assert {lens.value for lens in ReportLens} == {
        "RESEARCH",
        "PRODUCT",
        "ENGINEERING",
        "SOFTWARE",
        "PROCESS",
        "PATENT_SCREENING",
    }
    for field in (
        "assessment_id",
        "adjudication_id",
        "assessment_context_id",
        "phase6_snapshot_id",
    ):
        missing = scope.model_dump()
        del missing[field]
        with pytest.raises(ValidationError):
            ReportScope.model_validate(missing)
    with pytest.raises(ValidationError):
        scope.adjudication_id = "p7frozen_other"
    for forbidden in ("novelty_override", "novelty_score", "search", "trusted", "qualification"):
        with pytest.raises(ValidationError):
            ReportOptions.model_validate({forbidden: "STRONG_EVIDENCE_OF_NOVELTY"})
    with pytest.raises(ValidationError):
        ReportExecutionRecord.model_validate({"trusted": True})
    record = _compilation()
    with pytest.raises(ValidationError):
        ReportCompilationRecord.model_validate(
            {**record.model_dump(), "started_at": datetime(2026, 10, 5)}
        )
    assert record.started_at.utcoffset() == timedelta(0)
    ref = AuthorityRef(
        kind="TARGET",
        native_id="mcu_report",
        digest="a" * 64,
        scope=scope,
        target=TargetRef(kind="MCU", id="mcu_report"),
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_authority_refs((ref, ref), scope)
    foreign = AuthorityRef.model_validate(
        {
            **ref.model_dump(),
            "scope": {**scope.model_dump(), "assessment_context_id": "p7ctx_other"},
        }
    )
    with pytest.raises(ValueError, match="scope"):
        validate_authority_refs((foreign,), scope)
    assert ReportOptions().limits is not ReportOptions().limits


def _compilation(*, observed=OBSERVED):
    from novelty_harness.reporting.artifacts import (
        ReportCompilationRecord,
        compilation_id,
        compilation_key,
    )
    from novelty_harness.reporting.execution import bind_compilation_configuration
    from novelty_harness.reporting.models import ReportOptions

    scope, options, config = report_scope(), ReportOptions(), report_configuration()
    key = compilation_key(scope, "b" * 64, options, config)
    return ReportCompilationRecord(
        scope=scope,
        compilation_id=compilation_id(key, "attempt-one"),
        compilation_key=key,
        attempt_token="attempt-one",
        options=options,
        configuration=bind_compilation_configuration(
            config, scope, compilation_id(key, "attempt-one")
        ),
        bundle_digest="b" * 64,
        started_at=observed,
    )


def test_observation_does_not_change_compilation_identity():
    from novelty_harness.reporting.artifacts import ReportArtifact, report_artifact_id
    from novelty_harness.reporting.execution import (
        ReportExecutionObservations,
        ReportExecutionRecord,
    )

    first, later = _compilation(), _compilation(observed=OBSERVED + timedelta(days=1))
    assert first.compilation_id == later.compilation_id
    role = first.configuration.roles[0]
    execution = ReportExecutionRecord(
        scope=first.scope,
        compilation_id=first.compilation_id,
        invocation_id="invocation-one",
        role=role.role,
        task_name="report-plan",
        method_version=role.method_version,
        actual_instruction_hash=role.instruction_hash,
        configuration_id=role.configuration_id,
        request_hash="c" * 64,
        raw_response_hash="d" * 64,
        validated_proposal_hash="e" * 64,
        outcome="VALIDATED",
        observations=ReportExecutionObservations(observed_at=OBSERVED, tokens=12, cost_usd=0.1),
    )
    artifact = ReportArtifact(
        scope=first.scope,
        compilation_id=first.compilation_id,
        artifact_id="pending",
        kind="EXECUTION",
        method_version=role.method_version,
        document=execution,
    )
    changed = ReportArtifact.model_validate(
        {
            **artifact.model_dump(),
            "document": {
                **execution.model_dump(),
                "observations": {
                    "observed_at": OBSERVED + timedelta(hours=2),
                    "tokens": 80,
                    "cost_usd": 3,
                    "latency_ms": 1000,
                },
            },
        }
    )
    assert report_artifact_id(artifact) == report_artifact_id(changed)
    different = ReportArtifact.model_validate(
        {
            **artifact.model_dump(),
            "document": {**execution.model_dump(), "raw_response_hash": "f" * 64},
        }
    )
    assert report_artifact_id(artifact) != report_artifact_id(different)


def test_options_have_operational_not_epistemic_limits():
    from novelty_harness.reporting.models import ReportGenerationLimits, ReportOptions

    options = ReportOptions(
        limits=ReportGenerationLimits(max_calls=0, max_tokens=0, max_repairs_total=0)
    )
    assert options.limits.max_calls == 0
    assert options.limits.max_tokens == 0
    for forbidden in ("research_sufficient", "saturated", "positive_permission"):
        with pytest.raises(ValidationError):
            ReportGenerationLimits.model_validate({forbidden: True})
    for field in ("max_calls", "max_tokens", "max_cost_usd", "max_context_chars"):
        with pytest.raises(ValidationError):
            ReportGenerationLimits.model_validate({field: -1})
    with pytest.raises(ValidationError):
        options.limits.max_calls = 10


def test_dependency_paths_do_not_collide():
    from novelty_harness.reporting.models import (
        AuthorityRef,
        ReportDependency,
        authority_dependency_id,
    )

    refs = tuple(
        AuthorityRef(
            kind="CIR",
            native_id="idea_record",
            digest="a" * 64,
            scope=report_scope(),
            path=(field,),
        )
        for field in ("mechanism", "claimed_advantages")
    )
    assert authority_dependency_id(refs[0]) != authority_dependency_id(refs[1])
    for ref in refs:
        dep = ReportDependency(
            dependency_kind="UPSTREAM",
            dependency_id=authority_dependency_id(ref),
            expected_digest=ref.digest,
            authority_ref=ref,
        )
        assert dep.authority_ref.path == ref.path
        with pytest.raises(ValidationError):
            ReportDependency.model_validate(
                {**dep.model_dump(), "report_artifact_id": "p8artifact_other"}
            )
        with pytest.raises(ValidationError):
            ReportDependency.model_validate({**dep.model_dump(), "dependency_id": "wrong-field"})
    with pytest.raises(ValidationError):
        AuthorityRef.model_validate({**refs[0].model_dump(), "path": (-1,)})


def test_semantic_options_change_compilation_key():
    from novelty_harness.reporting.artifacts import compilation_key
    from novelty_harness.reporting.models import ReportOptions

    scope, config = report_scope(), report_configuration()
    key = compilation_key(scope, "b" * 64, ReportOptions(), config)
    assert key.startswith("p8key_")
    for changes in (
        {"lens": "ENGINEERING"},
        {"compact_summary": True},
        {"detail": "DETAILED"},
        {"render_policy_version": "p8-render-future"},
    ):
        assert (
            compilation_key(scope, "b" * 64, ReportOptions.model_validate(changes), config) != key
        )
    assert (
        compilation_key(scope, "b" * 64, ReportOptions(), report_configuration(model="other-model"))
        != key
    )


def test_method_registry_rejects_unknown_or_relabelled_instruction():
    from novelty_harness.reporting.execution import validate_method_registration

    role = report_configuration().roles[0]
    validate_method_registration(role.method)
    with pytest.raises(ValueError, match="approved"):
        validate_method_registration(role.method.model_copy(update={"instruction_hash": "a" * 64}))
    with pytest.raises(ValueError, match="approved"):
        validate_method_registration(
            role.method.model_copy(update={"method_version": "p8-unregistered"})
        )


def test_artifact_union_and_configuration_reject_cross_scope_and_role_duplicates():
    from novelty_harness.reporting.artifacts import ReportArtifact
    from novelty_harness.reporting.execution import ReportCompilationConfiguration

    config = report_configuration()
    with pytest.raises(ValidationError):
        ReportCompilationConfiguration(roles=(config.roles[0], config.roles[0]))
    with pytest.raises(ValidationError):
        ReportArtifact(
            scope=report_scope(),
            compilation_id="p8run_other",
            artifact_id="pending",
            kind="METHOD",
            method_version=config.roles[0].method_version,
            document=config.roles[0].method,
        )
    with pytest.raises(ValidationError):
        ReportArtifact(
            scope=report_scope(),
            compilation_id="p8run_shapes",
            artifact_id="pending",
            kind="METHOD",
            method_version=config.roles[0].method_version,
            document={"trusted": True},
        )

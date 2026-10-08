"""Semantic provenance describes an execution, never a model's self-description."""

import asyncio
from dataclasses import replace

import pytest

from novelty_harness.adjudication.roles import validate_prosecution_case
from novelty_harness.application.phase7 import publish_frozen_phase7_trace, run_phase7
from novelty_harness.application.phase7_model_adapter import (
    Phase7ModelOutputError,
    ProsecutionModelAdapter,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase6 import StubLLMProvider
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.integration.test_phase7_slice import _real_ports
from tests.unit.adjudication.test_roles import build_packet, valid_case


@pytest.fixture(scope="module")
def packet(tmp_path_factory):
    return build_packet(tmp_path_factory.mktemp("phase7_execution"))


def test_role_case_prompt_version_must_match_execution_record(packet):
    stale = valid_case(packet).model_copy(update={"prompt_version": "p7-prosecutor-v1"})
    with pytest.raises(ValueError, match="prompt"):
        validate_prosecution_case(stale, packet)


def test_model_supplied_prompt_version_cannot_gain_authority(packet):
    stale = valid_case(packet).model_copy(update={"prompt_version": "p7-prosecutor-v1"})
    provider = StubLLMProvider({"phase7_prosecutor": stale.model_dump(mode="json")})
    adapter = ProsecutionModelAdapter(SemanticRunner(provider))
    with pytest.raises(Phase7ModelOutputError):
        asyncio.run(adapter.propose(packet))
    assert len(provider.calls) == 2
    assert all(a.prompt_version == "p7-prosecutor-v2" for a in adapter.audits)


def test_stale_v1_role_case_cannot_freeze_under_v2_run(tmp_path):
    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)

    class StaleRole:
        def __init__(self, inner, version):
            self.inner = inner
            self.version = version

        async def propose(self, given):
            return (await self.inner.propose(given)).model_copy(
                update={"prompt_version": self.version}
            )

    try:
        with pytest.raises(ValueError, match="prompt"):
            asyncio.run(
                run_phase7(
                    packet.assessment_id,
                    context_id=packet.assessment_context_id,
                    repository=repository,
                    ports=replace(
                        ports,
                        prosecutor=StaleRole(ports.prosecutor, "p7-prosecutor-v1"),
                        defender=StaleRole(ports.defender, "p7-defender-v1"),
                    ),
                )
            )
    finally:
        repository.close()


def test_trace_and_repository_provenance_are_derived_from_same_execution(tmp_path):
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        adjudication_id = repository.freeze_phase7_adjudication(run.run_id, proposed)
        sink = InMemoryTraceSink()
        events = publish_frozen_phase7_trace(
            packet.assessment_id, adjudication_id=adjudication_id, repository=repository, sink=sink
        )
        artifacts = repository.load_phase7_artifacts(run.run_id)
        for artifact in artifacts:
            if artifact.kind not in {"PROSECUTION_CASE", "DEFENSE_CASE", "REBUTTAL", "JUDGE_RUN"}:
                continue
            execution = getattr(artifact, "execution", None)
            assert execution is not None
            event = next(
                e
                for e in events
                if e.reason_code == "PHASE7_ARTIFACT_COMMITTED"
                and e.data["artifact_ids"] == [artifact.artifact_id]
            )
            assert event.data["prompt_version"] == execution.prompt_version
            assert event.data["model_config_id"] == execution.model_config_id
            assert event.data.get("invocation_prompt_hash") == execution.invocation_prompt_hash
            assert event.request_hash == execution.request_hash
            assert event.response_hash == execution.response_hash
    finally:
        repository.close()


def test_adapter_execution_record_binds_actual_invocation_and_output(packet):
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    provider = StubLLMProvider({"phase7_prosecutor": valid_case(packet).model_dump(mode="json")})
    adapter = ProsecutionModelAdapter(SemanticRunner(provider))
    proposal = asyncio.run(adapter.propose(packet))
    execution = adapter.execution_for(proposal)
    assert execution.prompt_version == adapter.audits[-1].prompt_version
    assert execution.request_hash == adapter.audits[-1].request_hash
    assert execution.response_hash == adapter.audits[-1].response_hash
    assert execution.proposal_hash == canonical_hash(proposal)
    assert execution.provider_name == provider.name


def _replace_frozen_artifact(repository, frozen, original, changed):
    """Coherently rewrite content IDs/FKs, so a generic bad hash cannot prove the test."""
    from novelty_harness.adjudication.execution import phase7_artifact_id
    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.runtime.tracing.hashing import canonical_json

    changed = changed.model_copy(
        update={
            "artifact_id": phase7_artifact_id(
                changed.run_id, changed.kind, changed.document_json, changed.execution
            )
        }
    )
    document = frozen.model_dump_json().replace(original.artifact_id, changed.artifact_id)
    replacement = type(frozen).model_validate_json(document)
    replacement = replacement.model_copy(update={"adjudication_id": phase7_frozen_id(replacement)})
    connection = repository.engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute(
            "UPDATE phase7_artifacts SET artifact_id=?, document_json=? WHERE artifact_id=?",
            (changed.artifact_id, canonical_json(changed), original.artifact_id),
        )
        cursor.execute(
            "UPDATE phase7_frozen_dependencies SET artifact_id=? WHERE artifact_id=?",
            (changed.artifact_id, original.artifact_id),
        )
        cursor.execute(
            "UPDATE phase7_frozen_manifests SET adjudication_id=?, document_json=? "
            "WHERE adjudication_id=?",
            (replacement.adjudication_id, canonical_json(replacement), frozen.adjudication_id),
        )
        cursor.execute(
            "UPDATE phase7_frozen_dependencies SET adjudication_id=? WHERE adjudication_id=?",
            (replacement.adjudication_id, frozen.adjudication_id),
        )
        connection.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
        assert cursor.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
    return replacement


def test_frozen_load_rejects_stale_prompt_dependency(tmp_path):
    from novelty_harness.adjudication.roles import ProsecutionCase
    from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        original = next(
            a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == "PROSECUTION_CASE"
        )
        stale = ProsecutionCase.model_validate_json(original.document_json).model_copy(
            update={"prompt_version": "p7-prosecutor-v1"}
        )
        changed = original.model_copy(
            update={
                "document_json": canonical_json(stale),
                "execution": original.execution.model_copy(
                    update={"proposal_hash": canonical_hash(stale)}
                ),
            }
        )
        replacement = _replace_frozen_artifact(repository, proposed, original, changed)
        with pytest.raises(ValueError, match="prompt"):
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=replacement.adjudication_id
            )
    finally:
        repository.close()


@pytest.mark.parametrize(
    "kind, field, wrong",
    [
        ("PROSECUTION_CASE", "prompt_hash", "same-label-wrong-instruction"),
        ("DEFENSE_CASE", "prompt_version", "p7-defender-v1"),
        ("JUDGE_RUN", "prompt_version", "p7-judge-rubric-v1"),
        ("JUDGE_RUN", "model_config_id", "p7model_another-model"),
        ("PROSECUTION_CASE", "configuration_id", "another-target-registration"),
    ],
)
def test_frozen_execution_tampering_fails_even_with_consistent_content_ids(
    tmp_path, kind, field, wrong
):
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        original = next(a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == kind)
        changed = original.model_copy(
            update={"execution": original.execution.model_copy(update={field: wrong})}
        )
        replacement = _replace_frozen_artifact(repository, proposed, original, changed)
        with pytest.raises(ValueError, match="execution|prompt|config"):
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=replacement.adjudication_id
            )
    finally:
        repository.close()


def test_rebuttal_execution_rejects_old_prompt_and_foreign_configuration(packet):
    from novelty_harness.adjudication.execution import validate_semantic_execution
    from novelty_harness.adjudication.models import SemanticExecutionRecord
    from novelty_harness.adjudication.roles import RebuttalCase
    from novelty_harness.application.phase7_execution import invocation_configuration
    from novelty_harness.application.phase7_roles import make_phase7_artifact
    from novelty_harness.runtime.tracing.hashing import canonical_hash
    from tests.unit.adjudication.test_roles import scope

    proposal = RebuttalCase(
        **scope(packet, valid_case(packet).target_id),
        rebuttal_id="p7reb_execution",
        role="PROSECUTOR",
        dispute_ids=(),
        argument_ids=(),
    )
    config = invocation_configuration(object(), "REBUTTAL", proposal)
    registration = make_phase7_artifact("review-run", "SEMANTIC_CONFIGURATION", config)
    execution = SemanticExecutionRecord(
        invocation_prompt_hash=config.prompt_hash,
        configuration_id=registration.artifact_id,
        prompt_version="p7-rebuttal-v1",
        prompt_hash=config.prompt_hash,
        model_config_id=config.model_config_id,
        provider_name=config.provider_name,
        execution_mode="PORT_PROTOCOL",
        request_hash="request",
        response_hash="response",
        proposal_hash=canonical_hash(proposal),
    )
    artifact = make_phase7_artifact("review-run", "REBUTTAL", proposal, execution=execution)
    with pytest.raises(ValueError, match="prompt"):
        validate_semantic_execution(artifact, (registration,))
    wrong = registration.model_copy(update={"run_id": "another-run"})
    with pytest.raises(ValueError, match="scope"):
        validate_semantic_execution(artifact, (wrong,))


def test_trace_cannot_advertise_another_prompt_for_committed_execution(tmp_path):
    from novelty_harness.application.phase7_model_adapter import Phase7ModelCallRecord
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        execution = next(
            a.execution
            for a in repository.load_phase7_artifacts(run.run_id)
            if a.kind == "PROSECUTION_CASE"
        )
        fake = Phase7ModelCallRecord(
            prompt_version="p7-prosecutor-v1",
            model_name=None,
            provider_name=execution.provider_name,
            provider_version=None,
            request_hash=execution.request_hash,
            response_hash=execution.response_hash,
            latency_ms=0,
            validation_state="VALIDATED",
        )
        sink = InMemoryTraceSink()
        with pytest.raises(ValueError, match="provenance"):
            publish_frozen_phase7_trace(
                packet.assessment_id,
                adjudication_id=proposed.adjudication_id,
                repository=repository,
                sink=sink,
                call_records=(fake,),
            )
        assert not sink.events
    finally:
        repository.close()


def test_execution_retains_actual_model_and_provider_metadata(packet):
    from novelty_harness.ports.models import LLMCallConfig

    provider = StubLLMProvider({"phase7_prosecutor": valid_case(packet).model_dump(mode="json")})
    adapter = ProsecutionModelAdapter(
        SemanticRunner(provider, LLMCallConfig(model="recorded-review-model"))
    )
    proposal = asyncio.run(adapter.propose(packet))
    execution = adapter.execution_for(proposal)
    assert execution.model_name == "recorded-review-model"
    assert execution.provider_version == adapter.audits[-1].call.provider_version
    assert execution.latency_ms >= 0


def test_recovery_execution_hashes_the_actual_recovery_instruction(packet):
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    def response(blocks):
        return (
            valid_case(packet).model_dump(mode="json")
            if "previous response failed" in blocks[0].text
            else {}
        )

    provider = StubLLMProvider({"phase7_prosecutor": response})
    adapter = ProsecutionModelAdapter(SemanticRunner(provider))
    proposal = asyncio.run(adapter.propose(packet))
    execution = adapter.execution_for(proposal)
    assert len(provider.calls) == 2
    assert execution.invocation_prompt_hash == canonical_hash(provider.calls[-1][1][0].text)
    assert execution.request_hash == adapter.audits[-1].request_hash


def test_model_roles_persist_their_own_runtime_audit_on_shared_runner(tmp_path):
    from novelty_harness.adjudication.roles import DefenseCase
    from novelty_harness.application.phase7_model_adapter import DefenseModelAdapter
    from novelty_harness.application.phase7_roles import run_independent_first_passes
    from tests.unit.adjudication.test_roles import scope

    given = build_packet(tmp_path)
    prosecution = valid_case(given)
    defense = DefenseCase(
        **scope(given, prosecution.target_id), case_id="p7def_execution", points=()
    )
    provider = StubLLMProvider(
        {
            "phase7_prosecutor": prosecution.model_dump(mode="json"),
            "phase7_defender": defense.model_dump(mode="json"),
        }
    )
    runner = SemanticRunner(provider)
    prosecutor, defender = ProsecutionModelAdapter(runner), DefenseModelAdapter(runner)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        run = repository.begin_phase7_run(given.assessment_context_id)
        asyncio.run(
            run_independent_first_passes(run.run_id, given, prosecutor, defender, repository)
        )
        for kind, task in (
            ("PROSECUTION_CASE", "phase7_prosecutor"),
            ("DEFENSE_CASE", "phase7_defender"),
        ):
            artifact = next(
                a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == kind
            )
            audit = next(a for a in runner.audits if a.task_name == task)
            assert artifact.execution.execution_mode == "SEMANTIC_RUNNER"
            assert artifact.execution.request_hash == audit.request_hash
            assert artifact.execution.response_hash == audit.response_hash
            assert artifact.execution.provider_name == provider.name
            assert artifact.execution.configuration_id in {
                a.artifact_id for a in repository.load_phase7_artifacts(run.run_id)
            }
    finally:
        repository.close()

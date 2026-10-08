import pytest
from sqlalchemy import event, inspect, text

from novelty_harness.adjudication.models import Phase7RunState
from novelty_harness.adjudication.repository import Phase7AuthorityError
from novelty_harness.evidence.graph.migrations import ensure_schema, schema_version
from novelty_harness.evidence.graph.sqlalchemy_models import Base
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.runtime.budgets.controller import BudgetUsage
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.unit.adjudication.test_context import make_manifest, make_snapshot
from tests.unit.adjudication.test_roles import build_packet

PHASE7_TABLES = {
    "phase7_input_manifests",
    "phase7_assessment_contexts",
    "phase7_runs",
    "phase7_run_transitions",
    "phase7_artifacts",
    "phase7_qualification_refs",
    "phase7_frozen_manifests",
    "phase7_frozen_dependencies",
}


def test_context_rejects_changed_mcu_mechanism_under_same_phase6_snapshot(tmp_path) -> None:
    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        graph = packet.manifest.mcu_graph
        changed_mcus = tuple(
            mcu.model_copy(update={"mechanism": "A new claimed mechanism"})
            if mcu.mcu_id == "mcu_status"
            else mcu
            for mcu in graph.mcus
        )
        changed_graph = graph.model_copy(update={"mcus": changed_mcus})
        with pytest.raises(ValueError, match="target profile"):
            repository.seal_phase7_context(
                packet.assessment_id,
                snapshot_id=packet.phase6_snapshot_id,
                manifest=packet.manifest.model_copy(update={"mcu_graph": changed_graph}),
                parent_context_id=packet.assessment_context_id,
            )
    finally:
        repository.close()


def test_v7_migrates_to_empty_v8_without_phase7_backfill(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    # Reconstruct the actual v7 table topology before asking v8 to migrate.
    phase7_rows = tuple(
        table for table in Base.metadata.tables.values() if table.name in PHASE7_TABLES
    )
    Base.metadata.drop_all(repository.engine, tables=phase7_rows)
    with repository.engine.begin() as connection:
        connection.execute(text("UPDATE schema_version SET version = 7"))
    assert not PHASE7_TABLES & set(inspect(repository.engine).get_table_names())
    assert ensure_schema(repository.engine) == 9
    assert schema_version(repository.engine) == 9
    assert PHASE7_TABLES <= set(inspect(repository.engine).get_table_names())
    with repository.engine.connect() as connection:
        for table in sorted(PHASE7_TABLES):
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
    repository.close()


def test_v8_initialization_is_idempotent_and_rollback_is_atomic(tmp_path) -> None:
    database = tmp_path / "phase7.db"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    assert ensure_schema(repository.engine) == 9
    repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(database)
    assert ensure_schema(reopened.engine) == 9
    assert PHASE7_TABLES <= set(inspect(reopened.engine).get_table_names())
    snapshot_id = make_snapshot(reopened)
    manifest = make_manifest(
        phase6_snapshot_id=snapshot_id,
        budget_usage=BudgetUsage(provider_calls=1),
    )

    def fail_context_insert(_connection, _cursor, statement, _parameters, _context, _many):
        if "INSERT INTO phase7_assessment_contexts" in statement:
            raise RuntimeError("injected context insert failure")

    event.listen(reopened.engine, "before_cursor_execute", fail_context_insert)
    try:
        with pytest.raises(RuntimeError, match="injected context insert failure"):
            reopened.seal_phase7_context("asm_context", snapshot_id=snapshot_id, manifest=manifest)
    finally:
        event.remove(reopened.engine, "before_cursor_execute", fail_context_insert)
    with reopened.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM phase7_input_manifests")).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM phase7_assessment_contexts")).scalar_one()
            == 0
        )
    reopened.close()


def test_run_state_rejects_skipped_first_pass_and_stale_transition(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    snapshot_id = make_snapshot(repository)
    context = repository.seal_phase7_context(
        "asm_context",
        snapshot_id=snapshot_id,
        manifest=make_manifest(phase6_snapshot_id=snapshot_id),
    )
    run = repository.begin_phase7_run(context.context_id, attempt_token="state-guard")
    with pytest.raises(Phase7AuthorityError, match="Invalid run transition"):
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FROZEN,
        )
    with pytest.raises(Phase7AuthorityError, match="first passes"):
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FIRST_PASSES_COMPLETE,
        )
    repository.transition_phase7_run(
        run.run_id,
        expected_state=Phase7RunState.CASE_BUILT,
        next_state=Phase7RunState.FAILED,
    )
    with pytest.raises(Phase7AuthorityError, match="changed before expected|Terminal run"):
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FAILED,
        )
    repository.close()


def test_run_load_rejects_tampered_case_identity(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "phase7.db")
    snapshot_id = make_snapshot(repository)
    context = repository.seal_phase7_context(
        "asm_context",
        snapshot_id=snapshot_id,
        manifest=make_manifest(phase6_snapshot_id=snapshot_id),
    )
    run = repository.begin_phase7_run(context.context_id, attempt_token="tamper")
    with repository.engine.begin() as connection:
        document = connection.execute(
            text("SELECT document_json FROM phase7_runs WHERE run_id = :run_id"),
            {"run_id": run.run_id},
        ).scalar_one()
        connection.execute(
            text("UPDATE phase7_runs SET document_json = :document WHERE run_id = :run_id"),
            {"document": document.replace(run.case_id, "p7case_forged"), "run_id": run.run_id},
        )
    with pytest.raises(Phase7AuthorityError, match="run identity"):
        repository.load_phase7_run(run.run_id)
    repository.close()


def _insert_fixture_dependency(repository, run_id, kind, payload, *, execution=None):
    """Untrusted staged data: only freeze's revalidation can authorize it."""
    from sqlalchemy.orm import Session

    from novelty_harness.application.phase7_roles import make_phase7_artifact
    from novelty_harness.evidence.graph.phase7_models import Phase7ArtifactRow
    from novelty_harness.runtime.tracing.hashing import canonical_json

    artifact = make_phase7_artifact(run_id, kind, payload, execution=execution)
    with Session(repository.engine) as session, session.begin():
        session.add(
            Phase7ArtifactRow(
                artifact_id=artifact.artifact_id,
                run_id=run_id,
                context_id=artifact.assessment_context_id,
                assessment_id=artifact.assessment_id,
                snapshot_id=artifact.phase6_snapshot_id,
                kind=kind,
                target_id=artifact.target_id,
                document_json=canonical_json(artifact),
            )
        )
    return artifact.artifact_id


def _freeze_fixture(tmp_path, *, all_unassessable=False, observation_clock=None):
    import asyncio
    import json
    from datetime import UTC, datetime

    from novelty_harness.adjudication.frozen import (
        FrozenAdjudication,
        LanguagePermissionClass,
        compose_assessment,
        phase7_frozen_id,
    )
    from novelty_harness.adjudication.gates import (
        evaluate_gate_a,
        evaluate_gate_b,
        evaluate_gate_c,
        evaluate_gate_d,
    )
    from novelty_harness.adjudication.judge import (
        JudgeStability,
        compare_counterbalance,
        resolve_judge_comparisons,
    )
    from novelty_harness.adjudication.models import TargetRef
    from novelty_harness.adjudication.packet import build_adjudication_case
    from novelty_harness.adjudication.policy import VerdictPermissionPolicy
    from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase
    from novelty_harness.application.phase7_roles import run_neutral_judging
    from novelty_harness.domain.enums import SufficiencyState
    from tests.fixtures.phase7_execution import executed_artifact
    from tests.unit.adjudication.test_judge import _judging_fixture, _scripted_judge
    from tests.unit.adjudication.test_roles import scope

    packet, repository, run, prosecution, _, disputes, facts = _judging_fixture(
        tmp_path, observation_clock=observation_clock
    )
    judge = _scripted_judge(packet, prosecution)
    if all_unassessable:
        manifest = packet.manifest.model_copy(
            update={
                "sufficiency": packet.manifest.sufficiency.model_copy(
                    update={"state": SufficiencyState.INSUFFICIENT}
                )
            }
        )
        context = repository.seal_phase7_context(
            packet.assessment_id,
            snapshot_id=packet.phase6_snapshot_id,
            manifest=manifest,
            parent_context_id=packet.assessment_context_id,
        )
        packet = build_adjudication_case(
            context,
            repository.load_phase6_assessment(
                packet.assessment_id, snapshot_id=packet.phase6_snapshot_id
            ),
        )
        run = repository.begin_phase7_run(context.context_id, attempt_token="unassessable")
        for target_id in sorted(packet.target_ids):
            cases = (
                ProsecutionCase(
                    **scope(packet, target_id), case_id=f"p7pro_{target_id}", challenges=()
                ),
                DefenseCase(**scope(packet, target_id), case_id=f"p7def_{target_id}", points=()),
            )
            for kind, case in zip(("PROSECUTION_CASE", "DEFENSE_CASE"), cases, strict=True):
                repository.record_phase7_artifact(
                    run.run_id,
                    executed_artifact(repository, run.run_id, kind, case),
                )
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FIRST_PASSES_COMPLETE,
        )
        asyncio.run(run_neutral_judging(run.run_id, packet, (), {}, judge, repository))
        judge_runs = ()
        comparisons = ()
        resolutions = ()
    else:
        judge_runs = asyncio.run(
            run_neutral_judging(run.run_id, packet, disputes, facts, judge, repository)
        )
        comparison = compare_counterbalance(*judge_runs)
        resolution = resolve_judge_comparisons(comparison, None)
        _insert_fixture_dependency(repository, run.run_id, "JUDGE_RESOLUTION", resolution)
        comparisons = (comparison,)
        resolutions = (resolution,)
    findings = []
    qualification_ids = []
    input_need_ids = []
    for profile in sorted(packet.target_profiles, key=lambda p: p.target_id):
        target = TargetRef(kind=profile.target_kind, id=profile.target_id)
        witness = (
            judge_runs[0].finding
            if judge_runs and profile.target_id == judge_runs[0].target_id
            else None
        )
        gate_a, needs = evaluate_gate_a(packet, target)
        gates = (
            gate_a,
            evaluate_gate_b(packet, target),
            evaluate_gate_c(packet, target, witness),
            evaluate_gate_d(packet, target, witness, None),
        )
        robustness, domain = repository.load_phase7_qualifications(
            packet.assessment_context_id, target
        )
        for kind, payload in zip(("GATE_A", "GATE_B", "GATE_C", "GATE_D"), gates, strict=True):
            _insert_fixture_dependency(repository, run.run_id, kind, payload)
        for kind, payload in (
            ("ROBUSTNESS_QUALIFICATION", robustness),
            ("DOMAIN_QUALIFICATION", domain),
        ):
            _insert_fixture_dependency(repository, run.run_id, kind, payload)
            qualification_ids.append(payload.qualification_id)
        for need in needs:
            _insert_fixture_dependency(repository, run.run_id, "INPUT_NEED", need)
            input_need_ids.append(need.need_id)
        findings.append(
            VerdictPermissionPolicy().evaluate(
                packet=packet,
                gate_a=gates[0],
                gate_b=gates[1],
                gate_c=gates[2],
                gate_d=gates[3],
                stability=JudgeStability.STABLE,
                robustness=robustness,
                domain=domain,
            )
        )
    targets = tuple(findings)
    expected = tuple(TargetRef(kind=f.target_kind, id=f.target_id) for f in targets)
    overall = compose_assessment(targets, expected)
    artifacts = repository.load_phase7_artifacts(run.run_id)
    permitted = {permission for f in targets for permission in f.language_permission}
    if overall.verdict.value == "MIXED_CONTRIBUTION_SPECIFIC":
        permitted.add(LanguagePermissionClass.MIXED_BY_TARGET)
    proposed = FrozenAdjudication(
        assessment_id=packet.assessment_id,
        assessment_context_id=packet.assessment_context_id,
        phase6_snapshot_id=packet.phase6_snapshot_id,
        adjudication_id="pending",
        run_id=run.run_id,
        case_id=packet.case_id,
        as_of=packet.as_of,
        frozen_at=datetime(2026, 10, 4, tzinfo=UTC),
        target_findings=targets,
        overall_finding=overall,
        expected_targets=expected,
        dependency_ids=tuple(sorted(a.artifact_id for a in artifacts)),
        role_case_ids=tuple(
            sorted(
                a.artifact_id for a in artifacts if a.kind in {"PROSECUTION_CASE", "DEFENSE_CASE"}
            )
        ),
        input_need_ids=tuple(sorted(input_need_ids)),
        qualification_ids=tuple(sorted(qualification_ids)),
        judge_run_ids=tuple(sorted(r.run_id for r in judge_runs)),
        counterbalance_comparison_ids=tuple(sorted(c.comparison_id for c in comparisons)),
        judge_resolution_ids=tuple(sorted(r.resolution_id for r in resolutions)),
        permitted_language=tuple(sorted(permitted)),
        limiting_factors=tuple(
            sorted(
                {
                    *overall.limiting_factors,
                    *(limit for r in resolutions for limit in r.limiting_factors),
                }
            )
        ),
        unresolved_questions=tuple(
            sorted(
                {
                    *packet.manifest.remaining_gaps,
                    *packet.manifest.cir.unknowns,
                    *(
                        question
                        for a in artifacts
                        if a.kind in {"GATE_A", "GATE_B", "GATE_C", "GATE_D"}
                        for question in json.loads(a.document_json)["unresolved_questions"]
                    ),
                }
            )
        ),
    )
    return (
        packet,
        repository,
        run,
        proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)}),
    )


def _assert_no_frozen_rows(repository):
    with repository.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM phase7_frozen_manifests")).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM phase7_frozen_dependencies")).scalar_one()
            == 0
        )


def test_freeze_recomputes_verdict_permission(tmp_path) -> None:
    from novelty_harness.adjudication.frozen import compose_assessment, phase7_frozen_id
    from novelty_harness.domain.enums import VerdictState

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        strongest = proposed.target_findings[0].model_copy(
            update={"verdict": VerdictState.STRONG_EVIDENCE_OF_NOVELTY}
        )
        changed = (strongest, *proposed.target_findings[1:])
        forged = proposed.model_copy(
            update={
                "target_findings": changed,
                "overall_finding": compose_assessment(changed, proposed.expected_targets),
            }
        )
        forged = forged.model_copy(update={"adjudication_id": phase7_frozen_id(forged)})
        with pytest.raises(ValueError, match="permission|verdict|qualification"):
            repository.freeze_phase7_adjudication(run.run_id, forged)
        _assert_no_frozen_rows(repository)
        assert (
            repository.freeze_phase7_adjudication(run.run_id, proposed) == proposed.adjudication_id
        )
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.FROZEN
        assert (
            repository.freeze_phase7_adjudication(run.run_id, proposed) == proposed.adjudication_id
        )
    finally:
        repository.close()


@pytest.mark.parametrize("attack", ("relation", "passage"))
def test_freeze_rolls_back_on_missing_passage_or_relation(tmp_path, attack) -> None:
    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        with repository.engine.begin() as connection:
            if attack == "relation":
                connection.execute(
                    text("DELETE FROM phase6_graph_edge_memberships WHERE edge_id=:id"),
                    {"id": packet.authorized_relations[0].edge.edge_id},
                )
            else:
                import json

                edge_id = packet.comparisons[0].comparison.comparison.chain.edge.edge_id
                document = json.loads(
                    connection.execute(
                        text("SELECT document_json FROM verified_chains WHERE edge_id=:id"),
                        {"id": edge_id},
                    ).scalar_one()
                )
                document["bundle"]["passages"] = []
                connection.execute(
                    text("UPDATE verified_chains SET document_json=:doc WHERE edge_id=:id"),
                    {"id": edge_id, "doc": json.dumps(document)},
                )
        with pytest.raises(ValueError):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


@pytest.mark.parametrize("attack", ("context", "policy", "method"))
def test_freeze_rejects_stale_context_or_policy(tmp_path, attack) -> None:
    _, repository, run, proposed = _freeze_fixture(tmp_path)
    forged = proposed.model_copy(
        update={"assessment_context_id": "foreign"}
        if attack == "context"
        else {"policy_version" if attack == "policy" else "method_version": "stale-policy"}
    )
    try:
        with pytest.raises(ValueError):
            repository.freeze_phase7_adjudication(run.run_id, forged)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


def test_freeze_rejects_missing_high_impact_pair(tmp_path) -> None:
    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.adjudication.judge import CounterbalanceRun

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        artifacts = repository.load_phase7_artifacts(run.run_id)
        second = next(
            a
            for a in artifacts
            if a.kind == "JUDGE_RUN"
            and CounterbalanceRun.model_validate_json(a.document_json).order == ("B", "A")
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase7_artifacts WHERE artifact_id=:id"),
                {"id": second.artifact_id},
            )
        removed = CounterbalanceRun.model_validate_json(second.document_json)
        proposed = proposed.model_copy(
            update={
                "dependency_ids": tuple(
                    ref for ref in proposed.dependency_ids if ref != second.artifact_id
                ),
                "judge_run_ids": tuple(
                    ref for ref in proposed.judge_run_ids if ref != removed.run_id
                ),
            }
        )
        proposed = proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)})
        with pytest.raises(ValueError, match="pair"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


@pytest.mark.parametrize("attack", ("single_alternate", "voted_resolution", "omitted_candidate"))
def test_freeze_rejects_alternate_single_call_or_voted_result(tmp_path, attack) -> None:
    from novelty_harness.adjudication.judge import CounterbalanceRun
    from novelty_harness.adjudication.models import Phase7Artifact
    from novelty_harness.runtime.tracing.hashing import canonical_json

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        artifacts = repository.load_phase7_artifacts(run.run_id)
        if attack == "single_alternate":
            first = CounterbalanceRun.model_validate_json(
                next(a.document_json for a in artifacts if a.kind == "JUDGE_RUN")
            )
            alternate = first.model_copy(
                update={"model_config_id": "alternate", "run_id": "p7judge_unpaired"}
            )
            _insert_fixture_dependency(repository, run.run_id, "JUDGE_RUN", alternate)
        else:
            selected = next(
                a
                for a in artifacts
                if a.kind == ("JUDGE_RESOLUTION" if attack == "voted_resolution" else "DISPUTE")
            )
            import json

            document = json.loads(selected.document_json)
            if attack == "voted_resolution":
                document["majority_vote"] = True
            else:
                document["candidates"] = document["candidates"][:1]
            mutated = selected.model_copy(update={"document_json": canonical_json(document)})
            assert isinstance(mutated, Phase7Artifact)
            with repository.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE phase7_artifacts SET document_json=:document WHERE artifact_id=:id"
                    ),
                    {"document": canonical_json(mutated), "id": selected.artifact_id},
                )
        with pytest.raises(ValueError):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


def test_freeze_accepts_unassessable_without_operational_failure(tmp_path) -> None:
    from novelty_harness.domain.enums import VerdictState

    _, repository, run, proposed = _freeze_fixture(tmp_path, all_unassessable=True)
    try:
        assert proposed.overall_finding.verdict == VerdictState.UNASSESSABLE
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.ABSTAINED
    finally:
        repository.close()


def test_context_reopen_works_with_in_memory_shared_connection() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    try:
        snapshot_id = make_snapshot(repository)
        context = repository.seal_phase7_context(
            "asm_context",
            snapshot_id=snapshot_id,
            manifest=make_manifest(phase6_snapshot_id=snapshot_id),
        )
        assert (
            repository.load_phase7_context("asm_context", context_id=context.context_id) == context
        )
    finally:
        repository.close()


def test_public_store_accepts_typed_freeze_dependencies(tmp_path) -> None:
    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        for artifact in repository.load_phase7_artifacts(run.run_id):
            if artifact.kind in {
                "JUDGE_RESOLUTION",
                "GATE_A",
                "GATE_B",
                "GATE_C",
                "GATE_D",
                "ROBUSTNESS_QUALIFICATION",
                "DOMAIN_QUALIFICATION",
            }:
                assert (
                    repository.record_phase7_artifact(run.run_id, artifact) == artifact.artifact_id
                )
        repository.freeze_phase7_adjudication(run.run_id, proposed)
    finally:
        repository.close()


@pytest.mark.parametrize("attack", ("limits", "questions", "history"))
def test_freeze_cannot_erase_limitations_or_invent_history(tmp_path, attack) -> None:
    from novelty_harness.adjudication.frozen import phase7_frozen_id

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    changes = {
        "limits": {"limiting_factors": ()},
        "questions": {"unresolved_questions": ("invented authoritative conclusion",)},
        "history": {"superseded_context_ids": ("p7ctx_invented",)},
    }[attack]
    forged = proposed.model_copy(update=changes)
    forged = forged.model_copy(update={"adjudication_id": phase7_frozen_id(forged)})
    try:
        with pytest.raises(ValueError, match="limitations|questions|history"):
            repository.freeze_phase7_adjudication(run.run_id, forged)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


def test_freeze_rejects_posthoc_primary_alternate_swap(tmp_path) -> None:
    import asyncio

    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.adjudication.judge import (
        CounterbalanceComparison,
        compare_counterbalance,
        resolve_judge_comparisons,
    )
    from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase, material_disputes
    from novelty_harness.application.phase7_roles import run_neutral_judging
    from tests.unit.adjudication.test_judge import _scripted_judge

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        artifacts = repository.load_phase7_artifacts(run.run_id)
        prosecution = next(
            ProsecutionCase.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "PROSECUTION_CASE"
            and ProsecutionCase.model_validate_json(a.document_json).challenges
        )
        defense = next(
            DefenseCase.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "DEFENSE_CASE" and a.target_id == prosecution.target_id
        )
        # Reuse the immutable packet gates required by the pure consequence classifier.
        from novelty_harness.adjudication.gates import (
            evaluate_gate_a,
            evaluate_gate_b,
            evaluate_gate_c,
            evaluate_gate_d,
        )
        from novelty_harness.adjudication.judge import GateFacts
        from novelty_harness.adjudication.models import TargetRef

        target = TargetRef(kind="MCU", id=prosecution.target_id)
        robustness, domain = repository.load_phase7_qualifications(
            packet.assessment_context_id, target
        )
        facts = GateFacts(
            gate_a=evaluate_gate_a(packet, target)[0],
            gate_b=evaluate_gate_b(packet, target),
            undisputed_c=evaluate_gate_c(packet, target, None),
            undisputed_d=evaluate_gate_d(packet, target, None, None),
            robustness=robustness,
            domain=domain,
        )
        alternate = _scripted_judge(packet, prosecution)
        alternate.model_config_id = "scripted-alternate-v1"
        pair = asyncio.run(
            run_neutral_judging(
                run.run_id,
                packet,
                material_disputes(prosecution, defense, packet),
                {target.id: facts},
                alternate,
                repository,
            )
        )
        original = next(
            CounterbalanceComparison.model_validate_json(a.document_json)
            for a in artifacts
            if a.kind == "COUNTERBALANCE_COMPARISON"
        )
        swapped = resolve_judge_comparisons(compare_counterbalance(*pair), original)
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase7_artifacts WHERE run_id=:run AND kind='JUDGE_RESOLUTION'"),
                {"run": run.run_id},
            )
        _insert_fixture_dependency(repository, run.run_id, "JUDGE_RESOLUTION", swapped)
        changed = proposed.model_copy(
            update={
                "dependency_ids": tuple(
                    sorted(a.artifact_id for a in repository.load_phase7_artifacts(run.run_id))
                ),
                "judge_run_ids": tuple(
                    sorted((*proposed.judge_run_ids, *(r.run_id for r in pair)))
                ),
                "counterbalance_comparison_ids": tuple(
                    sorted(
                        (
                            *proposed.counterbalance_comparison_ids,
                            compare_counterbalance(*pair).comparison_id,
                        )
                    )
                ),
                "judge_resolution_ids": (swapped.resolution_id,),
            }
        )
        changed = changed.model_copy(update={"adjudication_id": phase7_frozen_id(changed)})
        with pytest.raises(ValueError, match="designation"):
            repository.freeze_phase7_adjudication(run.run_id, changed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


def test_freeze_dependency_insert_failure_rolls_back_terminal_state(tmp_path) -> None:
    from sqlalchemy.exc import IntegrityError

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        with repository.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER reject_dependency BEFORE INSERT ON phase7_frozen_dependencies "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
            )
        with pytest.raises(IntegrityError, match="injected failure"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.JUDGING
    finally:
        repository.close()


def test_freeze_rejects_corrupted_transition_scope(tmp_path) -> None:
    import json

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        with repository.engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT transition_id,document_json FROM phase7_run_transitions "
                    "WHERE run_id=:run AND state='JUDGING'"
                ),
                {"run": run.run_id},
            ).one()
            document = json.loads(row.document_json)
            document["assessment_context_id"] = "forged-context"
            connection.execute(
                text(
                    "UPDATE phase7_run_transitions SET document_json=:doc WHERE transition_id=:id"
                ),
                {"doc": json.dumps(document), "id": row.transition_id},
            )
        with pytest.raises(ValueError, match="transition"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


@pytest.mark.parametrize("issuer", ("caller", "fixture:validated"))
def test_freeze_rejects_caller_or_fixture_qualified_record(tmp_path, issuer) -> None:
    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.adjudication.qualifications import RobustnessQualification

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        original = next(
            a
            for a in repository.load_phase7_artifacts(run.run_id)
            if a.kind == "ROBUSTNESS_QUALIFICATION"
        )
        qualification = RobustnessQualification.model_validate_json(original.document_json)
        qualification = qualification.model_copy(update={"status": "QUALIFIED", "issuer": issuer})
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase7_artifacts WHERE artifact_id=:id"),
                {"id": original.artifact_id},
            )
        _insert_fixture_dependency(
            repository, run.run_id, "ROBUSTNESS_QUALIFICATION", qualification
        )
        proposed = proposed.model_copy(
            update={
                "dependency_ids": tuple(
                    sorted(a.artifact_id for a in repository.load_phase7_artifacts(run.run_id))
                )
            }
        )
        proposed = proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)})
        with pytest.raises(ValueError, match="qualification"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        _assert_no_frozen_rows(repository)
    finally:
        repository.close()


def test_frozen_load_rejects_missing_dependency(tmp_path) -> None:
    from novelty_harness.adjudication.frozen import FrozenAdjudication

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        assert (
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
            == proposed
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM phase7_frozen_dependencies WHERE adjudication_id=:id "
                    "AND artifact_id=:artifact"
                ),
                {"id": proposed.adjudication_id, "artifact": proposed.dependency_ids[0]},
            )
        # Export still has a valid shape; it cannot replace the missing repository join.
        assert FrozenAdjudication.model_validate_json(proposed.model_dump_json()) == proposed
        with pytest.raises(ValueError, match="dependenc"):
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
    finally:
        repository.close()


@pytest.mark.parametrize("attack", ("graph", "context", "gate", "qualification", "terminal"))
def test_frozen_load_rejects_revoked_phase6_graph_authority(tmp_path, attack) -> None:
    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        with repository.engine.begin() as connection:
            if attack == "graph":
                connection.execute(
                    text("DELETE FROM phase6_graph_edge_memberships WHERE edge_id=:id"),
                    {"id": packet.authorized_relations[0].edge.edge_id},
                )
            elif attack == "context":
                connection.execute(
                    text(
                        "UPDATE phase7_assessment_contexts SET document_json='{}' "
                        "WHERE context_id=:id"
                    ),
                    {"id": proposed.assessment_context_id},
                )
            elif attack in {"gate", "qualification"}:
                kind = "GATE_C" if attack == "gate" else "ROBUSTNESS_QUALIFICATION"
                connection.execute(
                    text(
                        "UPDATE phase7_artifacts SET document_json='{}' "
                        "WHERE run_id=:id AND kind=:kind"
                    ),
                    {"id": run.run_id, "kind": kind},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE phase7_run_transitions SET document_json='{}' "
                        "WHERE run_id=:id AND state='FROZEN'"
                    ),
                    {"id": run.run_id},
                )
        with pytest.raises(ValueError):
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
    finally:
        repository.close()


def test_v7_migration_does_not_authorize_fixture_adjudication(tmp_path) -> None:
    repository = SqlAlchemyEvidenceGraphRepository(tmp_path / "no-phase7.sqlite3")
    try:
        with repository.engine.begin() as connection:
            connection.execute(text("UPDATE schema_version SET version=7"))
        assert ensure_schema(repository.engine) == 9
        with pytest.raises(ValueError, match="missing"):
            repository.load_frozen_adjudication("asm_fixture", adjudication_id="fixture-json-id")
    finally:
        repository.close()


def test_v8_reopen_and_exact_replay(tmp_path) -> None:
    _, repository, run, proposed = _freeze_fixture(tmp_path)
    path = repository.engine.url.database
    repository.freeze_phase7_adjudication(run.run_id, proposed)
    repository.close()
    reopened = SqlAlchemyEvidenceGraphRepository(path)
    try:
        assert (
            reopened.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
            == proposed
        )
        assert reopened.freeze_phase7_adjudication(run.run_id, proposed) == proposed.adjudication_id
        with pytest.raises(ValueError, match="foreign|missing"):
            reopened.load_frozen_adjudication(
                "other-assessment", adjudication_id=proposed.adjudication_id
            )
    finally:
        reopened.close()


def test_frozen_load_rejects_nonterminal_manifest(tmp_path) -> None:
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.phase7_models import (
        Phase7FrozenDependencyRow,
        Phase7FrozenManifestRow,
    )
    from novelty_harness.runtime.tracing.hashing import canonical_json

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        with Session(repository.engine) as session, session.begin():
            session.add(
                Phase7FrozenManifestRow(
                    adjudication_id=proposed.adjudication_id,
                    run_id=run.run_id,
                    context_id=proposed.assessment_context_id,
                    assessment_id=proposed.assessment_id,
                    snapshot_id=proposed.phase6_snapshot_id,
                    document_json=canonical_json(proposed),
                )
            )
            session.flush()
            session.add_all(
                Phase7FrozenDependencyRow(
                    adjudication_id=proposed.adjudication_id, artifact_id=artifact_id
                )
                for artifact_id in proposed.dependency_ids
            )
        with pytest.raises(ValueError, match="terminal"):
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
    finally:
        repository.close()


def test_frozen_manifest_row_must_match_document(tmp_path) -> None:
    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        repository.freeze_phase7_adjudication(run.run_id, proposed)
        other = repository.begin_phase7_run(
            proposed.assessment_context_id, attempt_token="another-run"
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("UPDATE phase7_frozen_manifests SET run_id=:run WHERE adjudication_id=:id"),
                {"run": other.run_id, "id": proposed.adjudication_id},
            )
        with pytest.raises(ValueError, match="manifest"):
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
    finally:
        repository.close()


def test_frozen_load_uses_one_explicit_read_transaction(tmp_path) -> None:
    from sqlalchemy import event

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    repository.freeze_phase7_adjudication(run.run_id, proposed)
    reads = []

    def inspect_read(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT"):
            driver = connection.connection.driver_connection
            reads.append((id(driver), driver.in_transaction, statement))

    event.listen(repository.engine, "before_cursor_execute", inspect_read)
    try:
        assert (
            repository.load_frozen_adjudication(
                proposed.assessment_id, adjudication_id=proposed.adjudication_id
            )
            == proposed
        )
        assert reads and len({entry[0] for entry in reads}) == 1
        assert all(entry[1] for entry in reads)
        assert any("phase6_assessment_snapshots" in entry[2] for entry in reads)
        assert any("phase7_frozen_dependencies" in entry[2] for entry in reads)
    finally:
        event.remove(repository.engine, "before_cursor_execute", inspect_read)
        repository.close()


def test_freeze_cannot_erase_role_case_limitation(tmp_path) -> None:
    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.adjudication.roles import ProsecutionCase

    _, repository, run, proposed = _freeze_fixture(tmp_path)
    try:
        original = next(
            a for a in repository.load_phase7_artifacts(run.run_id) if a.kind == "PROSECUTION_CASE"
        )
        case = ProsecutionCase.model_validate_json(original.document_json).model_copy(
            update={"limitations": ("material_role_scope_limitation",)}
        )
        with repository.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM phase7_artifacts WHERE artifact_id=:id"),
                {"id": original.artifact_id},
            )
        # Even a coherently forged execution must not erase a material limitation.
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        changed_id = _insert_fixture_dependency(
            repository,
            run.run_id,
            "PROSECUTION_CASE",
            case,
            execution=original.execution.model_copy(update={"proposal_hash": canonical_hash(case)}),
        )
        proposed = proposed.model_copy(
            update={
                "dependency_ids": tuple(
                    sorted(a.artifact_id for a in repository.load_phase7_artifacts(run.run_id))
                ),
                "role_case_ids": tuple(
                    sorted(
                        changed_id if ref == original.artifact_id else ref
                        for ref in proposed.role_case_ids
                    )
                ),
            }
        )
        proposed = proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)})
        with pytest.raises(ValueError, match="limitations"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
    finally:
        repository.close()


def test_terminal_run_rejects_new_research_artifact(tmp_path) -> None:
    from novelty_harness.adjudication.needs import ResearchGapRequest
    from novelty_harness.application.phase7_roles import make_phase7_artifact

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        run = repository.begin_phase7_run(packet.assessment_context_id)
        repository.transition_phase7_run(
            run.run_id, expected_state=Phase7RunState.CASE_BUILT, next_state=Phase7RunState.FAILED
        )
        request = ResearchGapRequest(
            assessment_id=packet.assessment_id,
            assessment_context_id=packet.assessment_context_id,
            phase6_snapshot_id=packet.phase6_snapshot_id,
            target_id=packet.target_profiles[0].target_id,
            request_id="p7gap_terminal",
            requesting_stage="FIRST_PASS",
            gap_type="COVERAGE",
            reason="A material external branch remains open",
            research_hypothesis="The branch may contain the claimed configuration",
            material_gate="B",
            stop_condition="TEST_BRANCH",
        )
        with pytest.raises(Phase7AuthorityError, match="active"):
            repository.record_phase7_artifact(
                run.run_id, make_phase7_artifact(run.run_id, "RESEARCH_GAP", request)
            )
    finally:
        repository.close()


def test_neutral_scope_research_can_link_committed_position_ids(tmp_path) -> None:
    from novelty_harness.adjudication.needs import ResearchGapRequest
    from novelty_harness.adjudication.roles import (
        DefenseCase,
        ProsecutionCase,
        neutral_review_issues,
    )
    from novelty_harness.application.phase7_roles import make_phase7_artifact
    from tests.fixtures.phase7_execution import executed_artifact
    from tests.unit.adjudication.test_roles import scope

    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        run = repository.begin_phase7_run(packet.assessment_context_id)
        for target_id in sorted(packet.target_ids):
            prosecutor = ProsecutionCase(
                **scope(packet, target_id), case_id="p7pro_empty_" + target_id, challenges=()
            )
            defender = DefenseCase(
                **scope(packet, target_id), case_id="p7def_empty_" + target_id, points=()
            )
            for kind, proposal in (("PROSECUTION_CASE", prosecutor), ("DEFENSE_CASE", defender)):
                repository.record_phase7_artifact(
                    run.run_id, executed_artifact(repository, run.run_id, kind, proposal)
                )
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.CASE_BUILT,
            next_state=Phase7RunState.FIRST_PASSES_COMPLETE,
        )
        target_id = "mcu_control"
        prosecutor = ProsecutionCase(
            **scope(packet, target_id), case_id="p7pro_empty_" + target_id, challenges=()
        )
        defender = DefenseCase(
            **scope(packet, target_id), case_id="p7def_empty_" + target_id, points=()
        )
        issue = neutral_review_issues(prosecutor, defender, packet)[0]
        repository.record_phase7_artifact(
            run.run_id, make_phase7_artifact(run.run_id, "DISPUTE", issue)
        )
        request = ResearchGapRequest(
            **scope(packet, target_id),
            request_id="p7gap_position",
            requesting_stage="ADJUDICATION",
            gap_type="CHRONOLOGY",
            material_gate="C",
            reason="Prior-art chronology remains unresolved",
            research_hypothesis="A dated version might resolve chronology",
            stop_condition="VERIFY_DATE",
            linked_argument_ids=issue.argument_ids,
        )
        artifact = make_phase7_artifact(run.run_id, "RESEARCH_GAP", request)
        assert repository.record_phase7_artifact(run.run_id, artifact) == artifact.artifact_id
    finally:
        repository.close()

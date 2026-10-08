"""Strict report shape factories. These objects confer no repository authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novelty_harness.adjudication.frozen import FrozenAdjudication
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from novelty_harness.reporting.bundle import ReportInputBundle

OBSERVED = datetime(2026, 10, 5, tzinfo=UTC)


def report_scope():
    from novelty_harness.reporting.models import ReportScope

    return ReportScope(
        assessment_id="asm_report_shapes",
        adjudication_id="p7frozen_shapes",
        assessment_context_id="p7ctx_shapes",
        phase6_snapshot_id="p6snap_shapes",
    )


def report_configuration(*, model="recorded-model"):
    from novelty_harness.reporting.execution import (
        ReportCompilationConfiguration,
        ReportPortConfiguration,
        approved_role_configuration,
    )
    from novelty_harness.reporting.models import ReportSemanticRole

    port = ReportPortConfiguration(
        mode="PORT_PROTOCOL", implementation="recorded-port", model=model
    )
    return ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(report_scope(), "p8run_shapes", role, port)
            for role in ReportSemanticRole
        )
    )


@dataclass(frozen=True)
class ReportCase:
    """Test-owned references to genuinely frozen and repository-loaded authority."""

    repository: SqlAlchemyEvidenceGraphRepository
    frozen: FrozenAdjudication
    bundle: ReportInputBundle


def make_report_case(
    path: Path, *, unassessable: bool = False, observe=None, observation_clock=None
) -> ReportCase:
    from tests.fixtures.sqlite_baselines import _timed
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    repository = None
    try:
        with _timed("upstream_construction", observe):
            packet, repository, run, proposed = _freeze_fixture(
                path, all_unassessable=unassessable, observation_clock=observation_clock
            )
        with _timed("native_freeze", observe):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
        with _timed("native_frozen_load", observe):
            frozen = repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=proposed.adjudication_id
            )
        with _timed("native_bundle_load", observe):
            bundle = repository.load_report_input_bundle(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
        return ReportCase(repository, frozen, bundle)
    except BaseException:
        if repository is not None:
            repository.close()
        raise


def make_report_scenario(path: Path, scenario: str) -> ReportCase:
    """Build native commits and recorded Phase7 findings, then reopen authoritative locators."""
    if scenario in {"BUDGET_STOPPED", "PROVIDER_BLOCKED", "NO_NEW_YIELD"}:
        from unittest.mock import patch

        from novelty_harness.adjudication.context import Phase7InputManifest
        from novelty_harness.runtime.budgets.controller import BudgetUsage

        def manifest(**values):
            # Alter the input before repository sealing, never a loaded authority projection.
            values.update(
                stop_reason=scenario,
                budget_usage=BudgetUsage(provider_calls=7),
                query_history=("recorded-zero-yield-query",),
                providers_attempted=("recorded-provider",),
                access_failures=("recorded-source-unavailable",),
                remaining_gaps=("relationship evidence remains incomplete",),
            )
            return Phase7InputManifest(**values)

        with patch("tests.unit.adjudication.test_roles.Phase7InputManifest", side_effect=manifest):
            return make_report_case(path)
    if scenario in {"LIMITED", "ZERO_YIELD_SUCCESSOR"}:
        from dataclasses import replace
        from unittest.mock import patch

        from novelty_harness.domain.enums import SufficiencyState
        from tests.fixtures.phase1 import make_fixture
        from tests.integration.test_phase7_slice import (
            _run_material_gap_case,
            test_semantic_input_need_freezes_clarification_without_research,
        )

        if scenario == "LIMITED":
            fixture = make_fixture()
            limited = replace(
                fixture,
                sufficiency=fixture.sufficiency.model_copy(
                    update={"state": SufficiencyState.EXPLORATORY}
                ),
            )
            with patch("tests.unit.adjudication.test_roles.make_fixture", return_value=limited):
                test_semantic_input_need_freezes_clarification_without_research(path, "FIRST_PASS")
        else:
            _run_material_gap_case(path, "changed")
        return load_report_case(path)
    if scenario == "M1":
        from dataclasses import replace
        from unittest.mock import patch

        from novelty_harness.domain.enums import ValueMaturity
        from tests.fixtures.phase1 import make_fixture

        fixture = make_fixture()
        idea = fixture.idea.model_copy(
            update={
                "claimed_advantages": tuple(
                    a.model_copy(update={"maturity": ValueMaturity.DEMONSTRATED})
                    for a in fixture.idea.claimed_advantages
                )
            }
        )
        # Replace the test normalizer input BEFORE native context sealing/freeze.
        # The label remains attributed; no value validation basis is produced.
        with patch(
            "tests.unit.adjudication.test_roles.make_fixture",
            return_value=replace(fixture, idea=idea),
        ):
            return make_report_case(path)
    if scenario in {"MIXED", "UNASSESSABLE"}:
        return make_report_case(path, unassessable=scenario == "UNASSESSABLE")
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.phase7_models import Phase7FrozenManifestRow
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from tests.integration.test_phase6_evidence_pipeline import graph_database
    from tests.integration.test_phase7_slice import (
        test_real_phase7_slice_supports_direct_partial_and_combination,
    )

    kind = "PARTIAL_POTENTIAL" if scenario == "POTENTIAL" else scenario
    if kind not in {"DIRECT", "PARTIAL_NEGATIVE", "PARTIAL_POTENTIAL"}:
        raise ValueError("unknown real report scenario")
    test_real_phase7_slice_supports_direct_partial_and_combination(path, kind)
    repository = SqlAlchemyEvidenceGraphRepository(
        graph_database(path) if kind == "DIRECT" else path / "STRONG_PARTIAL_PRECEDENT.sqlite"
    )
    try:
        with Session(repository.engine) as session:
            row = session.scalars(select(Phase7FrozenManifestRow)).one()
            assessment_id, adjudication_id = row.assessment_id, row.adjudication_id
        frozen = repository.load_frozen_adjudication(assessment_id, adjudication_id=adjudication_id)
        bundle = repository.load_report_input_bundle(assessment_id, adjudication_id=adjudication_id)
        return ReportCase(repository, frozen, bundle)
    except Exception:
        repository.close()
        raise


def load_report_case(path: Path) -> ReportCase:
    """Reload the sole actual accepted adjudication in an upstream integration fixture."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from novelty_harness.evidence.graph.phase7_models import Phase7FrozenManifestRow
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from tests.integration.test_phase6_evidence_pipeline import graph_database

    repository = SqlAlchemyEvidenceGraphRepository(graph_database(path))
    try:
        with Session(repository.engine) as session:
            row = session.scalars(select(Phase7FrozenManifestRow)).one()
            assessment_id, adjudication_id = row.assessment_id, row.adjudication_id
        frozen = repository.load_frozen_adjudication(assessment_id, adjudication_id=adjudication_id)
        bundle = repository.load_report_input_bundle(assessment_id, adjudication_id=adjudication_id)
        return ReportCase(repository, frozen, bundle)
    except Exception:
        repository.close()
        raise

"""Actual bound state is retained without saturation or novelty inference."""

import pytest

from novelty_harness.reporting.models import AuthorityKind, AuthorityRef
from novelty_harness.runtime.budgets.controller import BudgetUsage
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


@pytest.mark.parametrize("stop", ["BUDGET_STOPPED", "NO_NEW_YIELD", "PROVIDER_BLOCKED"])
def test_uncertainty_preserves_budget_no_yield_provider_and_ancestor_scope(report_case, stop):
    from novelty_harness.reporting.uncertainty import project_uncertainty
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    bundle = report_case.bundle
    manifest = bundle.research_state.model_copy(
        update={
            "stop_reason": stop,
            "budget_usage": BudgetUsage(provider_calls=7),
            "query_history": ("zero-yield-query",),
            "providers_attempted": ("blocked-provider",),
            "access_failures": ("source-unavailable",),
            "remaining_gaps": ("relationship evidence",),
        }
    )
    ancestor = AuthorityRef(
        kind=AuthorityKind.SUPERSESSION,
        native_id="p7ctx_ancestor",
        digest=canonical_hash("historical context"),
        scope=bundle.scope,
    )
    closure = bundle.judge_resolutions_and_limitations.model_copy(
        update={"superseded_context_refs": (ancestor,)}
    )
    # Pure projection tests intentionally do not grant this caller variant authority.
    items = project_uncertainty(
        bundle.model_copy(
            update={
                "research_state": manifest,
                "judge_resolutions_and_limitations": closure,
            }
        )
    )
    assert any(i.state == stop for i in items)
    assert any("7" in i.reason and i.upstream_kind == "BUDGET_USAGE" for i in items)
    assert any("zero-yield-query" in i.reason for i in items)
    assert any("source-unavailable" in i.reason for i in items)
    history = [i for i in items if ancestor in i.authority_refs]
    assert history and all(i.historical and i.target is None for i in history)
    assert not any(i.state == "SATURATED" for i in items)
    assert bundle.target_findings == report_case.frozen.target_findings


def test_actual_unknowns_and_material_limits_keep_exact_field_identity(report_case):
    from novelty_harness.reporting.uncertainty import project_uncertainty
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    bundle = report_case.bundle
    items = project_uncertainty(bundle)
    assert any(i.state == "UNKNOWN" for i in items)
    for target in bundle.target_findings:
        for limit in target.limiting_factors:
            assert any(
                i.target
                and i.target.id == target.target_id
                and any(r.digest == canonical_hash(limit) for r in i.authority_refs)
                for i in items
            ), limit
    assert len({i.uncertainty_id for i in items}) == len(items)


def test_role_input_and_missing_value_limitations_remain_explicit(report_case):
    from novelty_harness.reporting.uncertainty import project_uncertainty

    bundle = report_case.bundle
    closure = bundle.judge_resolutions_and_limitations
    first = closure.role_cases[0].model_copy(
        update={"limitations": ("Cannot compare causal effect",)}
    )
    variant = bundle.model_copy(
        update={
            "cir": bundle.cir.model_copy(update={"unknowns": ("Timing behavior unspecified",)}),
            "judge_resolutions_and_limitations": closure.model_copy(
                update={
                    "role_cases": (first, *closure.role_cases[1:]),
                }
            ),
        }
    )
    items = project_uncertainty(variant)
    assert any(
        i.reason == "Cannot compare causal effect" and i.upstream_kind == "ROLE_LIMITATION"
        for i in items
    )
    assert any(i.reason == "Timing behavior unspecified" and 1 in i.question_ids for i in items)
    assert any(
        i.state == "NO_VALUE_ASSESSMENT" and 6 in i.question_ids and 9 in i.question_ids
        for i in items
    )


def test_source_version_access_and_metadata_limits_are_retained(report_case):
    from novelty_harness.reporting.uncertainty import project_uncertainty

    bundle = report_case.bundle
    original = bundle.source_metadata[0]
    assert original.version is not None
    observed = original.model_copy(
        update={
            "source": original.source.model_copy(
                update={"limitations": ("Source translation incomplete",)}
            ),
            "version": original.version.model_copy(
                update={"limitations": ("Version appendix inaccessible",)}
            ),
        }
    )
    items = project_uncertainty(
        bundle.model_copy(
            update={
                "source_metadata": (observed, *bundle.source_metadata[1:]),
            }
        )
    )
    assert any(i.reason == "Source translation incomplete" for i in items)
    assert any(i.reason == "Version appendix inaccessible" for i in items)
    assert any(i.upstream_kind == "SOURCE_ACCESS_STATE" for i in items)

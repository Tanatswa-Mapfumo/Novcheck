"""Golden fallback prose only; native scope/basis equality has separate exact checks."""

import json
import re
from pathlib import Path

import pytest

from tests.fixtures.phase8 import make_report_scenario
from tests.unit.reporting.test_fallback import public_text, sections_for
from tests.unit.reporting.test_rendering import ir_case as _ir_case
from tests.unit.reporting.test_rendering import report_case as _report_case
from tests.unit.reporting.test_rendering import report_shape as _report_shape

report_case = _report_case
ir_case = _ir_case
report_shape = _report_shape


def fallback_golden(sections):
    # Real run/context hashes contain observational upstream identities. Normalize
    # only hashed display identifiers and UTC retrieval observations. Publication
    # dates, cutoff dates, propositions, verdicts and limitations stay exact.
    normalized = []
    for section in sections:
        text = re.sub(r"\b(?:[a-z][a-z0-9_]*_)?[0-9a-f]{64}\b", "<native-id>", public_text(section))
        text = re.sub(
            r"\d{4}-\d{2}-\d{2}T\d{2}：\d{2}：\d{2}(?:\.\d+)?(?:Z|[+]00：00)",
            "<retrieval-observation-utc>",
            text,
        )
        normalized.append(text)
    return normalized


def assert_fallback_scenario_semantics(case, sections, scenario):
    """Independent scenario expectations precede normalized prose comparison."""
    from novelty_harness.adjudication.roles import DefenseCase
    from novelty_harness.reporting.fallback import attributed_text
    from novelty_harness.reporting.uncertainty import project_uncertainty

    bundle, frozen = case.bundle, case.frozen
    texts = [public_text(section) for section in sections]
    assert tuple(section.draft.question_id for section in sections) == tuple(range(1, 10))
    assert {
        home.obligation_id for section in sections for home in section.obligation_satisfaction
    } == {obligation.obligation_id for obligation in bundle.coverage_obligations}
    assert frozen.value_findings == frozen.novelty_significance == ()
    assert all(value.maturity is None for value in bundle.value_projection)
    assert "No authoritative value assessment is available" in texts[5]
    assert "Prospective validation recommendation; no result is established" in texts[6]
    assert "Unsupported example to avoid:" in texts[7]
    assert "This wording is not permitted" in texts[7]
    assert f"Cutoff: {bundle.as_of.isoformat()}" in texts[1]

    for finding in frozen.target_findings:
        claims = [
            claim
            for claim in sections[7].claims
            if claim.normalized_assertion.startswith(
                f"Accepted target {finding.target_id}: {finding.verdict.value}."
            )
        ]
        assert len(claims) == 1
        assert any(
            scope.target.id == finding.target_id and scope.claim_scope == finding.claim_scope
            for scope in claims[0].target_scopes
        )
        envelope = next(
            item for item in bundle.language_envelopes if item.target.id == finding.target_id
        )
        for limitation in envelope.required_limitations:
            assert (
                attributed_text("Attached limitation", limitation) in claims[0].normalized_assertion
            )
        assert set(envelope.permitted_classes) == set(finding.language_permission)

    # Compare raw IDs, target/scope joins and actual states BEFORE normalization
    # masks display hashes. This does not trust normalized prose as authority.
    q9 = sections[8]
    for item in project_uncertainty(bundle):
        prefix = (
            f"Uncertainty {item.uncertainty_id}: {item.upstream_kind}; "
            f"state {item.state}; historical={item.historical}. "
        )
        claims = [claim for claim in q9.claims if claim.normalized_assertion.startswith(prefix)]
        assert len(claims) == 1
        claim = claims[0]
        assert attributed_text("Recorded limitation", item.reason) in claim.normalized_assertion
        links = [link for link in q9.basis_links if link.claim_id == claim.claim_id]
        assert tuple(link.authority_ref for link in links) == item.authority_refs
        assert all(link.authority_ref.scope == bundle.scope for link in links)
        expected_scopes = tuple(
            (envelope.target, envelope.claim_scope)
            for envelope in bundle.language_envelopes
            if any(ref.target == envelope.target for ref in item.authority_refs)
        )
        assert (
            tuple((scope.target, scope.claim_scope) for scope in claim.target_scopes)
            == expected_scopes
        )

    gates = {gate.gate_id: gate for gate in bundle.gate_findings}
    verdicts = {finding.target_id: finding.verdict.value for finding in frozen.target_findings}
    if scenario in {"PARTIAL_NEGATIVE", "POTENTIAL"}:
        assert len(frozen.target_findings) == 1
        finding = frozen.target_findings[0]
        assert verdicts[finding.target_id] == (
            "NOT_NOVEL_AT_CLAIMED_LEVEL" if scenario == "PARTIAL_NEGATIVE" else "POTENTIALLY_NOVEL"
        )
        assert gates[finding.gate_c_id].state == "SUBSTANTIALLY_REPRODUCED_WITH_RESIDUAL_DELTA"
        assert gates[finding.gate_d_id].state == (
            "NON_SUBSTANTIVE" if scenario == "PARTIAL_NEGATIVE" else "SUBSTANTIVE"
        )
        classification = bundle.eligible_comparisons[0].comparison.classification
        assert classification.relation.value == "STRONG_PARTIAL_PRECEDENT"
        residual = {
            *classification.missing_elements,
            *classification.missing_relationships,
            *((classification.configuration_gap,) if classification.configuration_gap else ()),
        }
        assert residual
        for difference in residual:
            assert difference in texts[2]
        assert bundle.counterfactuals
        for localization in bundle.counterfactuals:
            assert localization.target_id == finding.target_id
            assert localization.removed_element in residual
            assert set(localization.remaining_differences) == residual - {
                localization.removed_element
            }
            assert localization.removed_element in texts[3]
            assert localization.substantial_equivalence_after_removal is True
    elif scenario == "UNASSESSABLE":
        assert set(verdicts.values()) == {"UNASSESSABLE"}
        assert "phase2_insufficient" in texts[8]
        assert all(
            gates[finding.gate_a_id].state == "INSUFFICIENT" for finding in frozen.target_findings
        )
        assert all(
            gates[finding.gate_d_id].state == "UNRESOLVED" for finding in frozen.target_findings
        )
    else:
        combinations = [
            profile for profile in bundle.target_profiles if profile.target_kind == "COMBINATION"
        ]
        assert len(combinations) == 1
        combination = combinations[0]
        assert set(combination.combination_members) == {"mcu_control", "mcu_status"}
        combination_finding = next(
            f for f in frozen.target_findings if f.target_id == combination.target_id
        )
        assert combination_finding.target_kind == "COMBINATION"
        assert combination_finding.claim_scope == combination.statement
        assert verdicts == {
            "mcu_control": "NOT_NOVEL_AT_CLAIMED_LEVEL",
            "mcu_status": "UNASSESSABLE",
            combination.target_id: "UNASSESSABLE",
        }
        assert (
            gates[
                next(f.gate_c_id for f in frozen.target_findings if f.target_id == "mcu_control")
            ].state
            == "DIRECT_ESTABLISHED"
        )
        defenses = [
            point
            for role in bundle.judge_resolutions_and_limitations.role_cases
            if isinstance(role, DefenseCase)
            for point in role.points
        ]
        expected_disposition = "CONCESSION" if scenario == "DIRECT" else "OBJECTION"
        assert any(point.disposition == expected_disposition for point in defenses)
        assert f"Recorded defense disposition: {expected_disposition}." in texts[4]
        if scenario == "M1":
            advantages = [
                value for value in bundle.value_projection if value.kind == "ATTRIBUTED_INPUT_CLAIM"
            ]
            assert advantages and all(
                value.attributed_maturity_label.value == "DEMONSTRATED" for value in advantages
            )
            assert "Submitter's claimed advantage; no assessed maturity" in texts[5]
            assert "DEMONSTRATED" in texts[5]


@pytest.mark.parametrize(
    "scenario",
    [
        "DIRECT",
        "PARTIAL_NEGATIVE",
        "POTENTIAL",
        "MIXED",
        "UNASSESSABLE",
        "M1",
    ],
)
def test_fallback_real_scenario_golden(tmp_path, scenario):
    from novelty_harness.reporting.execution import ReportCompilationConfiguration
    from novelty_harness.reporting.fallback import validate_fallback_section
    from novelty_harness.reporting.models import ReportOptions

    case = make_report_scenario(tmp_path, scenario)
    try:
        compilation = case.repository.begin_report_compilation(
            case.bundle.scope.assessment_id,
            adjudication_id=case.frozen.adjudication_id,
            options=ReportOptions(),
            configuration=ReportCompilationConfiguration(),
            attempt_token="golden",
        )
        sections = sections_for(case.bundle, compilation)
        for section in sections:
            validate_fallback_section(section, case.bundle, compilation)
        if scenario == "POTENTIAL":
            assert any(f.verdict.value == "POTENTIALLY_NOVEL" for f in case.frozen.target_findings)
        if scenario == "PARTIAL_NEGATIVE":
            assert case.bundle.eligible_comparisons[0].comparison.classification.relation.value == (
                "STRONG_PARTIAL_PRECEDENT"
            )
        assert_fallback_scenario_semantics(case, sections, scenario)
        golden = Path(__file__).parent / "phase8" / (scenario.lower() + ".json")
        actual = fallback_golden(sections)
        expected = json.loads(golden.read_text())
        assert len(actual) == len(expected) == 9
        for question, (observed, stored) in enumerate(zip(actual, expected, strict=True), 1):
            if observed != stored:
                offset = next(
                    (i for i, (a, b) in enumerate(zip(observed, stored)) if a != b),
                    min(len(observed), len(stored)),
                )
                pytest.fail(
                    f"Q{question} golden differs at {offset}: "
                    f"actual={observed[offset : offset + 120]!r}; "
                    f"stored={stored[offset : offset + 120]!r}"
                )
    finally:
        case.repository.close()


def format_public_projection(payload):
    """Golden facts omit observations, retaining scope/verdict/permission meaning."""
    ir = payload["ir"]
    projection = {
        "questions": [[s["question_id"], s["question_label"]] for s in ir["sections"]],
        "overall_verdict": ir["overall_finding"]["verdict"],
        "targets": [
            {
                key: f[key]
                for key in (
                    "target_id",
                    "target_kind",
                    "claim_scope",
                    "verdict",
                    "language_permission",
                    "limiting_factors",
                )
            }
            for f in ir["target_findings"]
        ],
        "value": [v["kind"] for v in ir["value_availability"]],
        "material_limitations": ir["report_limitations"],
        "citations": [
            {
                key: c[key]
                for key in (
                    "display_number",
                    "source_id",
                    "source_version_id",
                    "passage_id",
                    "locator",
                    "passage_access_state",
                    "limitations",
                    "canonical_page_is_versionless",
                    "unversioned_authority",
                )
            }
            for c in ir["citation_registry"]["citations"]
        ],
    }
    normalized = re.sub(
        r"\b(?:[a-z][a-z0-9_]*_)?[0-9a-f]{64}\b", "<native-id>", json.dumps(projection)
    )
    return json.loads(normalized)


def format_markdown_projection(markdown):
    # Fixed visible question labels, projection headings, reference and date
    # labels. Full prose has six independent native-scenario goldens above.
    selected = [
        line
        for line in markdown.splitlines()
        if line.startswith(
            (
                "## ",
                "### Reference ",
                "Publication date:",
                "Retrieval observation:",
                "Assessed cutoff:",
            )
        )
    ]
    text = "\n".join(selected) + "\n"
    text = re.sub(r"\d{4}\\-\d{2}\\-\d{2}T[^\n]+", "<retrieval-observation-utc>", text)
    return text


def test_rendered_format_public_projection_golden(report_shape):
    import yaml

    from novelty_harness.reporting.rendering import (
        render_compiled_report,
        validate_rendition_parity,
    )

    rendered = render_compiled_report(report_shape)
    validate_rendition_parity(report_shape, rendered)
    directory = Path(__file__).parent / "phase8"
    actual_json = format_public_projection(json.loads(rendered.json))
    actual_yaml = format_public_projection(yaml.safe_load(rendered.yaml))
    assert actual_json == actual_yaml
    assert actual_json == json.loads((directory / "rendering-public.json").read_text())
    assert actual_yaml == yaml.safe_load((directory / "rendering-public.yaml").read_text())
    assert (
        format_markdown_projection(rendered.markdown)
        == (directory / "rendering-public.md").read_text()
    )

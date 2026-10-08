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

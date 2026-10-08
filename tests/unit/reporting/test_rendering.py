"""Rendered exports retain visible findings and cannot activate untrusted markup."""

import hashlib
import json
import re
from dataclasses import replace

import pytest

from novelty_harness.reporting.models import ReportProposalError
from tests.unit.reporting.test_ir import build_ir, compiled_shape
from tests.unit.reporting.test_ir import ir_case as _ir_case
from tests.unit.reporting.test_ir import report_case as _report_case

report_case = _report_case
ir_case = _ir_case


@pytest.fixture(scope="module")
def report_shape(report_case, ir_case):
    # Actual upstream and local proof were committed; repository acceptance is
    # introduced at Task 19. This caller wrapper is not authoritative.
    return compiled_shape(build_ir(report_case, ir_case), ir_case)


def plain_markdown(value):
    return re.sub(r"\\([\\`*_{}\[\]()#+.!|<>~=: /-])", r"\1", value).replace("  \n", "\n")


def digest(report, rendition, kind, content):
    payload = json.dumps(
        {
            "report_id": report.report_id,
            "renderer_version": rendition.renderer_version,
            "format": kind,
            "content": content,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def test_all_formats_preserve_questions_scope_permissions_and_limitations(report_shape):
    import yaml

    from novelty_harness.reporting.rendering import (
        render_compiled_report,
        validate_rendition_parity,
    )

    report = report_shape
    rendered = render_compiled_report(report)
    validate_rendition_parity(report, rendered)
    assert (
        json.loads(rendered.json) == yaml.safe_load(rendered.yaml) == report.model_dump(mode="json")
    )
    assert tuple(map(int, re.findall(r"^## Q([1-9])\.", rendered.markdown, re.M))) == tuple(
        range(1, 10)
    )
    public = plain_markdown(rendered.markdown)
    for section in report.ir.sections:
        assert section.question_label in public
        for block in section.blocks:
            assert block.draft_block.text in public
    for finding in report.ir.target_findings:
        assert finding.target_id in public and finding.verdict.value in public
        for limitation in finding.limiting_factors:
            assert limitation in public
    for wording in report.ir.supported_and_qualified_wording:
        assert wording.claim_scope in public and wording.language_class.value in public
        assert wording.wording_text in public
        assert all(limit in public for limit in wording.necessary_limitations)
    for item in report.ir.uncertainty_summary:
        assert item.reason in public and item.state in public
    assert "NO_VALUE_ASSESSMENT" in public
    assert all(limit in public for limit in report.ir.report_limitations)
    for cite in report.ir.citation_registry.citations:
        assert f"(#reference-{cite.display_number})" in rendered.markdown
        assert cite.source_id in public and cite.passage_id in public
        assert cite.comparison_id in public and cite.commit_id in public
    for kind in ("json", "yaml", "markdown"):
        assert getattr(rendered, kind + "_digest") == digest(
            report, rendered, kind, getattr(rendered, kind)
        )


def test_markdown_missing_material_limit_fails_parity(report_shape):
    from novelty_harness.reporting.rendering import (
        render_compiled_report,
        validate_rendition_parity,
    )

    rendered = render_compiled_report(report_shape)
    # Removing visible Q9 content fails even after the attacker recomputes the
    # emitted-byte hash and leaves the full JSON/YAML untouched.
    start = rendered.markdown.index("## Q9.")
    end = rendered.markdown.index("## Findings", start)
    changed = rendered.markdown[:start] + rendered.markdown[end:]
    attack = replace(
        rendered,
        markdown=changed,
        markdown_digest=digest(report_shape, rendered, "markdown", changed),
    )
    with pytest.raises(ReportProposalError):
        validate_rendition_parity(report_shape, attack)


def changed_report(report, blocks):
    from novelty_harness.reporting.ir import report_id

    first = report.ir.sections[0].model_copy(update={"blocks": blocks})
    changed = report.model_copy(
        update={"ir": report.ir.model_copy(update={"sections": (first, *report.ir.sections[1:])})}
    )
    return changed.model_copy(update={"report_id": report_id(changed)})


def test_html_links_yaml_tags_and_source_citation_syntax_are_inert(report_shape):
    import yaml

    from novelty_harness.reporting.rendering import render_compiled_report

    raw = (
        "<script>alert(1)</script> [99](javascript:boom) ![x](data:image/x) "
        "!!python/object/apply:os.system"
    )
    original = report_shape.ir.sections[0].blocks[0]
    block = original.model_copy(
        update={
            "draft_block": original.draft_block.model_copy(
                update={"text": raw, "citation_tokens": ()}
            )
        }
    )
    report = changed_report(report_shape, (block,))
    rendered = render_compiled_report(report)
    assert "<script>" not in rendered.markdown
    assert "[99](javascript:boom)" not in rendered.markdown
    assert "![x](data:image/x)" not in rendered.markdown
    assert raw in plain_markdown(rendered.markdown)
    assert yaml.safe_load(rendered.yaml) == json.loads(rendered.json)
    assert (
        "!!python/object" not in rendered.yaml
        or "!!python/object"
        in yaml.safe_load(rendered.yaml)["ir"]["sections"][0]["blocks"][0]["draft_block"]["text"]
    )


def test_no_separate_semantic_call_per_format(report_shape, report_case, ir_case):
    from novelty_harness.reporting.rendering import render_compiled_report

    before = report_case.repository.load_report_artifacts(ir_case[0].compilation_id)
    one = render_compiled_report(report_shape)
    two = render_compiled_report(report_shape)
    assert one == two
    assert before == report_case.repository.load_report_artifacts(ir_case[0].compilation_id)
    assert one is not two


def test_markdown_table_cell_and_heading_escaping(report_shape):
    from novelty_harness.reporting.rendering import render_compiled_report

    original = report_shape.ir.sections[0].blocks[0]
    heading = original.model_copy(
        update={
            "draft_block": original.draft_block.model_copy(
                update={"kind": "HEADING", "text": "<b>Claim [99]</b>", "citation_tokens": ()}
            )
        }
    )
    cell = original.model_copy(
        update={
            "draft_block": original.draft_block.model_copy(
                update={
                    "kind": "TABLE_CELL",
                    "text": "A | B\n# hidden heading",
                    "table_id": "t",
                    "row": 0,
                    "column": 0,
                    "citation_tokens": (),
                }
            )
        }
    )
    rendered = render_compiled_report(changed_report(report_shape, (heading, cell)))
    assert "### \\<b\\>Claim \\[99\\]\\<\\/b\\>" in rendered.markdown
    assert "| A \\| B / \\# hidden heading |" in rendered.markdown
    assert "\n# hidden heading" not in rendered.markdown


def test_rendered_unsupported_example_cannot_look_permitted(report_shape):
    from novelty_harness.reporting.ir import report_id
    from novelty_harness.reporting.rendering import render_compiled_report

    example = report_shape.ir.supported_and_qualified_wording[0].model_copy(
        update={
            "use": "UNSUPPORTED_EXAMPLE",
            "wording_text": "Unsupported example to avoid: No prior art exists anywhere.",
            "violation_reason_codes": ("UNIVERSAL_ABSENCE",),
        }
    )
    report = report_shape.model_copy(
        update={
            "ir": report_shape.ir.model_copy(update={"unsupported_wording_examples": (example,)})
        }
    )
    report = report.model_copy(update={"report_id": report_id(report)})
    rendered = render_compiled_report(report)
    assert "## Unsupported wording examples" in rendered.markdown
    public = plain_markdown(rendered.markdown)
    for example in report.ir.unsupported_wording_examples:
        assert "Unsupported example to avoid:" in example.wording_text
        assert example.wording_text in public
        assert all(reason in public for reason in example.violation_reason_codes)


def test_unknown_metadata_and_unversioned_url_are_labeled(report_shape):
    from novelty_harness.reporting.rendering import render_compiled_report

    rendered = render_compiled_report(report_shape)
    public = plain_markdown(rendered.markdown)
    assert "Assessed cutoff:" in public
    assert "Publication date:" in public
    assert "Retrieval observation:" in public
    assert "not recorded" in public
    for citation in report_shape.ir.citation_registry.citations:
        if citation.canonical_page_is_versionless:
            assert "versionless canonical page" in public


def test_changed_json_or_executable_yaml_fails_parity(report_shape):
    from novelty_harness.reporting.rendering import (
        render_compiled_report,
        validate_rendition_parity,
    )

    rendered = render_compiled_report(report_shape)
    payload = json.loads(rendered.json)
    payload["ir"]["value_availability"] = []
    changed = json.dumps(payload)
    with pytest.raises(ReportProposalError):
        validate_rendition_parity(
            report_shape,
            replace(
                rendered, json=changed, json_digest=digest(report_shape, rendered, "json", changed)
            ),
        )
    with pytest.raises(ReportProposalError):
        validate_rendition_parity(
            report_shape,
            replace(rendered, yaml="!!python/object/apply:os.system ['echo injected']"),
        )


def test_unknown_renderer_version_fails_closed(report_shape):
    from novelty_harness.reporting.rendering import render_compiled_report

    with pytest.raises(ReportProposalError):
        render_compiled_report(report_shape, renderer_version="unregistered")


def test_unicode_styles_and_prose_reordering_keep_stable_reference_numbers(report_shape):
    from novelty_harness.reporting.drafts import InlineStyle
    from novelty_harness.reporting.rendering import render_compiled_report

    first = report_shape.ir.sections[0].blocks[0]
    styled = first.model_copy(
        update={
            "draft_block": first.draft_block.model_copy(
                update={
                    "text": "Café <x> `literal`",
                    "inline_styles": (
                        InlineStyle(start=0, end=4, style="STRONG"),
                        InlineStyle(start=5, end=8, style="EMPHASIS"),
                        InlineStyle(start=9, end=18, style="CODE"),
                    ),
                    "citation_tokens": (),
                }
            )
        }
    )
    report = changed_report(
        report_shape, (styled, *reversed(report_shape.ir.sections[0].blocks[1:]))
    )
    rendered = render_compiled_report(report)
    assert "**Café**" in rendered.markdown
    assert "*\\<x\\>*" in rendered.markdown
    assert "`` `literal` ``" in rendered.markdown
    original = render_compiled_report(report_shape).markdown
    assert rendered.markdown.split("## References", 1)[1] == original.split("## References", 1)[1]

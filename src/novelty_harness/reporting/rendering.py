"""Deterministic inert exports of one report; rendition bytes confer no authority."""

import json
import re
from dataclasses import dataclass
from typing import Literal, cast

import yaml
from pydantic import JsonValue

from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.reporting.citations import ReportCitation, resolve_citation_link
from novelty_harness.reporting.drafts import DraftBlock
from novelty_harness.reporting.ir import CompiledAssessmentReport, report_id
from novelty_harness.reporting.models import ReportProposalError, ReportScope
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


@dataclass(frozen=True)
class ReportRenditions:
    scope: ReportScope
    compilation_id: str
    json: str
    yaml: str
    markdown: str
    json_digest: str
    yaml_digest: str
    markdown_digest: str
    renderer_version: str = "p8-render-v1"
    contract_kind: Literal["phase8-report-renditions-v1"] = "phase8-report-renditions-v1"


def _escape(text: str, *, cell: bool = False) -> str:
    # Escape all Markdown punctuation capable of markup, images, autolinks,
    # headings or list syntax. Evidence URLs stay plain, including in GFM.
    escaped = re.sub(r"([\\`*_{}\[\]()#+.!|<>~=: /-])", r"\\\1", text)
    # Spaces are ordinary text, not punctuation requiring an escape.
    escaped = escaped.replace("\\ ", " ")
    return escaped.replace("\n", " / " if cell else "  \n")


def _projection(value: JsonValue, *, depth: int = 0) -> list[str]:
    """Visible structured facts with their recorded labels, never hidden payloads."""
    indent = "  " * depth
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if key in {
                "schema_version",
                "contract_kind",
                "scope",
                "compilation_id",
                "assessment_id",
                "assessment_context_id",
                "phase6_snapshot_id",
                "basis_refs",
                "authority_refs",
                "permission_refs",
                "baseline_refs",
                "missing_input_refs",
                "missing_evidence_refs",
            }:
                continue
            label = _escape(key.replace("_", " ").capitalize())
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}- **{label}:**")
                lines.extend(_projection(item, depth=depth + 1))
            else:
                lines.append(f"{indent}- **{label}:** {_escape(_scalar(item))}")
        return lines or [indent + "- none recorded"]
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(indent + "- Recorded item:")
                lines.extend(_projection(item, depth=depth + 1))
            else:
                lines.append(indent + "- " + _escape(_scalar(item)))
        return lines or [indent + "- none recorded"]
    return [indent + "- " + _escape(_scalar(value))]


def _scalar(value: JsonValue) -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _styled(text: str, style: str | None, *, cell: bool) -> str:
    if style == "CODE":
        # A delimiter longer than every content run makes backticks inert.
        length = max((len(run) for run in re.findall(r"`+", text)), default=0) + 1
        marker = "`" * length
        content = text.replace("\n", " / " if cell else " ")
        return marker + " " + content + " " + marker
    marker = "**" if style == "STRONG" else "*" if style == "EMPHASIS" else ""
    return marker + _escape(text, cell=cell) + marker


def _block_text(block: DraftBlock, citations: tuple[ReportCitation, ...]) -> str:
    cell = block.kind == "TABLE_CELL"
    boundaries = {0, len(block.text)}
    tokens: dict[int, list[int]] = {}
    for style in block.inline_styles:
        if not 0 <= style.start < style.end <= len(block.text):
            raise ReportProposalError("rendered style is outside actual text")
        boundaries.update((style.start, style.end))
    for token in block.citation_tokens:
        if not 0 <= token.offset <= len(block.text):
            raise ReportProposalError("rendered citation is outside actual text")
        matches = [c.display_number for c in citations if token.authority_ref in c.basis_refs]
        if not matches:
            raise ReportProposalError("rendered citation token has no admitted registry entry")
        tokens.setdefault(token.offset, []).extend(matches)
        boundaries.add(token.offset)
    ordered = sorted(boundaries)
    result: list[str] = []
    for i, start in enumerate(ordered):
        for number in sorted(set(tokens.get(start, []))):
            result.append(f" [{number}](#reference-{number})")
        if i + 1 == len(ordered):
            continue
        end = ordered[i + 1]
        active = {s.style for s in block.inline_styles if s.start <= start and s.end >= end}
        style = next((s for s in ("CODE", "STRONG", "EMPHASIS") if s in active), None)
        result.append(_styled(block.text[start:end], style, cell=cell))
    return "".join(result)


def _markdown(report: CompiledAssessmentReport) -> str:
    ir = report.ir
    citations = ir.citation_registry.citations
    lines = [
        "# Novelty assessment report",
        "",
        f"Report: {_escape(report.report_id)}",
        "",
        f"Assessment: {_escape(report.scope.assessment_id)}",
        "",
        f"Adjudication: {_escape(report.scope.adjudication_id)}",
        "",
        f"Context: {_escape(report.scope.assessment_context_id)}",
        "",
        f"Snapshot: {_escape(report.scope.phase6_snapshot_id)}",
        "",
        f"Assessed cutoff: {ir.as_of.isoformat()}",
        "",
    ]
    if ir.compact_summary is not None:
        lines.extend(
            ["## Compact summary", "", *_projection(ir.compact_summary.model_dump(mode="json")), ""]
        )
    for section in ir.sections:
        lines.extend([f"## Q{section.question_id}. {_escape(section.question_label)}", ""])
        table: str | None = None
        for accepted in section.blocks:
            block = accepted.draft_block
            text = _block_text(block, citations)
            claim_ids = {c.claim_id for c in accepted.claims}
            implicit = [c for c in citations if claim_ids.intersection(c.claim_ids)]
            already = {
                n
                for token in block.citation_tokens
                for n in [
                    c.display_number for c in citations if token.authority_ref in c.basis_refs
                ]
            }
            text += "".join(
                f" [{c.display_number}](#reference-{c.display_number})"
                for c in implicit
                if c.display_number not in already
            )
            if block.kind == "TABLE_CELL":
                # A long-form cell table preserves authored cell order and exact
                # coordinates without fabricating header assertions or truncation.
                if table != block.table_id:
                    lines.extend(["| Row | Column | Content |", "| --- | --- | --- |"])
                    table = block.table_id
                lines.append(f"| {block.row} | {block.column} | {text} |")
            else:
                if table is not None:
                    lines.append("")
                table = None
                prefix = (
                    "#" * (block.heading_level + 2) + " "
                    if block.kind == "HEADING"
                    else "- "
                    if block.kind == "LIST_ITEM"
                    else ""
                )
                lines.extend([prefix + text, ""])
        lines.append("")
    lines.extend(
        [
            "## Findings",
            "",
            f"Overall verdict: {_escape(ir.overall_finding.verdict.value)}",
            "",
            *_projection(ir.overall_finding.model_dump(mode="json")),
            "",
        ]
    )
    for finding in ir.target_findings:
        lines.extend(
            [
                f"### Target {_escape(finding.target_id)}",
                "",
                *_projection(finding.model_dump(mode="json")),
                "",
            ]
        )
    public: tuple[tuple[str, JsonValue], ...] = (
        (
            "Supported and qualified wording",
            [w.model_dump(mode="json") for w in ir.supported_and_qualified_wording],
        ),
        (
            "Unsupported wording examples",
            [w.model_dump(mode="json") for w in ir.unsupported_wording_examples],
        ),
        (
            "Prospective validation recommendations",
            [r.model_dump(mode="json") for r in ir.validation_requirements],
        ),
        ("Value availability", [v.model_dump(mode="json") for v in ir.value_availability]),
        ("Coverage", ir.coverage_summary.model_dump(mode="json")),
        ("Uncertainty", [u.model_dump(mode="json") for u in ir.uncertainty_summary]),
        ("Material limitations", list(ir.report_limitations)),
    )
    for title, content in public:
        lines.extend([f"## {title}", "", *_projection(content), ""])
    lines.extend(["## References", ""])
    if not citations:
        lines.extend(
            [
                "No external passage citation is recorded; internal bases remain in JSON and YAML.",
                "",
            ]
        )
    for citation in citations:
        metadata = citation.source_metadata
        source, version = metadata.source, metadata.version
        lines.extend(
            [
                f"### Reference {citation.display_number}",
                "",
                _escape(source.canonical_title or source.source_id),
                "",
                f"Source: {_escape(citation.source_id)}",
                "",
                f"Source version: {_escape(citation.source_version_id or 'unversioned authority')}",
                "",
                f"Passage: {_escape(citation.passage_id)}",
                "",
                f"Comparison: {_escape(citation.comparison_id)}",
                "",
                f"Commit: {_escape(citation.commit_id)}",
                "",
                "Commitments: " + "; ".join(_escape(i) for i in citation.commitment_ids),
                "",
                "Locator:",
                *_projection(citation.locator.model_dump(mode="json")),
                "",
                "Publication date: "
                + _escape(
                    _scalar(
                        version.published_date.isoformat()
                        if version and version.published_date
                        else source.dates.publication_date.isoformat()
                        if source.dates.publication_date
                        else None
                    )
                ),
                "",
                "Recorded source dates:",
                *_projection(source.dates.model_dump(mode="json")),
                "",
                "Retrieval observation: "
                + _escape(
                    citation.retrieved_at.isoformat() if citation.retrieved_at else "not recorded"
                ),
                "",
                "Assessed cutoff: " + citation.as_of.isoformat(),
                "",
                "Passage access: " + _escape(citation.passage_access_state.value),
                "",
                "Identifiers:",
                *_projection(source.identifiers.model_dump(mode="json")),
                "",
                "Version identifiers:",
                *_projection(version.identifiers.model_dump(mode="json") if version else None),
                "",
                "Missing metadata:",
                *_projection(list(metadata.missing_fields)),
                "",
                "Conflicting metadata observations:",
                *_projection(
                    [r.model_dump(mode="json") for r in metadata.conflicting_observation_refs]
                ),
                "",
                "Limitations:",
                *_projection(list(citation.limitations)),
                "",
            ]
        )
        link = resolve_citation_link(citation)
        if link is not None:
            label = (
                "versionless canonical page"
                if citation.canonical_page_is_versionless
                else "stored identifier resolver"
            )
            lines.extend([f"[{label}]({link})", ""])
        else:
            lines.extend(["External link: not recorded or not admitted by the link policy", ""])
    return "\n".join(lines)


def _digest(report: CompiledAssessmentReport, version: str, kind: str, content: str) -> str:
    return canonical_hash(
        {
            "report_id": report.report_id,
            "renderer_version": version,
            "format": kind,
            "content": content,
        }
    )


def render_compiled_report(
    report: CompiledAssessmentReport, *, renderer_version: str = "p8-render-v1"
) -> ReportRenditions:
    if renderer_version != "p8-render-v1":
        raise ReportProposalError("unknown or withdrawn report renderer")
    try:
        report = CompiledAssessmentReport.model_validate_json(report.model_dump_json())
    except ValueError as error:
        raise ReportProposalError("rendered report fails strict serialization") from error
    if (
        report.report_id != report_id(report)
        or report.scope != report.ir.scope
        or report.compilation_id != report.ir.compilation_id
    ):
        raise ReportProposalError("rendered report identity or scope differs")
    if (
        tuple(s.question_id for s in report.ir.sections) != tuple(range(1, 10))
        or tuple(s.question_label for s in report.ir.sections) != CANONICAL_QUESTIONS
    ):
        raise ReportProposalError("rendered report lacks exact canonical questions")
    json_text = canonical_json(report)
    payload = cast(JsonValue, json.loads(json_text))
    yaml_text = yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=True, default_flow_style=False
    )
    markdown = _markdown(report)
    return ReportRenditions(
        scope=report.scope,
        compilation_id=report.compilation_id,
        json=json_text,
        yaml=yaml_text,
        markdown=markdown,
        json_digest=_digest(report, renderer_version, "json", json_text),
        yaml_digest=_digest(report, renderer_version, "yaml", yaml_text),
        markdown_digest=_digest(report, renderer_version, "markdown", markdown),
        renderer_version=renderer_version,
    )


def validate_rendition_parity(
    report: CompiledAssessmentReport, renditions: ReportRenditions
) -> None:
    expected = render_compiled_report(report, renderer_version=renditions.renderer_version)
    try:
        json_value = json.loads(renditions.json)
        yaml_value = yaml.safe_load(renditions.yaml)
    except (ValueError, yaml.YAMLError) as error:
        raise ReportProposalError(
            "report rendition is not safe structured serialization"
        ) from error
    if (
        json_value != report.model_dump(mode="json")
        or yaml_value != json_value
        or renditions != expected
    ):
        raise ReportProposalError("report rendition omits or changes canonical visible content")

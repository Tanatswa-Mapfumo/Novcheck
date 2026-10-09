"""Deterministic inert exports of one report; rendition bytes confer no authority."""

import codecs
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from mmap import ACCESS_READ, mmap
from tempfile import TemporaryFile
from typing import Literal, cast

import yaml
from pydantic import JsonValue

from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.reporting.citations import ReportCitation, resolve_citation_link
from novelty_harness.reporting.drafts import DraftBlock
from novelty_harness.reporting.ir import (
    CompiledAssessmentReport,
    report_id,
    snapshot_compiled_report,
)
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
    metadata: dict[str, JsonValue] = {
        "report_id": report.report_id,
        "renderer_version": version,
        "format": kind,
    }
    if type(content) is not str:
        # Preserve the generic encoder's behavior outside this private helper's
        # declared text contract. Do not coerce caller values into report text.
        return canonical_hash({**metadata, "content": content})
    digest = hashlib.sha256(b'{"content":"')
    for offset in range(0, len(content), 65536):
        # Encode complete Unicode code points with the original standard JSON
        # string encoder. Removing only each chunk's quotes preserves escaping,
        # including astral code points, control characters and lone surrogates.
        encoded = json.encoder.encode_basestring_ascii(content[offset : offset + 65536])
        digest.update(encoded[1:-1].encode("utf-8"))
    digest.update(b'",')
    # Sorted canonical metadata follows the lexically first content key. Keep
    # the existing encoder for every remaining value and its finite/type rules.
    digest.update(canonical_json(metadata).encode("utf-8")[1:])
    return digest.hexdigest()


def _rendition_payload(report: CompiledAssessmentReport, json_text: str) -> JsonValue:
    """Project the renderer's revalidated closed report without parsing text twice.

    JSON-mode serializers produce the same scalar/container projection as its
    canonical JSON; strings are immutable, and dumped containers are private.
    Preserve the previous parser path for unknown standalone subclasses.
    """
    if type(report) is not CompiledAssessmentReport:
        return cast(JsonValue, json.loads(json_text))
    return cast(JsonValue, report.model_dump(mode="json"))


def _yaml_text(payload: JsonValue) -> str:
    # Use the same SafeDumper and options. Its nodes/emitter are disposed before
    # reading the completed output, so a complete StringIO and the final text
    # do not coexist with those temporary representations. The private unnamed
    # file closes on emission, I/O or read failure; no rendition path is exposed.
    with TemporaryFile(mode="w+t", encoding="utf-16-le", newline="") as stream:
        yaml.safe_dump(
            payload, stream=stream, allow_unicode=True, sort_keys=True, default_flow_style=False
        )
        stream.flush()
        # Decode the read-only buffer directly. The private UTF-16 code units
        # avoid a complete UTF-8 bytes buffer and its variable-width decoder
        # over-allocation. Returned text and externally written bytes stay exact.
        with mmap(stream.fileno(), 0, access=ACCESS_READ) as encoded:
            return codecs.decode(encoded, "utf-16-le")


def _validated_render_report(
    report: CompiledAssessmentReport, renderer_version: str
) -> CompiledAssessmentReport:
    if renderer_version != "p8-render-v1":
        raise ReportProposalError("unknown or withdrawn report renderer")
    try:
        report = snapshot_compiled_report(report)
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
    return report


def _rendition_parts(
    report: CompiledAssessmentReport, renderer_version: str
) -> Iterator[tuple[str, str, str]]:
    """Render every exact format from the private serialized snapshot in order."""
    json_text = canonical_json(report)
    yield "json", json_text, _digest(report, renderer_version, "json", json_text)
    payload = _rendition_payload(report, json_text)
    del json_text
    yaml_text = _yaml_text(payload)
    del payload
    yield "yaml", yaml_text, _digest(report, renderer_version, "yaml", yaml_text)
    del yaml_text
    markdown = _markdown(report)
    yield "markdown", markdown, _digest(report, renderer_version, "markdown", markdown)


def render_compiled_report(
    report: CompiledAssessmentReport, *, renderer_version: str = "p8-render-v1"
) -> ReportRenditions:
    report = _validated_render_report(report, renderer_version)
    formats = {
        kind: (text, digest) for kind, text, digest in _rendition_parts(report, renderer_version)
    }
    return ReportRenditions(
        scope=report.scope,
        compilation_id=report.compilation_id,
        json=formats["json"][0],
        yaml=formats["yaml"][0],
        markdown=formats["markdown"][0],
        json_digest=formats["json"][1],
        yaml_digest=formats["yaml"][1],
        markdown_digest=formats["markdown"][1],
        renderer_version=renderer_version,
    )


def _expected_json_matches(
    report: CompiledAssessmentReport, version: str, content: str, identity: str
) -> bool:
    """Compare every expected canonical character and exact digest in chunks."""
    if type(content) is not str:
        expected = canonical_json(report)
        return content == expected and identity == _digest(report, version, "json", expected)
    encoder = json.JSONEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    digest = hashlib.sha256(b'{"content":"')
    offset, same = 0, True
    # The private strict closed report's JSON-mode projection is the exact
    # canonical scalar/container projection, independently differential-tested.
    for chunk in encoder.iterencode(report.model_dump(mode="json")):
        end = offset + len(chunk)
        same = (content[offset:end] == chunk) and same
        offset = end
        escaped = json.encoder.encode_basestring_ascii(chunk)
        digest.update(escaped[1:-1].encode("utf-8"))
    digest.update(b'",')
    metadata: dict[str, JsonValue] = {
        "report_id": report.report_id,
        "renderer_version": version,
        "format": "json",
    }
    digest.update(canonical_json(metadata).encode("utf-8")[1:])
    return same and offset == len(content) and identity == digest.hexdigest()


def validate_rendition_parity(
    report: CompiledAssessmentReport, renditions: ReportRenditions
) -> None:
    validated = _validated_render_report(report, renditions.renderer_version)
    json_same = _expected_json_matches(
        validated, renditions.renderer_version, renditions.json, renditions.json_digest
    )
    same = (
        json_same
        and type(renditions) is ReportRenditions
        and renditions.scope == validated.scope
        and renditions.compilation_id == validated.compilation_id
        and renditions.contract_kind == "phase8-report-renditions-v1"
    )
    # Compare every exact expected string and digest, releasing each before the
    # next format. Retain a boolean, never a complete second rendition bundle.
    for kind in ("yaml", "markdown"):
        text = (
            _yaml_text(cast(JsonValue, validated.model_dump(mode="json")))
            if kind == "yaml"
            else _markdown(validated)
        )
        digest = _digest(validated, renditions.renderer_version, kind, text)
        same = (
            getattr(renditions, kind) == text and getattr(renditions, kind + "_digest") == digest
        ) and same
        del text, digest
    del validated
    # Both original safe parses and complete visible mapping equality remain
    # mandatory even when an earlier byte/digest/metadata comparison differed.
    try:
        json_value = json.loads(renditions.json)
        yaml_value = yaml.safe_load(renditions.yaml)
    except (ValueError, yaml.YAMLError) as error:
        raise ReportProposalError(
            "report rendition is not safe structured serialization"
        ) from error
    if json_value != report.model_dump(mode="json") or yaml_value != json_value or not same:
        raise ReportProposalError("report rendition omits or changes canonical visible content")

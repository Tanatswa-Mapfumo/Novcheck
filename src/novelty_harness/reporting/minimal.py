import hashlib
import json
from collections.abc import Sequence

from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.enums import SupportVerificationState
from novelty_harness.domain.evidence import EvidenceEdge
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    SufficiencyAssessment,
)
from novelty_harness.domain.mcu import MCU
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS, CompiledReport, ReportAnswers


def _list_or_unknown(values: Sequence[str], missing: str) -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"Unknown: {missing}."


def compile_minimal_report(
    *,
    idea: CanonicalIdeaRepresentation,
    sufficiency: SufficiencyAssessment,
    mcus: Sequence[MCU],
    edges: Sequence[EvidenceEdge],
    adjudication: FrozenAdjudication,
) -> CompiledReport:
    # Frozen adjudication has only JSON scalars and ordered tuples, never sets.
    serialized = json.dumps(
        adjudication.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    adjudication_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    decisive_ids = {edge_id for finding in adjudication.mcus for edge_id in finding.decisive_edges}
    supported = [
        edge
        for edge in edges
        if edge.edge_id in decisive_ids
        and edge.support_verification == SupportVerificationState.SUPPORTED
    ]
    missing_ids = decisive_ids - {edge.edge_id for edge in supported}
    closest = [
        f"{edge.proposition} (MCU {edge.mcu_id}; source {edge.source_id}; "
        f"passages {', '.join(edge.passage_ids)}; relation {edge.relation_type.value}; "
        f"quality {edge.evidence_quality.value if edge.evidence_quality else 'unknown'}; "
        "cutoff support "
        f"{edge.predates_cutoff if edge.predates_cutoff is not None else 'unknown'})."
        for edge in supported
    ]
    challenges = adjudication.strongest_challenges if supported and not missing_ids else ()
    value = [
        f"{finding.dimension}: {finding.statement} (maturity: {finding.maturity.value})"
        for finding in adjudication.value_findings
    ]
    supported_wording = _list_or_unknown(
        adjudication.permitted_language, "no supported wording supplied in frozen findings"
    )
    forbidden = _list_or_unknown(adjudication.forbidden_claims, "no forbidden wording recorded")
    unresolved = (
        *adjudication.unresolved_questions,
        *adjudication.evidence_limitations,
        *sufficiency.missing_information,
        *sufficiency.consequences,
        *idea.unknowns,
        *(factor for finding in adjudication.mcus for factor in finding.limiting_factors),
        *(f"Missing or unsupported decisive edge: {identity}" for identity in sorted(missing_ids)),
    )
    answers = ReportAnswers(
        q1="\n".join(
            (
                idea.title or "Untitled idea",
                idea.problem.statement,
                *(f"{mcu.label}: {mcu.statement}" for mcu in mcus),
            )
        ),
        q2=_list_or_unknown(closest, "no verified closest precedent supplied in frozen findings"),
        q3=_list_or_unknown(adjudication.established_findings, "no established findings supplied"),
        q4=_list_or_unknown(
            adjudication.novelty_candidates, "no novelty candidate findings supplied"
        ),
        q5=_list_or_unknown(
            challenges, "no verified challenge; evidence is missing or unsupported"
        ),
        q6=_list_or_unknown(value, "no value findings supplied; novelty does not establish value"),
        q7=_list_or_unknown(
            adjudication.validation_requirements, "no validation requirements supplied"
        ),
        q8=f"Supported wording:\n{supported_wording}\nUnsupported wording:\n{forbidden}",
        q9=_list_or_unknown(unresolved, "no unresolved questions supplied"),
    )
    sections = [
        "# Assessment report",
        "\n".join(
            "> " + line
            for line in (
                f"Findings origin: {adjudication.provenance.kind}. {adjudication.provenance.detail}"
            ).splitlines()
        ),
        f"As of: {adjudication.as_of.isoformat()}. "
        f"Frozen verdict: {adjudication.overall_state.value}.",
    ]
    for index, question in enumerate(CANONICAL_QUESTIONS, 1):
        answer = str(getattr(answers, f"q{index}"))
        sections.extend(
            (f"## Q{index}. {question}", "\n".join("> " + line for line in answer.splitlines()))
        )
    return CompiledReport(
        assessment_id=adjudication.assessment_id,
        adjudication_hash=adjudication_hash,
        overall_verdict=adjudication.overall_state,
        answers=answers,
        markdown="\n\n".join(sections) + "\n",
        provenance=ArtifactProvenance(
            kind="implemented",
            component="minimal_report_compiler",
            detail="Deterministic rendering of frozen findings; no novelty decision.",
        ),
    )

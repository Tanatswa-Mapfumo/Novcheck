import hashlib
import json
from collections.abc import Sequence

from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.enums import PrecedentState, SupportVerificationState, VerdictState
from novelty_harness.domain.evidence import EvidenceEdge
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    SufficiencyAssessment,
)
from novelty_harness.domain.mcu import MCU
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS, CompiledReport, ReportAnswers
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    Phase6AssessmentView,
)
from novelty_harness.evidence.graph.models import GraphEdgeKind
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository


def _list_or_unknown(values: Sequence[str], missing: str) -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"Unknown: {missing}."


def _render_markdown(adjudication: FrozenAdjudication, answers: ReportAnswers) -> str:
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
    return "\n\n".join(sections) + "\n"


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
    return CompiledReport(
        assessment_id=adjudication.assessment_id,
        adjudication_hash=adjudication_hash,
        overall_verdict=adjudication.overall_state,
        answers=answers,
        markdown=_render_markdown(adjudication, answers),
        provenance=ArtifactProvenance(
            kind="implemented",
            component="minimal_report_compiler",
            detail="Deterministic rendering of frozen findings; no novelty decision.",
        ),
    )


def compile_minimal_phase6_report(
    *,
    idea: CanonicalIdeaRepresentation,
    sufficiency: SufficiencyAssessment,
    mcus: Sequence[MCU],
    view: Phase6AssessmentView,
    repository: EvidenceGraphRepository,
    adjudication: FrozenAdjudication,
) -> CompiledReport:
    """Render frozen findings against graph relations reloaded from repository authority."""
    authoritative = repository.load_phase6_assessment(
        view.assessment_id, snapshot_id=view.snapshot_id
    )
    if authoritative != view:
        raise ValueError("supplied Phase 6 assessment view does not match repository snapshot")
    if adjudication.assessment_id != authoritative.assessment_id:
        raise ValueError("frozen findings belong to a different assessment")
    if adjudication.as_of != authoritative.as_of:
        raise ValueError("frozen findings cutoff does not match the repository snapshot")
    if adjudication.provenance.kind != "fixture":
        raise ValueError("Phase 6 fixture reports require fixture-origin frozen findings")
    if adjudication.overall_state != VerdictState.UNASSESSABLE:
        raise ValueError("Phase 6 fixture reports require an UNASSESSABLE overall verdict")
    if any(finding.verdict != VerdictState.UNASSESSABLE for finding in adjudication.mcus):
        raise ValueError("Phase 6 fixture MCU findings must remain UNASSESSABLE")

    relations_by_edge: dict[str, list[AuthorizedGraphRelation]] = {}
    for relation in authoritative.authorized_graph_relations:
        relations_by_edge.setdefault(relation.verified_edge_id, []).append(relation)
    decisive_ids = {edge_id for finding in adjudication.mcus for edge_id in finding.decisive_edges}
    cited_relations: dict[str, AuthorizedGraphRelation] = {}
    for finding in adjudication.mcus:
        for edge_id in finding.decisive_edges:
            candidates = relations_by_edge.get(edge_id, [])
            if not candidates:
                raise ValueError(f"decisive evidence is not repository-authorized: {edge_id}")
            relation = next(
                (
                    item
                    for item in candidates
                    if item.edge.target_node_id == finding.mcu_id
                    and item.edge.kind == GraphEdgeKind.DIRECT_PRECEDENT
                ),
                None,
            )
            if relation is None:
                raise ValueError(
                    "decisive evidence does not identify direct evidence for the finding MCU"
                )
            if relation.edge.target_node_id != finding.mcu_id:
                raise ValueError("decisive evidence does not belong to the finding MCU")
            if (
                relation.edge.verification is None
                or not relation.edge.verification.decisive
                or relation.edge.verification.support_state != SupportVerificationState.SUPPORTED
            ):
                raise ValueError("decisive evidence is not eligible supported direct evidence")
            if finding.precedent_state != PrecedentState.DIRECT_PRECEDENT:
                raise ValueError(
                    "decisive DIRECT_PRECEDENT evidence requires a DIRECT_PRECEDENT finding state"
                )
            cited_relations[edge_id] = relation

    comparisons = {
        item.comparison.comparison.chain.edge.edge_id: item
        for item in authoritative.committed_comparisons
    }
    closest: list[str] = []
    limitations: list[str] = []
    scoped_context: list[str] = []
    for item in authoritative.committed_comparisons:
        comparison = item.comparison.comparison
        classification = item.comparison.classification
        chain = comparison.chain
        for scope in classification.scoped_coverage:
            source_version = chain.version.version_id if chain.version else "unversioned"
            passages = tuple(
                cited.passage
                for cited in item.cited_passages
                if cited.passage.passage_id in scope.passage_ids
            )
            scoped_context.append(
                f"Local {classification.relation.value} for MCU {chain.edge.mcu_id}: "
                f"supported subset {scope.supported_subset}; unsupported remainder "
                f"{scope.unsupported_remainder}; source version {source_version}; "
                + " ".join(
                    f"Passage {passage.passage_id}: “{passage.text}”" for passage in passages
                )
            )
            limitations.extend(
                f"{passage.passage_id}: {limitation}"
                for passage in passages
                for limitation in passage.limitations
            )
    for identity in sorted(decisive_ids):
        relation = cited_relations[identity]
        comparison_view = comparisons.get(relation.verified_edge_id)
        if comparison_view is None:
            raise ValueError("authorized relation has no committed semantic comparison")
        comparison = comparison_view.comparison.comparison
        classification = comparison_view.comparison.classification
        chain = comparison.chain
        if (
            chain.edge.edge_id != identity
            or chain.source.source_id != relation.edge.source_node_id
            or chain.edge.mcu_id != relation.edge.target_node_id
            or not classification.decisive
            or classification.relation.value != "DIRECT_PRECEDENT"
        ):
            raise ValueError(
                "authorized relation does not match its decisive source/MCU classification"
            )
        cited_passages = comparison_view.cited_passages
        passage_text = " ".join(
            f"Passage {item.passage.passage_id}: “{item.passage.text}”" for item in cited_passages
        )
        version = chain.version.version_id if chain.version else "unversioned"
        scope_text = "".join(
            f"; scoped coverage {item.supported_subset}; unsupported remainder: "
            f"{item.unsupported_remainder}"
            for item in classification.scoped_coverage
        )
        closest.append(
            f"{chain.edge.proposition} (MCU {chain.edge.mcu_id}; source {chain.source.source_id}; "
            f"version {version}; relation {classification.relation.value}; "
            f"support {chain.edge.support_state.value}{scope_text}; {passage_text})."
        )
        limitations.extend(
            f"{item.passage.passage_id}: {limitation}"
            for item in cited_passages
            for limitation in item.passage.limitations
        )
        for reason in chain.edge.eligibility.reasons:
            limitations.append(f"{chain.edge.edge_id}: {reason}")

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
        *scoped_context,
        *limitations,
        *authoritative.coverage.limitations,
        *sufficiency.missing_information,
        *sufficiency.consequences,
        *idea.unknowns,
        *(factor for finding in adjudication.mcus for factor in finding.limiting_factors),
    )
    answers = ReportAnswers(
        q1="\n".join(
            (
                idea.title or "Untitled idea",
                idea.problem.statement,
                *(f"{mcu.label}: {mcu.statement}" for mcu in mcus),
            )
        ),
        q2=_list_or_unknown(
            closest, "no authorized decisive direct precedent supplied in frozen findings"
        ),
        q3=_list_or_unknown(adjudication.established_findings, "no established findings supplied"),
        q4=_list_or_unknown(
            adjudication.novelty_candidates, "no novelty candidate findings supplied"
        ),
        q5=_list_or_unknown(
            adjudication.strongest_challenges if closest else (),
            "no authorized decisive challenge supplied in frozen findings",
        ),
        q6=_list_or_unknown(value, "no value findings supplied; novelty does not establish value"),
        q7=_list_or_unknown(
            adjudication.validation_requirements, "no validation requirements supplied"
        ),
        q8=f"Supported wording:\n{supported_wording}\nUnsupported wording:\n{forbidden}",
        q9=_list_or_unknown(unresolved, "no unresolved questions supplied"),
    )
    serialized = json.dumps(
        adjudication.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return CompiledReport(
        assessment_id=adjudication.assessment_id,
        adjudication_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        overall_verdict=adjudication.overall_state,
        answers=answers,
        markdown=_render_markdown(adjudication, answers),
        provenance=ArtifactProvenance(
            kind="implemented",
            component="minimal_phase6_report_compiler",
            detail=(
                "Deterministic rendering of frozen findings and repository-authorized evidence; "
                "no novelty decision."
            ),
        ),
    )

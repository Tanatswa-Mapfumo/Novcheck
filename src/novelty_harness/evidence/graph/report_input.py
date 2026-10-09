"""Report input authority is loaded in one explicit, shared SQLite read transaction."""

from collections.abc import Callable
from functools import partial

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from novelty_harness.adjudication.counterfactual import CounterfactualLocalization
from novelty_harness.adjudication.gates import (
    GateAFinding,
    GateBFinding,
    GateCFinding,
    GateDFinding,
)
from novelty_harness.adjudication.judge import (
    CounterbalanceComparison,
    CounterbalanceRun,
    JudgeResolution,
)
from novelty_harness.adjudication.models import Phase7Artifact, TargetRef
from novelty_harness.adjudication.needs import (
    InputClarificationNeed,
    ResearchGapDisposition,
    ResearchGapRequest,
)
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase, RebuttalCase
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.graph.assessment_ledger import phase6_candidate_record_id
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.evidence.graph.phase7_store import (
    load_frozen_adjudication_in_session,
    load_phase7_artifacts_in_session,
    load_phase7_context_in_session,
)
from novelty_harness.reporting.bundle import (
    AdjudicationReportingClosure,
    ReportInputBundle,
    derive_language_envelopes,
    project_source_metadata,
    report_bundle_digest,
)
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    BundlePolicyVersion,
    ReportDependency,
    ReportScope,
    authority_dependency_id,
)
from novelty_harness.reporting.obligations import derive_coverage_obligations
from novelty_harness.reporting.repository import ReportAuthorityError
from novelty_harness.reporting.uncertainty import project_uncertainty
from novelty_harness.reporting.value import project_value
from novelty_harness.runtime.tracing.hashing import canonical_hash


def _documents[T: BaseModel](
    artifacts: tuple[Phase7Artifact, ...], kind: str, model: type[T]
) -> tuple[T, ...]:
    return tuple(model.model_validate_json(a.document_json) for a in artifacts if a.kind == kind)


def load_report_input_bundle_in_session(
    session: Session,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
    bundle_version: BundlePolicyVersion = "p8-bundle-v2",
) -> ReportInputBundle:
    """Reuse upstream validation; this reader has no mutation or semantic capabilities."""
    try:
        if bundle_version not in ("p8-bundle-v1", "p8-bundle-v2"):
            raise ReportAuthorityError("report bundle policy is unsupported")
        frozen = load_frozen_adjudication_in_session(
            session,
            load_view_in_session,
            assessment_id,
            adjudication_id=adjudication_id,
        )
        load_view = partial(load_view_in_session, session)
        context = load_phase7_context_in_session(
            session, load_view, assessment_id, context_id=frozen.assessment_context_id
        )
        view = load_view(assessment_id, snapshot_id=frozen.phase6_snapshot_id)
        artifacts = tuple(
            sorted(
                load_phase7_artifacts_in_session(session, frozen.run_id),
                key=lambda a: a.artifact_id,
            )
        )
        scope = ReportScope(
            assessment_id=assessment_id,
            adjudication_id=adjudication_id,
            assessment_context_id=context.context_id,
            phase6_snapshot_id=view.snapshot_id,
        )
        manifest = context.manifest
        refs: dict[str, AuthorityRef] = {}

        def add(
            kind: AuthorityKind,
            identifier: str,
            document: BaseModel | str,
            *,
            target: TargetRef | None = None,
            path: tuple[str | int, ...] = (),
        ) -> AuthorityRef:
            ref = AuthorityRef(
                kind=kind,
                native_id=identifier,
                digest=canonical_hash(document),
                scope=scope,
                target=target,
                path=path,
            )
            identity = authority_dependency_id(ref)
            previous = refs.get(identity)
            if previous is not None and previous != ref:
                raise ReportAuthorityError("native field dependency has conflicting content")
            refs[identity] = ref
            return ref

        add(AuthorityKind.FROZEN, adjudication_id, frozen)
        add(AuthorityKind.CONTEXT, context.context_id, context)
        input_ref = add(AuthorityKind.INPUT_MANIFEST, context.manifest_id, manifest)
        add(AuthorityKind.CIR, manifest.cir.idea_id, manifest.cir)
        add(AuthorityKind.GRAPH, context.manifest_id, manifest.mcu_graph, path=("mcu_graph",))
        add(AuthorityKind.RESEARCH_STATE, context.manifest_id, manifest)
        add(AuthorityKind.COVERAGE, view.snapshot_id, view.coverage)
        targets = {p.target_id: TargetRef(kind=p.target_kind, id=p.target_id) for p in view.targets}
        for profile in view.targets:
            add(AuthorityKind.TARGET, profile.target_id, profile, target=targets[profile.target_id])
        for index, finding in enumerate(frozen.target_findings):
            add(
                AuthorityKind.TARGET_FINDING,
                adjudication_id,
                finding,
                target=targets[finding.target_id],
                path=("target_findings", index),
            )
        add(
            AuthorityKind.OVERALL_FINDING,
            adjudication_id,
            frozen.overall_finding,
            path=("overall_finding",),
        )
        metadata = project_source_metadata(view, scope)
        for observation in metadata:
            for ref in (
                *observation.comparison_refs,
                observation.source_ref,
                *(() if observation.version_ref is None else (observation.version_ref,)),
            ):
                identity = authority_dependency_id(ref)
                if identity in refs and refs[identity] != ref:
                    raise ReportAuthorityError("source metadata dependency differs")
                refs[identity] = ref
        for comparison in view.committed_comparisons:
            cls = comparison.comparison.classification
            add(
                AuthorityKind.COMMIT,
                comparison.commit_id,
                comparison,
                path=("comparisons", cls.classification_id),
            )
            for cited in comparison.cited_passages:
                # Citation use is comparison/commitment specific even for a shared passage.
                add(
                    AuthorityKind.PASSAGE,
                    cited.passage.passage_id,
                    cited,
                    target=targets[comparison.comparison.comparison.chain.edge.mcu_id],
                    path=(
                        "comparisons",
                        comparison.commit_id,
                        cls.classification_id,
                        "cited_passages",
                        cited.passage.passage_id,
                    ),
                )
        for relation in view.authorized_graph_relations:
            add(AuthorityKind.GRAPH_RELATION, relation.edge.edge_id, relation)
        for candidate in view.candidate_outcomes:
            add(
                AuthorityKind.CANDIDATE,
                phase6_candidate_record_id(candidate),
                candidate,
                target=targets[candidate.target_id],
            )
        for lineage in view.lineage:
            add(AuthorityKind.LINEAGE, lineage.cluster_id, lineage)
        for collection in ("multi_source_context", "patent_screenings"):
            for index, record in enumerate(getattr(view, collection)):
                add(
                    AuthorityKind.CONTEXT,
                    view.snapshot_id,
                    record,
                    target=targets[record.target_id],
                    path=(collection, index),
                )
        gates = (
            *_documents(artifacts, "GATE_A", GateAFinding),
            *_documents(artifacts, "GATE_B", GateBFinding),
            *_documents(artifacts, "GATE_C", GateCFinding),
            *_documents(artifacts, "GATE_D", GateDFinding),
        )
        qualifications = (
            *_documents(artifacts, "ROBUSTNESS_QUALIFICATION", RobustnessQualification),
            *_documents(artifacts, "DOMAIN_QUALIFICATION", DomainQualification),
        )
        roles = (
            *_documents(artifacts, "PROSECUTION_CASE", ProsecutionCase),
            *_documents(artifacts, "DEFENSE_CASE", DefenseCase),
        )
        rebuttals = _documents(artifacts, "REBUTTAL", RebuttalCase)
        judge_runs = _documents(artifacts, "JUDGE_RUN", CounterbalanceRun)
        comparisons = _documents(artifacts, "COUNTERBALANCE_COMPARISON", CounterbalanceComparison)
        resolutions = _documents(artifacts, "JUDGE_RESOLUTION", JudgeResolution)
        needs = _documents(artifacts, "INPUT_NEED", InputClarificationNeed)
        gaps = _documents(artifacts, "RESEARCH_GAP", ResearchGapRequest)
        counterfactuals = _documents(artifacts, "COUNTERFACTUAL", CounterfactualLocalization)
        for artifact in artifacts:
            add(
                AuthorityKind.FROZEN,
                adjudication_id,
                artifact,
                path=("dependency_artifacts", artifact.artifact_id),
            )
        for kind, documents, id_field in (
            (AuthorityKind.GATE, gates, "gate_id"),
            (AuthorityKind.QUALIFICATION, qualifications, "qualification_id"),
            (AuthorityKind.ROLE, roles, "case_id"),
            (AuthorityKind.REBUTTAL, rebuttals, "rebuttal_id"),
            (AuthorityKind.JUDGE_RUN, judge_runs, "run_id"),
            (AuthorityKind.JUDGE_COMPARISON, comparisons, "comparison_id"),
            (AuthorityKind.JUDGE_RESOLUTION, resolutions, "resolution_id"),
            (AuthorityKind.INPUT_NEED, needs, "need_id"),
            (AuthorityKind.RESEARCH_GAP, gaps, "request_id"),
            (AuthorityKind.COUNTERFACTUAL, counterfactuals, "localization_id"),
        ):
            for document in documents:
                add(
                    kind,
                    str(getattr(document, id_field)),
                    document,
                    target=targets[document.target_id],
                )
        history: list[AuthorityRef] = []
        for identifier in frozen.superseded_context_ids:
            ancestor = load_phase7_context_in_session(
                session, load_view, assessment_id, context_id=identifier
            )
            history.append(add(AuthorityKind.SUPERSESSION, identifier, ancestor))
        closure = AdjudicationReportingClosure(
            scope=scope,
            phase6_view=view,
            role_cases=roles,
            rebuttals=rebuttals,
            judge_runs=judge_runs,
            judge_comparisons=comparisons,
            judge_resolutions=resolutions,
            research_dispositions=_documents(
                artifacts, "RESEARCH_GAP_DISPOSITION", ResearchGapDisposition
            ),
            upstream_artifacts=artifacts,
            superseded_context_refs=tuple(history),
        )
        dependencies = tuple(
            ReportDependency(
                dependency_kind="UPSTREAM",
                dependency_id=identity,
                expected_digest=ref.digest,
                authority_ref=ref,
            )
            for identity, ref in sorted(refs.items())
        )
        bundle = ReportInputBundle(
            contract_kind=(
                "phase8-report-input-bundle-v1"
                if bundle_version == "p8-bundle-v1"
                else "phase8-report-input-bundle-v2"
            ),
            bundle_version=bundle_version,
            scope=scope,
            as_of=view.as_of,
            bundle_digest="0" * 64,
            frozen_adjudication=frozen,
            input_manifest_ref=input_ref,
            cir=manifest.cir,
            graph_or_version=manifest.mcu_graph,
            target_profiles=view.targets,
            target_findings=frozen.target_findings,
            overall_finding=frozen.overall_finding,
            gate_findings=gates,
            qualifications=qualifications,
            eligible_comparisons=view.committed_comparisons,
            authorized_relations=view.authorized_graph_relations,
            cited_passages=tuple(p for c in view.committed_comparisons for p in c.cited_passages),
            source_metadata=metadata,
            research_state=manifest,
            input_needs=needs,
            research_gaps=gaps,
            judge_resolutions_and_limitations=closure,
            counterfactuals=counterfactuals,
            dependency_manifest=dependencies,
            audit_refs=view.audit_refs,
        )
        envelopes = derive_language_envelopes(bundle)
        value_projection = project_value(bundle)
        obligations = derive_coverage_obligations(bundle)
        projection_refs = (
            *(r for record in envelopes for r in record.authority_refs),
            *(r for record in obligations for r in record.authority_refs),
            *(r for record in project_uncertainty(bundle) for r in record.authority_refs),
            *(r for record in value_projection for r in record.basis_refs),
        )
        for ref in projection_refs:
            identity = authority_dependency_id(ref)
            if identity in refs and refs[identity] != ref:
                raise ReportAuthorityError("report field identity has conflicting content")
            refs[identity] = ref
        dependencies = tuple(
            ReportDependency(
                dependency_kind="UPSTREAM",
                dependency_id=identity,
                expected_digest=ref.digest,
                authority_ref=ref,
            )
            for identity, ref in sorted(refs.items())
        )
        bundle = ReportInputBundle.model_validate(
            bundle.model_dump(mode="json")
            | {
                "language_envelopes": envelopes,
                "value_projection": value_projection,
                "coverage_obligations": obligations,
                "dependency_manifest": dependencies,
            }
        )
        return bundle.model_copy(update={"bundle_digest": report_bundle_digest(bundle)})
    except ValueError as exc:
        if isinstance(exc, ReportAuthorityError):
            raise
        raise ReportAuthorityError(f"Report upstream authority validation failed: {exc}") from exc


def load_report_input_bundle(
    engine: Engine,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
    bundle_version: BundlePolicyVersion = "p8-bundle-v2",
) -> ReportInputBundle:
    with Session(engine) as session:
        session.connection().exec_driver_sql("BEGIN")
        bundle = load_report_input_bundle_in_session(
            session,
            load_view_in_session,
            assessment_id,
            adjudication_id=adjudication_id,
            bundle_version=bundle_version,
        )
        session.commit()
        return bundle

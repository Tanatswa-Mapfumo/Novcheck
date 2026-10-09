"""Append-only report attempts and typed artifacts on the existing engine."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView
from novelty_harness.evidence.graph.report_input import load_report_input_bundle_in_session
from novelty_harness.evidence.graph.report_models import (
    CompiledReportRow,
    ReportArtifactRow,
    ReportCompilationRow,
    ReportDependencyRow,
)
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportArtifactKind,
    ReportAttemptState,
    ReportCompilationRecord,
    ReportStatusEvent,
    compilation_id,
    compilation_key,
    make_report_artifact,
    report_artifact_id,
    report_artifact_semantic_content,
    report_status_event_id,
)
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.claims import ClaimExtractionProposal, validate_claim_extraction
from novelty_harness.reporting.drafts import (
    SectionDraft,
    SectionDraftFragment,
    build_section_context,
)
from novelty_harness.reporting.execution import (
    DETERMINISTIC_VERSIONS,
    ReportCompilationConfiguration,
    ReportExecutionRecord,
    ReportMethodRegistration,
    ReportRoleConfiguration,
    approved_role_configuration,
    bind_compilation_configuration,
    validate_method_registration,
)
from novelty_harness.reporting.fallback import FallbackRecord, validate_fallback_section
from novelty_harness.reporting.firewall import FirewallResult, check_report_claims
from novelty_harness.reporting.ir import CompiledAssessmentReport, report_id
from novelty_harness.reporting.models import ReportOptions, ReportScope, ReportSemanticRole
from novelty_harness.reporting.plan import (
    ReportPlan,
    ReportPlanProposal,
    build_coverage_plan,
    validate_report_plan,
)
from novelty_harness.reporting.repair import (
    LocalRepairContext,
    RepairCluster,
    apply_repair_fragment,
    repair_cluster_id,
    repair_origin_id,
    report_violations,
    select_repair_clusters,
    validate_repair_fragment,
)
from novelty_harness.reporting.repository import ReportAuthorityError
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    CompositionCheck,
    CompositionContext,
    VerificationDisposition,
    build_claim_verification_context,
    validate_composition_check,
    validate_verification_batch,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def _validate_configuration(
    configuration: ReportCompilationConfiguration, scope: ReportScope
) -> None:
    if set(configuration.deterministic_versions) != set(DETERMINISTIC_VERSIONS):
        raise ReportAuthorityError("report deterministic policies are unapproved or incomplete")
    for role in configuration.roles:
        if role.scope != scope or role != approved_role_configuration(
            scope, role.compilation_id, role.role, role.port, method_version=role.method_version
        ):
            raise ReportAuthorityError("report role configuration is not approved")


def load_report_compilation_in_session(session: Session, locator: str) -> ReportCompilationRecord:
    row = session.get(ReportCompilationRow, locator)
    if row is None:
        raise ReportAuthorityError("report compilation is missing")
    record = ReportCompilationRecord.model_validate_json(row.document_json)
    scope = record.scope
    if (
        record.compilation_id,
        record.compilation_key,
        record.attempt_token,
        scope.assessment_id,
        scope.adjudication_id,
        scope.assessment_context_id,
        scope.phase6_snapshot_id,
        record.bundle_digest,
        canonical_hash(record.options),
        canonical_hash(record.configuration),
        canonical_json(record),
    ) != (
        row.compilation_id,
        row.compilation_key,
        row.attempt_token,
        row.assessment_id,
        row.adjudication_id,
        row.context_id,
        row.snapshot_id,
        row.bundle_digest,
        row.options_digest,
        row.configuration_digest,
        row.document_json,
    ):
        raise ReportAuthorityError("report compilation columns or content differ")
    _validate_configuration(record.configuration, scope)
    return record


def _artifact_row(artifact: ReportArtifact) -> ReportArtifactRow:
    scope = artifact.scope
    return ReportArtifactRow(
        artifact_id=artifact.artifact_id,
        compilation_id=artifact.compilation_id,
        assessment_id=scope.assessment_id,
        adjudication_id=scope.adjudication_id,
        context_id=scope.assessment_context_id,
        snapshot_id=scope.phase6_snapshot_id,
        kind=artifact.kind.value,
        question_id=artifact.question_id,
        cluster_origin_id=artifact.cluster_origin_id,
        execution_artifact_id=artifact.execution_ref,
        document_json=canonical_json(artifact),
    )


def report_attempt_state(artifacts: tuple[ReportArtifact, ...]) -> ReportStatusEvent:
    statuses = {
        a.document.event_id: a.document
        for a in artifacts
        if isinstance(a.document, ReportStatusEvent)
    }
    if not statuses or len(statuses) != sum(a.kind == ReportArtifactKind.STATUS for a in artifacts):
        raise ReportAuthorityError("report status chain is missing or duplicated")
    roots = [s for s in statuses.values() if s.predecessor_id is None]
    if len(roots) != 1:
        raise ReportAuthorityError("report status chain has no unique root")
    current = roots[0]
    visited = {current.event_id}
    while True:
        successors = [s for s in statuses.values() if s.predecessor_id == current.event_id]
        if not successors:
            break
        if len(successors) != 1:
            raise ReportAuthorityError("report status chain forked")
        successor = successors[0]
        if successor.event_id in visited or successor.expected_state != current.next_state:
            raise ReportAuthorityError("report status predecessor/state differs")
        visited.add(successor.event_id)
        current = successor
    if len(visited) != len(statuses):
        raise ReportAuthorityError("report status chain is disconnected")
    return current


def _validate_stage_records(
    event: ReportStatusEvent,
    artifacts: tuple[ReportArtifact, ...],
    *,
    accepted_report_id: str | None = None,
) -> None:
    if event.next_state == ReportAttemptState.PLANNED:
        if sum(isinstance(a.document, ReportPlan) for a in artifacts) != 1:
            raise ReportAuthorityError("planned stage requires one committed valid plan")
        return
    fallback_questions = {
        a.question_id for a in artifacts if isinstance(a.document, FallbackRecord)
    }
    if event.next_state == ReportAttemptState.DRAFTED:
        drafts = {a.question_id for a in artifacts if isinstance(a.document, SectionDraft)}
        if not set(range(1, 10)) <= fallback_questions | drafts:
            raise ReportAuthorityError("drafted stage lacks complete nine-question records")
        return
    if event.next_state == ReportAttemptState.VERIFIED:
        verified = {
            a.question_id
            for a in artifacts
            if isinstance(a.document, ClaimVerificationBatch)
            and a.document.accepted
            and a.execution_ref is not None
        }
        if not set(range(1, 10)) <= fallback_questions | verified:
            raise ReportAuthorityError("verified stage lacks complete independent section proof")
        generative = set(range(1, 10)) - fallback_questions
        if generative:
            checks = [
                a.document
                for a in artifacts
                if isinstance(a.document, CompositionCheck) and a.execution_ref is not None
            ]
            contexts = [a.document for a in artifacts if isinstance(a.document, CompositionContext)]
            if len(checks) != 1 or len(contexts) != 1:
                raise ReportAuthorityError("verified generative report lacks one composition proof")
            check, context = checks[0], contexts[0]
            affected = set(check.implicated_question_ids) | {
                draft.question_id
                for draft in context.drafts
                if any(block.block_id in check.implicated_block_ids for block in draft.blocks)
            }
            if not check.accepted and (
                check.indeterminate_scope or not affected or affected & generative
            ):
                raise ReportAuthorityError("composition rejection still implicates public content")
        return
    if event.next_state == ReportAttemptState.ACCEPTED:
        if (
            accepted_report_id is None
            or event.reason != f"Accepted compiled report {accepted_report_id}"
        ):
            raise ReportAuthorityError(
                "ACCEPTED is created only by transactional report acceptance"
            )
        return
    if event.next_state not in {ReportAttemptState.STARTED, ReportAttemptState.FAILED}:
        raise ReportAuthorityError("report stage lacks its completed committed records")


def _accepted_header_id(session: Session, compilation: ReportCompilationRecord) -> str | None:
    row = session.scalar(
        select(CompiledReportRow).where(
            CompiledReportRow.compilation_id == compilation.compilation_id
        )
    )
    if row is None:
        return None
    stored = CompiledAssessmentReport.model_validate_json(row.document_json)
    scope = compilation.scope
    if (
        stored.scope,
        stored.compilation_id,
        stored.report_id,
        canonical_json(stored),
        report_id(stored),
        stored.ir.bundle_digest,
        canonical_hash(stored.ir),
        stored.accepted_at.isoformat(),
    ) != (
        scope,
        compilation.compilation_id,
        row.report_id,
        row.document_json,
        row.report_id,
        row.bundle_digest,
        row.ir_digest,
        row.accepted_at,
    ) or (row.assessment_id, row.adjudication_id, row.context_id, row.snapshot_id) != (
        scope.assessment_id,
        scope.adjudication_id,
        scope.assessment_context_id,
        scope.phase6_snapshot_id,
    ):
        raise ReportAuthorityError("accepted report header columns, identity or scope differ")
    return row.report_id


def _validate_artifact_bindings(
    compilation: ReportCompilationRecord,
    artifact: ReportArtifact,
    artifacts: tuple[ReportArtifact, ...],
    bundle: ReportInputBundle,
    *,
    accepted_report_id: str | None = None,
) -> None:
    if (artifact.scope, artifact.compilation_id) != (compilation.scope, compilation.compilation_id):
        raise ReportAuthorityError("artifact belongs to a foreign report attempt")
    if artifact.artifact_id != report_artifact_id(artifact):
        raise ReportAuthorityError("artifact identity differs from semantic content")
    if artifact.kind not in {
        ReportArtifactKind.DRAFT,
        ReportArtifactKind.REPAIR,
        ReportArtifactKind.EXTRACTION,
        ReportArtifactKind.FIREWALL,
        ReportArtifactKind.VERIFICATION,
        ReportArtifactKind.FALLBACK,
    } and (artifact.question_id is not None or artifact.cluster_origin_id is not None):
        raise ReportAuthorityError("registration, execution and status have no section ownership")
    document = artifact.document
    configs = {c.role: c for c in compilation.configuration.roles}
    if artifact.execution_ref is not None:
        proposal_roles: dict[type[object], ReportSemanticRole] = {
            ReportPlanProposal: ReportSemanticRole.PLANNER,
            SectionDraft: ReportSemanticRole.WRITER,
            SectionDraftFragment: ReportSemanticRole.REPAIR,
            ClaimExtractionProposal: ReportSemanticRole.EXTRACTOR,
            ClaimVerificationBatch: ReportSemanticRole.VERIFIER,
            CompositionCheck: ReportSemanticRole.COMPOSITION,
        }
        role = proposal_roles.get(type(document))
        execution = next(
            (a.document for a in artifacts if a.artifact_id == artifact.execution_ref), None
        )
        if (
            role is None
            or not isinstance(execution, ReportExecutionRecord)
            or execution.scope != artifact.scope
            or execution.compilation_id != artifact.compilation_id
            or execution.role != role
            or execution.method_version != artifact.method_version
            or execution.outcome != "VALIDATED"
            or execution.validated_proposal_hash != canonical_hash(document)
        ):
            raise ReportAuthorityError("proposal differs from its actual validated execution")
    if isinstance(document, ReportMethodRegistration):
        validate_method_registration(document)
        config = configs.get(document.role)
        if config is None or config.port.mode != document.mode:
            raise ReportAuthorityError("method is not selected for this attempt")
    elif isinstance(document, ReportRoleConfiguration):
        if configs.get(document.role) != document:
            raise ReportAuthorityError("configuration differs from immutable attempt selection")
        if document.port.mode != "NOT_CONFIGURED" and not any(
            a.document == document.method for a in artifacts if a.kind == ReportArtifactKind.METHOD
        ):
            raise ReportAuthorityError("configuration lacks prior method registration")
    elif isinstance(document, ReportExecutionRecord):
        config = configs.get(document.role)
        if (
            config is None
            or config.port.mode == "NOT_CONFIGURED"
            or document.configuration_id != config.configuration_id
        ):
            raise ReportAuthorityError("execution configuration is absent or foreign")
        if not any(
            a.document == config for a in artifacts if a.kind == ReportArtifactKind.CONFIGURATION
        ):
            raise ReportAuthorityError("execution lacks committed configuration")
        if not any(
            isinstance(a.document, ReportMethodRegistration)
            and a.document.role == document.role
            and a.document.recovery == document.recovery
            and a.document.method_version == document.method_version
            and a.document.instruction_hash == document.actual_instruction_hash
            for a in artifacts
        ):
            raise ReportAuthorityError("execution lacks matching approved method/instruction")
        if document.recovery:
            predecessor = next(
                (a.document for a in artifacts if a.artifact_id == document.predecessor_ref), None
            )
            if (
                not isinstance(predecessor, ReportExecutionRecord)
                or predecessor.recovery
                or predecessor.outcome != "INVALID"
                or (predecessor.role, predecessor.task_name) != (document.role, document.task_name)
            ):
                raise ReportAuthorityError("execution recovery predecessor differs")
        elif document.predecessor_ref is not None:
            raise ReportAuthorityError("normal execution cannot claim a recovery predecessor")
        if any(
            isinstance(a.document, ReportExecutionRecord)
            and a.document.invocation_id == document.invocation_id
            and a.artifact_id != artifact.artifact_id
            for a in artifacts
        ):
            raise ReportAuthorityError("invocation identity conflicts with committed execution")
    elif isinstance(document, ReportPlanProposal):
        if (
            document.bundle_digest != bundle.bundle_digest
            or artifact.method_version != "p8-plan-v1"
        ):
            raise ReportAuthorityError("plan proposal bundle or method differs")
        # Strict untrusted proposals, including semantic rejection, are retained.
        # The PLAN arm recomputes authority; this arm grants none.
    elif isinstance(document, ReportPlan):
        if artifact.method_version != "p8-plan-firewall-v1":
            raise ReportAuthorityError("validated plan firewall method differs")
        if document.origin == "COVERAGE_FALLBACK":
            expected = build_coverage_plan(bundle, compilation)
        else:
            proposal = ReportPlanProposal(
                scope=document.scope,
                compilation_id=document.compilation_id,
                bundle_digest=document.bundle_digest,
                questions=document.questions,
            )
            expected = validate_report_plan(proposal, bundle, compilation.options)
        if document != expected:
            raise ReportAuthorityError("validated plan content or receipt differs")
    elif isinstance(document, ClaimVerificationBatch):
        if artifact.method_version != "p8-verify-v1":
            raise ReportAuthorityError("verification method differs")
        drafts = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, SectionDraft)
            and canonical_hash(a.document) == document.draft_digest
        )
        extractions = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, ClaimExtractionProposal)
            and canonical_hash(a.document) == document.extraction_digest
        )
        receipts = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, FirewallResult)
            and (a.document.draft_digest, a.document.extraction_digest)
            == (document.draft_digest, document.extraction_digest)
        )
        if len(drafts) != 1 or len(extractions) != 1 or len(receipts) != 1:
            raise ReportAuthorityError("verification lacks one exact committed input set")
        plans = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, ReportPlan) and a.document.plan_id == receipts[0].plan_id
        )
        if len(plans) != 1:
            raise ReportAuthorityError("verification lacks its committed plan")
        context = build_claim_verification_context(drafts[0], extractions[0], bundle, plans[0])
        validate_verification_batch(context, document, receipts[0])
    elif isinstance(document, FallbackRecord):
        if (artifact.method_version, document.method_version) != (
            "p8-fallback-v1",
            "p8-fallback-v1",
        ):
            raise ReportAuthorityError("fallback method differs")
        if (
            document.bundle_digest != bundle.bundle_digest
            or document.question_id != document.section.draft.question_id
        ):
            raise ReportAuthorityError("fallback bundle or question differs")
        validate_fallback_section(document.section, bundle, compilation)
    elif isinstance(document, CompositionContext):
        if artifact.method_version != "p8-compose-check-v1" or artifact.execution_ref is not None:
            raise ReportAuthorityError("composition input method or execution differs")
        if any(
            isinstance(a.document, CompositionContext) and a.artifact_id != artifact.artifact_id
            for a in artifacts
        ):
            raise ReportAuthorityError("composition input is already committed")
        _validate_composition_input(document, compilation, bundle, artifacts)
    elif isinstance(document, CompositionCheck):
        contexts = tuple(
            a.document for a in artifacts if isinstance(a.document, CompositionContext)
        )
        if artifact.method_version != "p8-compose-check-v1" or len(contexts) != 1:
            raise ReportAuthorityError("composition result lacks its exact committed input")
        validate_composition_check(contexts[0], document)
        if artifact.execution_ref is None:
            raise ReportAuthorityError("composition result lacks its actual execution")
        if any(
            isinstance(a.document, CompositionCheck) and a.artifact_id != artifact.artifact_id
            for a in artifacts
        ):
            raise ReportAuthorityError("composition cannot choose another completed result")
        execution = next(a.document for a in artifacts if a.artifact_id == artifact.execution_ref)
        config = configs[ReportSemanticRole.COMPOSITION]
        if (
            config.port.mode == "PORT_PROTOCOL"
            and isinstance(execution, ReportExecutionRecord)
            and execution.request_hash != canonical_hash(contexts[0])
        ):
            raise ReportAuthorityError("composition execution checks a different actual input")
    elif isinstance(document, FirewallResult):
        if artifact.method_version != document.method_version:
            raise ReportAuthorityError("firewall receipt method differs")
        drafts = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, SectionDraft)
            and canonical_hash(a.document) == document.draft_digest
        )
        extractions = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, ClaimExtractionProposal)
            and canonical_hash(a.document) == document.extraction_digest
        )
        plans = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, ReportPlan) and a.document.plan_id == document.plan_id
        )
        if len(drafts) != 1 or len(extractions) != 1 or len(plans) != 1:
            raise ReportAuthorityError("firewall receipt lacks one exact committed input set")
        if document != check_report_claims(drafts[0], extractions[0], bundle, plans[0]):
            raise ReportAuthorityError(
                "firewall receipt differs from exact deterministic recomputation"
            )
    elif isinstance(document, ClaimExtractionProposal):
        if artifact.method_version != "p8-extract-v1":
            raise ReportAuthorityError("extraction method differs")
        drafts = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, SectionDraft)
            and canonical_hash(a.document) == document.draft_digest
        )
        if len(drafts) != 1:
            raise ReportAuthorityError("extraction lacks one exact committed public draft")
        validate_claim_extraction(drafts[0], document)
    elif isinstance(document, (SectionDraft, SectionDraftFragment, RepairCluster)):
        plans = tuple(a.document for a in artifacts if isinstance(a.document, ReportPlan))
        if len(plans) != 1:
            raise ReportAuthorityError("section proposal lacks one committed validated plan")
        if isinstance(document, SectionDraft) and artifact.method_version == "p8-write-v1":
            # Public writer text remains untrusted, including rejected realizations.
            return
        if artifact.method_version != "p8-repair-v1":
            raise ReportAuthorityError("section proposal method differs")
        _validate_repair_document(compilation, artifact, artifacts, bundle, plans[0])
    else:
        if (
            document.event_id != report_status_event_id(document)
            or artifact.method_version != "p8-bundle-v1"
        ):
            raise ReportAuthorityError("status identity or method differs")
        _validate_stage_records(document, artifacts, accepted_report_id=accepted_report_id)


def _validate_composition_input(
    context: CompositionContext,
    compilation: ReportCompilationRecord,
    bundle: ReportInputBundle,
    artifacts: tuple[ReportArtifact, ...],
) -> None:
    if (
        context.scope,
        context.compilation_id,
        context.bundle_digest,
        context.language_envelopes,
        context.target_findings,
        context.overall_finding,
        context.coverage_obligations,
    ) != (
        bundle.scope,
        compilation.compilation_id,
        bundle.bundle_digest,
        bundle.language_envelopes,
        bundle.target_findings,
        bundle.overall_finding,
        bundle.coverage_obligations,
    ):
        raise ReportAuthorityError("composition input changes native findings or obligations")
    if (
        tuple(d.question_id for d in context.drafts) != tuple(range(1, 10))
        or len(context.extractions) != 9
    ):
        raise ReportAuthorityError("composition input requires complete Q1–Q9")
    probe = CompositionCheck(
        scope=context.scope,
        compilation_id=context.compilation_id,
        narrative_digest=context.narrative_digest,
        claims_digest=context.claims_digest,
        permission_digest=context.permission_digest,
        disposition=VerificationDisposition.SUPPORTED,
        implicated_block_ids=(),
        implicated_question_ids=(),
        indeterminate_scope=False,
        reason_codes=(),
        reason="Mechanical digest validation only, never semantic acceptance",
    )
    validate_composition_check(context, probe)
    for draft, projection in zip(context.drafts, context.extractions, strict=True):
        validate_claim_extraction(draft, projection)
        known = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, FallbackRecord)
            and a.document.section.draft == draft
            and a.document.section.claims == projection.claims
            and a.document.section.basis_links == projection.basis_links
        )
        if known:
            continue
        drafts = tuple(
            a for a in artifacts if isinstance(a.document, SectionDraft) and a.document == draft
        )
        extractions = tuple(
            a
            for a in artifacts
            if isinstance(a.document, ClaimExtractionProposal)
            and a.document.draft_digest == canonical_hash(draft)
            and (a.document.claims, a.document.basis_links)
            == (projection.claims, projection.basis_links)
        )
        if len(drafts) != 1 or len(extractions) != 1 or extractions[0].execution_ref is None:
            raise ReportAuthorityError(
                "composition lacks exact independently extracted public drafts"
            )
        if drafts[0].method_version == "p8-write-v1" and drafts[0].execution_ref is None:
            raise ReportAuthorityError("composition draft lacks its actual writer execution")
        if drafts[0].method_version == "p8-repair-v1" and any(
            isinstance(a.document, SectionDraftFragment)
            and a.document.question_id == draft.question_id
            and a.execution_ref is None
            for a in artifacts
        ):
            raise ReportAuthorityError("composition repair lacks its actual execution")
        accepted = tuple(
            a
            for a in artifacts
            if isinstance(a.document, ClaimVerificationBatch)
            and a.document.accepted
            and a.execution_ref is not None
            and (a.document.draft_digest, a.document.extraction_digest)
            == (canonical_hash(draft), canonical_hash(extractions[0].document))
        )
        if len(accepted) != 1:
            raise ReportAuthorityError("composition lacks exact independent support/completeness")


def _validate_repair_document(
    compilation: ReportCompilationRecord,
    artifact: ReportArtifact,
    artifacts: tuple[ReportArtifact, ...],
    bundle: ReportInputBundle,
    plan: ReportPlan,
) -> None:
    document = artifact.document
    drafts = tuple(
        a.document
        for a in artifacts
        if isinstance(a.document, SectionDraft) and a.artifact_id != artifact.artifact_id
    )
    clusters = tuple(a.document for a in artifacts if isinstance(a.document, RepairCluster))
    if isinstance(document, RepairCluster):
        if document.cluster_id != repair_cluster_id(document):
            raise ReportAuthorityError("repair cluster identity differs")
        originals = tuple(
            a.document
            for a in artifacts
            if isinstance(a.document, SectionDraft)
            and a.method_version == "p8-write-v1"
            and repair_origin_id(a.document, document.original_spans) == document.origin_id
        )
        if len(originals) != 1:
            raise ReportAuthorityError("repair lacks its exact original public draft")
        original = originals[0]
        if any(c.origin_id == document.origin_id and c != document for c in clusters):
            raise ReportAuthorityError("repair origin was consumed with different ownership")
        if any(
            c.question_id == document.question_id
            and c.original_block_ids == document.original_block_ids
            and c.origin_id != document.origin_id
            for c in clusters
        ):
            raise ReportAuthorityError(
                "replacement segmentation cannot create another repair origin"
            )
        supported = False
        for a in artifacts:
            fw = a.document
            if not isinstance(fw, FirewallResult) or fw.draft_digest != canonical_hash(original):
                continue
            extraction = next(
                (
                    e.document
                    for e in artifacts
                    if isinstance(e.document, ClaimExtractionProposal)
                    and canonical_hash(e.document) == fw.extraction_digest
                ),
                None,
            )
            if extraction is None:
                continue
            batches = tuple(
                e.document
                for e in artifacts
                if isinstance(e.document, ClaimVerificationBatch)
                and e.document.draft_digest == canonical_hash(original)
                and e.document.extraction_digest == canonical_hash(extraction)
            )
            for batch in batches or (None,):
                if document in select_repair_clusters(
                    original, report_violations(original, extraction, fw, batch)
                ):
                    supported = True
        if not supported:
            raise ReportAuthorityError("repair consumption lacks exact committed failure receipts")
    elif isinstance(document, SectionDraftFragment):
        owned = tuple(c for c in clusters if c.origin_id == document.cluster_origin_id)
        if len(owned) != 1:
            raise ReportAuthorityError("repair fragment lacks one consumed origin")
        cluster = owned[0]
        originals = tuple(
            d for d in drafts if repair_origin_id(d, cluster.original_spans) == cluster.origin_id
        )
        if len(originals) != 1:
            raise ReportAuthorityError("repair fragment lost its original public draft")
        original = originals[0]
        context = build_section_context(
            bundle, plan, question_id=cluster.question_id, compilation=compilation
        )
        local = LocalRepairContext(
            scope=compilation.scope,
            compilation_id=compilation.compilation_id,
            section_context=context,
            cluster=cluster,
            original_blocks=tuple(
                b for b in original.blocks if b.block_id in cluster.original_block_ids
            ),
            neighboring_blocks=tuple(
                b for b in original.blocks if b.block_id not in cluster.original_block_ids
            ),
            relevant_basis_refs=context.selected_basis_refs,
            required_qualification_refs=(),
        )
        validate_repair_fragment(document, cluster, local)
        if any(
            isinstance(a.document, SectionDraftFragment)
            and a.document.cluster_origin_id == cluster.origin_id
            and a.artifact_id != artifact.artifact_id
            for a in artifacts
        ):
            raise ReportAuthorityError("repair origin cannot receive a second semantic fragment")
    elif isinstance(document, SectionDraft):
        if artifact.execution_ref is not None:
            raise ReportAuthorityError("derived repaired draft cannot claim a writer execution")
        matches = 0
        for a in artifacts:
            fragment = a.document
            if not isinstance(fragment, SectionDraftFragment):
                continue
            cluster = next((c for c in clusters if c.origin_id == fragment.cluster_origin_id), None)
            if cluster is None:
                continue
            for parent in drafts:
                if set(cluster.original_block_ids) <= {b.block_id for b in parent.blocks}:
                    if apply_repair_fragment(parent, fragment, cluster) == document:
                        matches += 1
        if matches != 1:
            raise ReportAuthorityError(
                "repaired draft lacks one exact parent and committed fragment"
            )


def _read_report_artifact_documents(
    session: Session, compilation_locator: str
) -> tuple[ReportArtifact, ...]:
    # Keep the complete typed closure, but release each serialized row after
    # strict decoding and exact byte/column comparison. The cursor is closed
    # before native cross-artifact validation uses this same transaction.
    documents: list[ReportArtifact] = []
    statement = (
        select(ReportArtifactRow)
        .where(ReportArtifactRow.compilation_id == compilation_locator)
        .order_by(ReportArtifactRow.artifact_id)
        .execution_options(yield_per=1)
    )
    with session.scalars(statement) as rows:
        for row in rows:
            artifact = ReportArtifact.model_validate_json(row.document_json)
            scope = artifact.scope
            if (
                artifact.artifact_id,
                artifact.compilation_id,
                scope.assessment_id,
                scope.adjudication_id,
                scope.assessment_context_id,
                scope.phase6_snapshot_id,
                artifact.kind.value,
                artifact.question_id,
                artifact.cluster_origin_id,
                artifact.execution_ref,
                canonical_json(artifact),
            ) != (
                row.artifact_id,
                row.compilation_id,
                row.assessment_id,
                row.adjudication_id,
                row.context_id,
                row.snapshot_id,
                row.kind,
                row.question_id,
                row.cluster_origin_id,
                row.execution_artifact_id,
                row.document_json,
            ):
                raise ReportAuthorityError("persisted report artifact columns or content differ")
            documents.append(artifact)
            del row
    return tuple(documents)


def load_report_artifacts_in_session(
    session: Session, compilation: ReportCompilationRecord, bundle: ReportInputBundle
) -> tuple[ReportArtifact, ...]:
    artifacts = _read_report_artifact_documents(session, compilation.compilation_id)
    accepted_id = _accepted_header_id(session, compilation)
    for artifact in artifacts:
        _validate_artifact_bindings(
            compilation, artifact, artifacts, bundle, accepted_report_id=accepted_id
        )
    report_attempt_state(artifacts)
    return artifacts


def revalidate_report_bundle_in_session(
    session: Session, loader: Callable[..., Phase6AssessmentView], record: ReportCompilationRecord
) -> ReportInputBundle:
    bundle = load_report_input_bundle_in_session(
        session, loader, record.scope.assessment_id, adjudication_id=record.scope.adjudication_id
    )
    if bundle.scope != record.scope or bundle.bundle_digest != record.bundle_digest:
        raise ReportAuthorityError("report upstream bundle or scope changed")
    return bundle


def begin_report_compilation(
    engine: Engine,
    loader: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    adjudication_id: str,
    options: ReportOptions,
    configuration: ReportCompilationConfiguration,
    attempt_token: str | None = None,
) -> ReportCompilationRecord:
    try:
        options = ReportOptions.model_validate(options.model_dump(mode="json"))
        configuration = ReportCompilationConfiguration.model_validate(
            configuration.model_dump(mode="json")
        )
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            bundle = load_report_input_bundle_in_session(
                session, loader, assessment_id, adjudication_id=adjudication_id
            )
            _validate_configuration(configuration, bundle.scope)
            if options.render_policy_version != "p8-render-v1":
                raise ReportAuthorityError("report renderer is unapproved")
            key = compilation_key(bundle.scope, bundle.bundle_digest, options, configuration)
            token = attempt_token if attempt_token is not None else uuid4().hex
            locator = compilation_id(key, token)
            record = ReportCompilationRecord(
                scope=bundle.scope,
                compilation_id=locator,
                compilation_key=key,
                attempt_token=token,
                options=options,
                configuration=bind_compilation_configuration(configuration, bundle.scope, locator),
                bundle_digest=bundle.bundle_digest,
                started_at=datetime.now(UTC),
            )
            if session.get(ReportCompilationRow, locator) is not None:
                stored = load_report_compilation_in_session(session, locator)
                if stored.model_dump(exclude={"started_at"}) != record.model_dump(
                    exclude={"started_at"}
                ):
                    raise ReportAuthorityError(
                        "compilation identity conflicts with committed attempt"
                    )
                load_report_artifacts_in_session(session, stored, bundle)
                session.commit()
                return stored
            scope = record.scope
            session.add(
                ReportCompilationRow(
                    compilation_id=locator,
                    compilation_key=key,
                    attempt_token=token,
                    assessment_id=scope.assessment_id,
                    adjudication_id=scope.adjudication_id,
                    context_id=scope.assessment_context_id,
                    snapshot_id=scope.phase6_snapshot_id,
                    bundle_digest=record.bundle_digest,
                    options_digest=canonical_hash(options),
                    configuration_digest=canonical_hash(record.configuration),
                    document_json=canonical_json(record),
                )
            )
            session.flush()
            initial = ReportStatusEvent(
                scope=scope,
                compilation_id=locator,
                event_id="pending",
                next_state=ReportAttemptState.STARTED,
                reason="Report compilation started",
                observed_at=record.started_at,
            )
            initial = initial.model_copy(update={"event_id": report_status_event_id(initial)})
            session.add(
                _artifact_row(
                    make_report_artifact(
                        record, ReportArtifactKind.STATUS, initial, method_version="p8-bundle-v1"
                    )
                )
            )
            session.commit()
            return record
    except (ValueError, SQLAlchemyError) as exc:
        if isinstance(exc, ReportAuthorityError):
            raise
        raise ReportAuthorityError("report compilation begin failed authority validation") from exc


def _revalidate_artifact(value: object) -> ReportArtifact:
    return ReportArtifact.model_validate(
        value.model_dump(mode="json") if isinstance(value, ReportArtifact) else value
    )


def record_report_artifact(
    engine: Engine,
    loader: Callable[..., Phase6AssessmentView],
    compilation_id: str,
    artifact: ReportArtifact,
) -> str:
    try:
        artifact = _revalidate_artifact(artifact)
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            compilation = load_report_compilation_in_session(session, compilation_id)
            bundle = revalidate_report_bundle_in_session(session, loader, compilation)
            artifacts = load_report_artifacts_in_session(session, compilation, bundle)
            existing = next((a for a in artifacts if a.artifact_id == artifact.artifact_id), None)
            _validate_artifact_bindings(
                compilation,
                artifact,
                artifacts,
                bundle,
                accepted_report_id=_accepted_header_id(session, compilation)
                if existing is not None
                else None,
            )
            if existing is not None:
                if report_artifact_semantic_content(existing) != report_artifact_semantic_content(
                    artifact
                ):
                    raise ReportAuthorityError("artifact identity conflicts with committed content")
                session.commit()
                return existing.artifact_id
            current = report_attempt_state(artifacts)
            if current.next_state in {ReportAttemptState.ACCEPTED, ReportAttemptState.FAILED}:
                raise ReportAuthorityError("terminal report attempt cannot append artifacts")
            if (
                current.next_state == ReportAttemptState.VERIFIED
                and artifact.kind != ReportArtifactKind.STATUS
            ):
                raise ReportAuthorityError("verified attempt cannot append new semantic artifacts")
            if artifact.kind in {ReportArtifactKind.PLAN_PROPOSAL, ReportArtifactKind.PLAN}:
                if current.next_state != ReportAttemptState.STARTED or any(
                    a.kind == artifact.kind for a in artifacts
                ):
                    raise ReportAuthorityError(
                        "report permits one planner proposal and one completed plan"
                    )
            if isinstance(artifact.document, ReportStatusEvent) and (
                artifact.document.predecessor_id != current.event_id
                or artifact.document.expected_state != current.next_state
            ):
                raise ReportAuthorityError(
                    "status predecessor differs from current committed state"
                )
            session.add(_artifact_row(artifact))
            session.commit()
            return artifact.artifact_id
    except (ValueError, SQLAlchemyError) as exc:
        if isinstance(exc, ReportAuthorityError):
            raise
        raise ReportAuthorityError("report artifact failed authority validation") from exc


def load_report_artifacts(
    engine: Engine, loader: Callable[..., Phase6AssessmentView], compilation_id: str
) -> tuple[ReportArtifact, ...]:
    try:
        with Session(engine) as session:
            session.execute(text("BEGIN"))
            compilation = load_report_compilation_in_session(session, compilation_id)
            bundle = revalidate_report_bundle_in_session(session, loader, compilation)
            artifacts = load_report_artifacts_in_session(session, compilation, bundle)
            session.commit()
            return artifacts
    except (ValueError, SQLAlchemyError) as exc:
        if isinstance(exc, ReportAuthorityError):
            raise
        raise ReportAuthorityError("report artifact load failed authority validation") from exc


def _dependency_row(report: CompiledAssessmentReport, dependency: object) -> ReportDependencyRow:
    from novelty_harness.reporting.models import ReportDependency

    if not isinstance(dependency, ReportDependency):
        raise ReportAuthorityError("compiled dependency is not a strict typed arm")
    ref = dependency.authority_ref
    return ReportDependencyRow(
        report_id=report.report_id,
        dependency_kind=dependency.dependency_kind,
        dependency_id=dependency.dependency_id,
        expected_digest=dependency.expected_digest,
        upstream_kind=ref.kind.value if ref else None,
        native_id=ref.native_id if ref else None,
        path_json=canonical_json(list(ref.path)) if ref else None,
        scope_json=canonical_json(ref.scope) if ref else None,
        report_artifact_id=dependency.report_artifact_id,
        document_json=canonical_json(dependency),
    )


def accept_compiled_report(
    engine: Engine,
    loader: Callable[..., Phase6AssessmentView],
    compilation_id: str,
    proposed: CompiledAssessmentReport,
) -> str:
    from novelty_harness.evidence.graph.report_validation import validate_compiled_report_in_session

    try:
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            _, artifacts = validate_compiled_report_in_session(
                session, loader, compilation_id, proposed
            )
            existing = session.scalar(
                select(CompiledReportRow).where(CompiledReportRow.compilation_id == compilation_id)
            )
            if existing is not None:
                if report_attempt_state(artifacts).next_state != ReportAttemptState.ACCEPTED:
                    raise ReportAuthorityError("accepted report lacks its terminal receipt")
                original = CompiledAssessmentReport.model_validate_json(existing.document_json)
                if original.report_id != proposed.report_id or report_id(original) != report_id(
                    proposed
                ):
                    raise ReportAuthorityError(
                        "compiled report conflicts with immutable acceptance"
                    )
                _validate_dependency_rows(session, original)
                session.commit()
                return original.report_id
            current = report_attempt_state(artifacts)
            if current.next_state != ReportAttemptState.VERIFIED:
                raise ReportAuthorityError("only VERIFIED can atomically accept a report")
            accepted = proposed.model_copy(update={"accepted_at": datetime.now(UTC)})
            scope = accepted.scope
            session.add(
                CompiledReportRow(
                    report_id=accepted.report_id,
                    compilation_id=compilation_id,
                    assessment_id=scope.assessment_id,
                    adjudication_id=scope.adjudication_id,
                    context_id=scope.assessment_context_id,
                    snapshot_id=scope.phase6_snapshot_id,
                    bundle_digest=accepted.ir.bundle_digest,
                    ir_digest=canonical_hash(accepted.ir),
                    document_json=canonical_json(accepted),
                    accepted_at=accepted.accepted_at.isoformat(),
                )
            )
            session.flush()
            for dependency in accepted.dependencies:
                session.add(_dependency_row(accepted, dependency))
            compilation = load_report_compilation_in_session(session, compilation_id)
            status = ReportStatusEvent(
                scope=scope,
                compilation_id=compilation_id,
                event_id="pending",
                predecessor_id=current.event_id,
                expected_state=ReportAttemptState.VERIFIED,
                next_state=ReportAttemptState.ACCEPTED,
                reason=f"Accepted compiled report {accepted.report_id}",
                observed_at=accepted.accepted_at,
            )
            status = status.model_copy(update={"event_id": report_status_event_id(status)})
            session.add(
                _artifact_row(
                    make_report_artifact(
                        compilation,
                        ReportArtifactKind.STATUS,
                        status,
                        method_version="p8-bundle-v1",
                    )
                )
            )
            session.flush()
            _validate_dependency_rows(session, accepted)
            session.commit()
            return accepted.report_id
    except (ValueError, SQLAlchemyError) as error:
        if isinstance(error, ReportAuthorityError):
            raise
        raise ReportAuthorityError("report acceptance failed authoritative validation") from error


def _validate_dependency_rows(session: Session, report: CompiledAssessmentReport) -> None:
    rows = tuple(
        session.scalars(
            select(ReportDependencyRow).where(ReportDependencyRow.report_id == report.report_id)
        )
    )
    expected = {
        (d.dependency_kind, d.dependency_id): _dependency_row(report, d)
        for d in report.dependencies
    }
    if len(expected) != len(report.dependencies) or len(rows) != len(expected):
        raise ReportAuthorityError("accepted dependency rows are missing, extra or duplicated")
    fields = tuple(column.name for column in ReportDependencyRow.__table__.columns)
    for row in rows:
        match = expected.get((row.dependency_kind, row.dependency_id))
        if match is None or any(getattr(row, field) != getattr(match, field) for field in fields):
            raise ReportAuthorityError("accepted dependency row differs from exact typed closure")


def load_compiled_report_in_session(
    session: Session,
    load_view_in_session: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    report_id: str,
) -> CompiledAssessmentReport:
    from novelty_harness.evidence.graph.report_validation import validate_compiled_report_in_session

    row = session.get(CompiledReportRow, report_id)
    if row is None or row.assessment_id != assessment_id:
        raise ReportAuthorityError(
            "accepted report locator is missing or belongs to another assessment"
        )
    stored = CompiledAssessmentReport.model_validate_json(row.document_json)
    compilation = load_report_compilation_in_session(session, row.compilation_id)
    if _accepted_header_id(session, compilation) != report_id:
        raise ReportAuthorityError("accepted report locator differs from its immutable manifest")
    _, artifacts = validate_compiled_report_in_session(
        session, load_view_in_session, compilation.compilation_id, stored
    )
    if report_attempt_state(artifacts).next_state != ReportAttemptState.ACCEPTED:
        raise ReportAuthorityError("accepted report lacks its terminal receipt")
    _validate_dependency_rows(session, stored)
    return stored


def load_compiled_report(
    engine: Engine,
    loader: Callable[..., Phase6AssessmentView],
    assessment_id: AssessmentId,
    *,
    report_id: str,
) -> CompiledAssessmentReport:
    try:
        with Session(engine) as session:
            session.execute(text("BEGIN"))
            stored = load_compiled_report_in_session(
                session, loader, assessment_id, report_id=report_id
            )
            session.commit()
            return stored
    except (ValueError, SQLAlchemyError) as error:
        if isinstance(error, ReportAuthorityError):
            raise
        raise ReportAuthorityError("report read failed authoritative validation") from error

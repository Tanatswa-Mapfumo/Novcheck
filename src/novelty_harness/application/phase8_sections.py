"""Durable independent section assurance with one consumed repair per original origin."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import JsonValue

from novelty_harness.application.phase8_execution import (
    completed_invocation,
    invocation_configuration,
)
from novelty_harness.application.phase8_model_adapter import ReportModelAdapter
from novelty_harness.ports.reporting import ReportPorts
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportArtifactDocument,
    ReportArtifactKind,
    ReportCompilationRecord,
    make_report_artifact,
)
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.claims import (
    ClaimExtractionProposal,
    build_claim_extraction_context,
    validate_claim_extraction,
)
from novelty_harness.reporting.drafts import (
    SectionContext,
    SectionDraft,
    SectionDraftFragment,
    validate_section_draft,
)
from novelty_harness.reporting.execution import (
    ReportExecutionObservations,
    ReportExecutionRecord,
    ReportMethodRegistration,
    ReportRoleConfiguration,
)
from novelty_harness.reporting.fallback import FallbackRecord, render_fallback_section
from novelty_harness.reporting.firewall import FirewallResult, check_report_claims
from novelty_harness.reporting.models import ReportProposalError, ReportScoped, ReportSemanticRole
from novelty_harness.reporting.obligations import ObligationSatisfaction
from novelty_harness.reporting.plan import ReportPlan
from novelty_harness.reporting.prompts import approved_instruction
from novelty_harness.reporting.repair import (
    LocalRepairContext,
    RepairCluster,
    apply_repair_fragment,
    repair_available,
    report_violations,
    select_repair_clusters,
    validate_repair_fragment,
)
from novelty_harness.reporting.repository import ReportAuthorityError, ReportRepository
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    CompositionCheck,
    CompositionContext,
    VerifiedSection,
    build_claim_verification_context,
    build_composition_context,
    validate_composition_check,
    validate_verification_batch,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def record_section_artifact(
    compilation: ReportCompilationRecord,
    repository: ReportRepository,
    kind: ReportArtifactKind,
    document: ReportArtifactDocument,
    method: str,
    *,
    execution_ref: str | None = None,
) -> str:
    artifact = make_report_artifact(
        compilation, kind, document, method_version=method, execution_ref=execution_ref
    )
    return repository.record_report_artifact(compilation.compilation_id, artifact)


def _check_invocation_budget(
    compilation: ReportCompilationRecord,
    selected: ReportRoleConfiguration,
    context: ReportScoped,
    executions: tuple[ReportExecutionRecord, ...],
) -> None:
    """Reserve recovery and charge unknown usage conservatively, without fake observations."""
    limits = compilation.options.limits
    calls = (
        2
        if selected.port.mode == "SEMANTIC_RUNNER" and selected.role != ReportSemanticRole.REPAIR
        else 1
    )
    if len(executions) + calls > limits.max_calls:
        raise ReportProposalError("report call budget cannot cover the invocation and recovery")
    # This runtime has no price schedule. An unknown monetary charge cannot fit
    # an asserted monetary ceiling merely by being recorded as zero.
    if limits.max_cost_usd is not None:
        raise ReportProposalError("report cost budget has no configured charge bound")
    output = selected.port.sampling.max_output_tokens or 4 * limits.max_question_chars
    configurations = {r.configuration_id: r for r in compilation.configuration.roles}
    used = 0
    for execution in executions:
        if execution.observations.tokens is not None:
            used += execution.observations.tokens
        else:
            previous = configurations.get(execution.configuration_id)
            if previous is None:
                raise ReportAuthorityError("budget execution has no selected configuration")
            previous_output = (
                previous.port.sampling.max_output_tokens or 4 * limits.max_question_chars
            )
            used += 4 * limits.max_context_chars + previous_output
    request_chars = len(canonical_json(context)) + len(approved_instruction(selected.role))
    if (
        request_chars > limits.max_context_chars
        or used + calls * (4 * request_chars + output) > limits.max_tokens
    ):
        raise ReportProposalError("report token or context budget cannot cover the invocation")


async def invoke_report_operation[T: ReportScoped](
    compilation: ReportCompilationRecord,
    repository: ReportRepository,
    port: object,
    role: ReportSemanticRole,
    context: ReportScoped,
    output_type: type[T],
    call: Callable[[], Awaitable[object]],
) -> tuple[T, str]:
    """Register before dispatch, keep every actual attempt, never invent model audits."""
    selected = invocation_configuration(port, role, compilation)
    artifacts = repository.load_report_artifacts(compilation.compilation_id)
    registered = {a.artifact_id for a in artifacts}

    def register(kind: ReportArtifactKind, document: ReportArtifactDocument) -> None:
        artifact = make_report_artifact(
            compilation, kind, document, method_version=selected.method_version
        )
        if artifact.artifact_id not in registered:
            repository.record_report_artifact(compilation.compilation_id, artifact)
            registered.add(artifact.artifact_id)

    for kind, doc in (
        (ReportArtifactKind.METHOD, selected.method),
        (ReportArtifactKind.CONFIGURATION, selected),
    ):
        register(kind, doc)
    if selected.port.mode == "SEMANTIC_RUNNER" and role != ReportSemanticRole.REPAIR:
        recovery = ReportMethodRegistration(
            scope=compilation.scope,
            compilation_id=compilation.compilation_id,
            role=role,
            method_version=selected.method_version,
            mode="SEMANTIC_RUNNER",
            recovery=True,
            instruction_hash=canonical_hash(approved_instruction(role, recovery=True)),
        )
        register(ReportArtifactKind.METHOD, recovery)
    _check_invocation_budget(
        compilation,
        selected,
        context,
        tuple(a.document for a in artifacts if isinstance(a.document, ReportExecutionRecord)),
    )
    previous: set[str] = (
        {e.invocation_id for e in port.executions}
        if isinstance(port, ReportModelAdapter)
        else set()
    )
    request = context.model_dump(mode="json")
    raw: object = None
    raised: Exception | None = None
    try:
        raw = await call()
    except Exception as error:
        raised = error
    if isinstance(port, ReportModelAdapter):
        for execution in port.executions:
            if (
                execution.invocation_id not in previous
                and execution.role == role
                and (
                    port.invocation_context_digest(execution.invocation_id)
                    == canonical_hash(request)
                )
            ):
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.EXECUTION,
                    execution,
                    execution.method_version,
                )
    if raised is not None:
        if not isinstance(port, ReportModelAdapter):
            failure = ReportExecutionRecord(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                invocation_id="p8invoke_" + uuid4().hex,
                role=role,
                task_name="phase8-" + role.value.lower(),
                method_version=selected.method_version,
                actual_instruction_hash=selected.instruction_hash,
                configuration_id=selected.configuration_id,
                request_hash=canonical_hash(request),
                outcome="PROVIDER_FAILURE",
                observations=ReportExecutionObservations(observed_at=datetime.now(UTC)),
            )
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.EXECUTION,
                failure,
                selected.method_version,
            )
        raise ReportProposalError("report provider operation failed") from raised
    try:
        if not isinstance(raw, output_type):
            raise ReportProposalError("report port returned the wrong strict proposal type")
        proposal = output_type.model_validate_json(canonical_json(raw), strict=True)
        execution = completed_invocation(port, proposal, selected, request)
    except ValueError as error:
        if not isinstance(port, ReportModelAdapter):
            try:
                raw_hash = canonical_hash(cast(JsonValue, raw))
            except (ValueError, TypeError):
                raw_hash = None
            failure = ReportExecutionRecord(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                invocation_id="p8invoke_" + uuid4().hex,
                role=role,
                task_name="phase8-" + role.value.lower(),
                method_version=selected.method_version,
                actual_instruction_hash=selected.instruction_hash,
                configuration_id=selected.configuration_id,
                request_hash=canonical_hash(request),
                raw_response_hash=raw_hash,
                outcome="INVALID",
                observations=ReportExecutionObservations(observed_at=datetime.now(UTC)),
            )
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.EXECUTION,
                failure,
                selected.method_version,
            )
        raise ReportProposalError("report output failed strict invocation binding") from error
    execution_ref = record_section_artifact(
        compilation, repository, ReportArtifactKind.EXECUTION, execution, execution.method_version
    )
    return proposal, execution_ref


def _verified(
    compilation: ReportCompilationRecord,
    context: SectionContext,
    draft: SectionDraft,
    extraction: ClaimExtractionProposal,
    verification_ref: str,
    source_refs: tuple[str, ...],
    repaired_ids: set[str],
) -> VerifiedSection:
    satisfaction: list[ObligationSatisfaction] = []
    for obligation in context.coverage_obligations:
        blocks = tuple(
            b.block_id for b in draft.blocks if obligation.obligation_id in b.obligation_ids
        )
        ids = tuple(c.claim_id for c in extraction.claims if c.block_id in blocks)
        satisfaction.append(
            ObligationSatisfaction(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                obligation_id=obligation.obligation_id,
                question_id=context.question_id,
                block_ids=blocks,
                claim_ids=ids,
                basis_refs=obligation.authority_refs,
                verification_refs=(verification_ref,),
            )
        )
    return VerifiedSection(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        draft=draft,
        claims=extraction.claims,
        basis_links=extraction.basis_links,
        verification_refs=(verification_ref,),
        obligation_satisfaction=tuple(satisfaction),
        block_origins={
            b.block_id: "GENERATIVE_REPAIRED"
            if b.block_id in repaired_ids
            else "GENERATIVE_ACCEPTED"
            for b in draft.blocks
        },
        source_artifact_refs=tuple(dict.fromkeys(source_refs)),
    )


def _replay_verified_section(
    compilation: ReportCompilationRecord,
    context: SectionContext,
    bundle: ReportInputBundle,
    plan: ReportPlan,
    artifacts: tuple[ReportArtifact, ...],
) -> VerifiedSection | None:
    """Reconstruct accepted text from committed checks, never from an origin label."""
    candidates: list[VerifiedSection] = []
    local = tuple(a for a in artifacts if a.question_id == context.question_id)
    for artifact in local:
        if not isinstance(artifact.document, SectionDraft):
            continue
        try:
            draft = validate_section_draft(artifact.document, context)
        except ValueError:
            continue
        extractions = tuple(
            a
            for a in local
            if isinstance(a.document, ClaimExtractionProposal)
            and a.document.draft_digest == canonical_hash(draft)
        )
        if len(extractions) != 1:
            continue
        extraction_artifact = extractions[0]
        extraction = extraction_artifact.document
        assert isinstance(extraction, ClaimExtractionProposal)
        extraction = validate_claim_extraction(draft, extraction)
        firewall = check_report_claims(draft, extraction, bundle, plan)
        firewalls = tuple(a for a in local if a.document == firewall)
        if not firewall.accepted or len(firewalls) != 1:
            continue
        checked = build_claim_verification_context(draft, extraction, bundle, plan)
        matching: list[ReportArtifact] = []
        for proof in local:
            if (
                not isinstance(proof.document, ClaimVerificationBatch)
                or not proof.document.accepted
            ):
                continue
            try:
                validate_verification_batch(checked, proof.document, firewall)
            except ValueError:
                continue
            matching.append(proof)
        if len(matching) != 1:
            continue
        repairs = tuple(a for a in local if a.kind == ReportArtifactKind.REPAIR)
        repaired = {
            b.block_id
            for a in repairs
            if isinstance(a.document, SectionDraftFragment)
            for b in a.document.blocks
        }
        sources = (
            artifact.artifact_id,
            extraction_artifact.artifact_id,
            firewalls[0].artifact_id,
            matching[0].artifact_id,
            *(a.artifact_id for a in repairs),
        )
        candidates.append(
            _verified(
                compilation, context, draft, extraction, matching[0].artifact_id, sources, repaired
            )
        )
    if len(candidates) > 1:
        raise ReportAuthorityError("section has multiple completed accepted realizations")
    return candidates[0] if candidates else None


async def assure_report_section(
    compilation: ReportCompilationRecord,
    context: SectionContext,
    *,
    bundle: ReportInputBundle,
    plan: ReportPlan,
    ports: ReportPorts,
    repository: ReportRepository,
) -> VerifiedSection:
    if (
        compilation.scope,
        compilation.bundle_digest,
        context.scope,
        context.compilation_id,
        context.plan_id,
    ) != (
        bundle.scope,
        bundle.bundle_digest,
        bundle.scope,
        compilation.compilation_id,
        plan.plan_id,
    ):
        raise ReportAuthorityError("section assurance scope or bundle differs")
    artifacts = repository.load_report_artifacts(compilation.compilation_id)
    for artifact in artifacts:
        if (
            isinstance(artifact.document, FallbackRecord)
            and artifact.question_id == context.question_id
        ):
            return artifact.document.section
    completed = _replay_verified_section(compilation, context, bundle, plan, artifacts)
    if completed is not None:
        return completed

    def fallback() -> VerifiedSection:
        section = render_fallback_section(bundle, compilation, question_id=context.question_id)
        record_section_artifact(
            compilation,
            repository,
            ReportArtifactKind.FALLBACK,
            FallbackRecord(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                question_id=context.question_id,
                bundle_digest=bundle.bundle_digest,
                section=section,
            ),
            "p8-fallback-v1",
        )
        return section

    if (
        context.requires_fallback
        or ports.writer is None
        or ports.extractor is None
        or ports.verifier is None
    ):
        return fallback()
    # Interrupted consumed repairs cannot dispatch again.
    if any(
        isinstance(a.document, RepairCluster) and a.question_id == context.question_id
        for a in artifacts
    ):
        return fallback()
    sources: list[str] = []
    repaired_ids: set[str] = set()
    writer, extractor, verifier = ports.writer, ports.extractor, ports.verifier
    try:
        prior_drafts = tuple(
            a
            for a in artifacts
            if isinstance(a.document, SectionDraft) and a.question_id == context.question_id
        )
        if len(prior_drafts) > 1:
            raise ReportAuthorityError("unfinished section has multiple writer drafts")
        if prior_drafts:
            draft = prior_drafts[0].document
            assert isinstance(draft, SectionDraft)
            sources.append(prior_drafts[0].artifact_id)
        else:
            draft, execution = await invoke_report_operation(
                compilation,
                repository,
                writer,
                ReportSemanticRole.WRITER,
                context,
                SectionDraft,
                lambda: writer.write(context),
            )
            sources.append(
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.DRAFT,
                    draft,
                    "p8-write-v1",
                    execution_ref=execution,
                )
            )
        draft = validate_section_draft(draft, context)

        async def check(
            actual: SectionDraft,
        ) -> tuple[
            ClaimExtractionProposal, FirewallResult, ClaimVerificationBatch | None, str | None
        ]:
            extraction_context = build_claim_extraction_context(actual, context)
            committed = repository.load_report_artifacts(compilation.compilation_id)
            prior_extractions = tuple(
                a
                for a in committed
                if isinstance(a.document, ClaimExtractionProposal)
                and a.document.draft_digest == canonical_hash(actual)
            )
            if len(prior_extractions) > 1:
                raise ReportAuthorityError(
                    "section has multiple independent extractions for one draft"
                )
            if prior_extractions:
                extraction = prior_extractions[0].document
                assert isinstance(extraction, ClaimExtractionProposal)
                sources.append(prior_extractions[0].artifact_id)
            else:
                extraction, execution = await invoke_report_operation(
                    compilation,
                    repository,
                    extractor,
                    ReportSemanticRole.EXTRACTOR,
                    extraction_context,
                    ClaimExtractionProposal,
                    lambda: extractor.extract(extraction_context),
                )
                extraction = validate_claim_extraction(actual, extraction)
                sources.append(
                    record_section_artifact(
                        compilation,
                        repository,
                        ReportArtifactKind.EXTRACTION,
                        extraction,
                        "p8-extract-v1",
                        execution_ref=execution,
                    )
                )
            extraction = validate_claim_extraction(actual, extraction)
            firewall = check_report_claims(actual, extraction, bundle, plan)
            sources.append(
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.FIREWALL,
                    firewall,
                    "p8-semantic-firewall-v1",
                )
            )
            if not firewall.accepted:
                return extraction, firewall, None, None
            verification_context = build_claim_verification_context(
                actual, extraction, bundle, plan
            )
            prior_checks: list[ReportArtifact] = []
            for proof in committed:
                if not isinstance(proof.document, ClaimVerificationBatch):
                    continue
                try:
                    validate_verification_batch(verification_context, proof.document, firewall)
                except ValueError:
                    continue
                prior_checks.append(proof)
            if len(prior_checks) > 1:
                raise ReportAuthorityError("section has multiple checks for one public text")
            if prior_checks:
                proof = prior_checks[0]
                batch = proof.document
                assert isinstance(batch, ClaimVerificationBatch)
                sources.append(proof.artifact_id)
                return extraction, firewall, batch, proof.artifact_id
            batch, execution = await invoke_report_operation(
                compilation,
                repository,
                verifier,
                ReportSemanticRole.VERIFIER,
                verification_context,
                ClaimVerificationBatch,
                lambda: verifier.verify(verification_context),
            )
            batch = validate_verification_batch(verification_context, batch, firewall)
            sources.append(
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.VERIFICATION,
                    batch,
                    "p8-verify-v1",
                    execution_ref=execution,
                )
            )
            return extraction, firewall, batch, sources[-1]

        extraction, firewall, batch, verification_ref = await check(draft)
        if batch is not None and batch.accepted and verification_ref is not None:
            return _verified(
                compilation,
                context,
                draft,
                extraction,
                verification_ref,
                tuple(sources),
                repaired_ids,
            )
        original = draft
        clusters = select_repair_clusters(
            original, report_violations(original, extraction, firewall, batch)
        )
        if not clusters:
            return fallback()
        for cluster in clusters:
            artifacts = repository.load_report_artifacts(compilation.compilation_id)
            if (
                not repair_available(cluster, artifacts)
                or sum(isinstance(a.document, RepairCluster) for a in artifacts)
                >= compilation.options.limits.max_repairs_total
            ):
                return fallback()
            owned = tuple(b for b in draft.blocks if b.block_id in cluster.original_block_ids)
            local = LocalRepairContext(
                scope=compilation.scope,
                compilation_id=compilation.compilation_id,
                section_context=context,
                cluster=cluster,
                original_blocks=owned,
                neighboring_blocks=tuple(
                    b for b in draft.blocks if b.block_id not in cluster.original_block_ids
                ),
                relevant_basis_refs=context.selected_basis_refs,
                required_qualification_refs=tuple(
                    dict.fromkeys(
                        r
                        for envelope in context.language_envelopes
                        for r in envelope.authority_refs
                    )
                ),
            )
            # Consumption is durable BEFORE the provider sees the request.
            sources.append(
                record_section_artifact(
                    compilation, repository, ReportArtifactKind.REPAIR, cluster, "p8-repair-v1"
                )
            )
            fragment, execution = await invoke_report_operation(
                compilation,
                repository,
                writer,
                ReportSemanticRole.REPAIR,
                local,
                SectionDraftFragment,
                lambda: writer.repair(local),
            )
            fragment = validate_repair_fragment(fragment, cluster, local)
            sources.append(
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.REPAIR,
                    fragment,
                    "p8-repair-v1",
                    execution_ref=execution,
                )
            )
            draft = apply_repair_fragment(draft, fragment, cluster)
            sources.append(
                record_section_artifact(
                    compilation, repository, ReportArtifactKind.DRAFT, draft, "p8-repair-v1"
                )
            )
            repaired_ids.update(b.block_id for b in fragment.blocks)
        extraction, firewall, batch, verification_ref = await check(draft)
        if batch is not None and batch.accepted and verification_ref is not None:
            return _verified(
                compilation,
                context,
                draft,
                extraction,
                verification_ref,
                tuple(sources),
                repaired_ids,
            )
    except ReportAuthorityError:
        raise
    except (ValueError, RuntimeError):
        return fallback()
    return fallback()


async def assure_report_composition(
    compilation: ReportCompilationRecord,
    sections: tuple[VerifiedSection, ...],
    *,
    bundle: ReportInputBundle,
    ports: ReportPorts,
    repository: ReportRepository,
) -> tuple[VerifiedSection, ...]:
    """One global check, followed only by complete deterministic replacements."""
    from novelty_harness.reporting.fallback import validate_fallback_section
    from novelty_harness.reporting.obligations import check_report_coverage

    if (compilation.scope, compilation.bundle_digest) != (bundle.scope, bundle.bundle_digest):
        raise ReportAuthorityError("composition scope or upstream bundle differs")

    def replace(questions: set[int]) -> tuple[VerifiedSection, ...]:
        result: list[VerifiedSection] = []
        for section in sections:
            if section.draft.question_id in questions:
                section = render_fallback_section(
                    bundle, compilation, question_id=section.draft.question_id
                )
                record_section_artifact(
                    compilation,
                    repository,
                    ReportArtifactKind.FALLBACK,
                    FallbackRecord(
                        scope=compilation.scope,
                        compilation_id=compilation.compilation_id,
                        question_id=section.draft.question_id,
                        bundle_digest=bundle.bundle_digest,
                        section=section,
                    ),
                    "p8-fallback-v1",
                )
            if set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}:
                validate_fallback_section(section, bundle, compilation)
            result.append(section)
        final = tuple(result)
        check_report_coverage(final, bundle)
        return final

    try:
        context = build_composition_context(sections, bundle, compilation)
    except ValueError:
        return replace(set(range(1, 10)))
    if all(set(s.block_origins.values()) == {"DETERMINISTIC_FALLBACK"} for s in sections):
        return replace(set())
    if (
        ports.verifier is None
        or len(canonical_json(context)) > compilation.options.limits.max_context_chars
    ):
        return replace(set(range(1, 10)))
    artifacts = repository.load_report_artifacts(compilation.compilation_id)
    checks = tuple(a.document for a in artifacts if isinstance(a.document, CompositionCheck))
    if len(checks) > 1:
        raise ReportAuthorityError("composition has multiple completed semantic results")
    try:
        if checks:
            check = validate_composition_check(context, checks[0])
        else:
            if any(isinstance(a.document, CompositionContext) for a in artifacts):
                # Committed input consumes dispatch even if the process died mid-call.
                return replace(set(range(1, 10)))
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.COMPOSITION,
                context,
                "p8-compose-check-v1",
            )
            verifier = ports.verifier
            check, execution_ref = await invoke_report_operation(
                compilation,
                repository,
                verifier,
                ReportSemanticRole.COMPOSITION,
                context,
                CompositionCheck,
                lambda: verifier.check_composition(context),
            )
            check = validate_composition_check(context, check)
            record_section_artifact(
                compilation,
                repository,
                ReportArtifactKind.COMPOSITION,
                check,
                "p8-compose-check-v1",
                execution_ref=execution_ref,
            )
        if check.accepted:
            return sections
        affected: set[int] = set(check.implicated_question_ids)
        affected.update(
            d.question_id
            for d in context.drafts
            if any(b.block_id in check.implicated_block_ids for b in d.blocks)
        )
        return replace(set(range(1, 10)) if check.indeterminate_scope or not affected else affected)
    except ReportAuthorityError:
        raise
    except (ValueError, RuntimeError):
        return replace(set(range(1, 10)))

"""Canonical report proposals with exact proof joins; repository acceptance is separate."""

from datetime import date
from typing import Any, Literal, cast

from pydantic import BaseModel, JsonValue, create_model

from novelty_harness.adjudication.frozen import (
    LanguagePermissionClass,
    OverallFinding,
    TargetFinding,
)
from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.enums import VerdictState
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.evidence.graph.assessment_ledger import Phase6CoverageLedger
from novelty_harness.reporting.artifacts import (
    ReportArtifact,
    ReportCompilationRecord,
    report_artifact_semantic_content,
    report_artifact_snapshot_id,
)
from novelty_harness.reporting.bundle import ReportInputBundle
from novelty_harness.reporting.citations import CitationRegistry, validate_citation_registry
from novelty_harness.reporting.claims import ClaimBasisLink, ClaimExtractionProposal, ReportClaim
from novelty_harness.reporting.drafts import DraftBlock, SectionDraft, SectionDraftFragment
from novelty_harness.reporting.execution import (
    ReportCompilationConfiguration,
    ReportExecutionRecord,
    ReportMethodRegistration,
    ReportRoleConfiguration,
    bundle_policy_version,
    validate_method_registration,
)
from novelty_harness.reporting.fallback import FallbackRecord, validate_fallback_section
from novelty_harness.reporting.firewall import FirewallResult, check_report_claims
from novelty_harness.reporting.models import (
    Digest,
    NonBlank,
    QuestionId,
    ReportContract,
    ReportDependency,
    ReportOptions,
    ReportProposalError,
    ReportScoped,
    ReportSemanticRole,
)
from novelty_harness.reporting.obligations import (
    CoverageObligation,
    ObligationSatisfaction,
    check_report_coverage,
)
from novelty_harness.reporting.plan import QuestionPlan, ReportPlan, build_coverage_plan
from novelty_harness.reporting.recommendations import (
    ValidationRequirement,
    minimum_validation_requirements,
)
from novelty_harness.reporting.serialization import canonical_json_digest, share_validated_strings
from novelty_harness.reporting.uncertainty import UncertaintyItem, project_uncertainty
from novelty_harness.reporting.value import ValueProjection
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    CompositionCheck,
    CompositionContext,
    VerifiedSection,
    build_claim_verification_context,
    validate_composition_check,
    validate_verification_batch,
)
from novelty_harness.reporting.wording import ClaimWording, safe_claim_wording
from novelty_harness.runtime.tracing.hashing import canonical_hash

BlockOrigin = Literal["GENERATIVE_ACCEPTED", "GENERATIVE_REPAIRED", "DETERMINISTIC_FALLBACK"]


class AcceptedBlock(ReportScoped):
    contract_kind: Literal["phase8-accepted-block-v1"] = "phase8-accepted-block-v1"
    draft_block: DraftBlock
    claims: tuple[ReportClaim, ...]
    basis_links: tuple[ClaimBasisLink, ...]
    verification_refs: tuple[NonBlank, ...]
    obligation_satisfaction: tuple[ObligationSatisfaction, ...]
    origin: BlockOrigin
    source_artifact_refs: tuple[NonBlank, ...]


class ReportSection(ReportScoped):
    contract_kind: Literal["phase8-report-section-v1"] = "phase8-report-section-v1"
    question_id: QuestionId
    question_label: NonBlank
    question_plan: QuestionPlan
    blocks: tuple[AcceptedBlock, ...]


class ReportGenerationProvenance(ReportScoped):
    contract_kind: Literal["phase8-report-generation-provenance-v1"] = (
        "phase8-report-generation-provenance-v1"
    )
    options: ReportOptions
    configuration: ReportCompilationConfiguration
    approved_versions: tuple[NonBlank, ...]
    method_refs: tuple[NonBlank, ...]
    configuration_refs: tuple[NonBlank, ...]
    execution_refs: tuple[NonBlank, ...]


class SummaryTarget(ReportContract):
    contract_kind: Literal["phase8-summary-target-v1"] = "phase8-summary-target-v1"
    target: TargetRef
    claim_scope: NonBlank
    verdict: VerdictState
    permitted_classes: tuple[LanguagePermissionClass, ...]
    limitations: tuple[str, ...]


class CompactSummary(ReportScoped):
    contract_kind: Literal["phase8-compact-summary-v1"] = "phase8-compact-summary-v1"
    method_version: Literal["p8-summary-v1"] = "p8-summary-v1"
    overall_finding: OverallFinding
    targets: tuple[SummaryTarget, ...]
    principal_conclusions: tuple[ClaimWording, ...]
    value_availability: tuple[ValueProjection, ...]
    uncertainty: tuple[UncertaintyItem, ...]
    limitations: tuple[str, ...]


class ReportIR(ReportScoped):
    contract_kind: Literal["phase8-report-ir-v1"] = "phase8-report-ir-v1"
    report_contract_version: Literal["phase8-report-ir-v1"] = "phase8-report-ir-v1"
    as_of: date
    bundle_digest: Digest
    overall_finding: OverallFinding
    target_findings: tuple[TargetFinding, ...]
    sections: tuple[ReportSection, ...]
    material_claims: tuple[ReportClaim, ...]
    claim_basis_links: tuple[ClaimBasisLink, ...]
    verification_refs: tuple[NonBlank, ...]
    coverage_obligations: tuple[CoverageObligation, ...]
    coverage_satisfaction: tuple[ObligationSatisfaction, ...]
    citation_registry: CitationRegistry
    coverage_summary: Phase6CoverageLedger
    uncertainty_summary: tuple[UncertaintyItem, ...]
    supported_and_qualified_wording: tuple[ClaimWording, ...]
    unsupported_wording_examples: tuple[ClaimWording, ...]
    validation_requirements: tuple[ValidationRequirement, ...]
    value_availability: tuple[ValueProjection, ...]
    compact_summary: CompactSummary | None
    generation_provenance: ReportGenerationProvenance
    report_limitations: tuple[str, ...]
    source_dependency_manifest: tuple[ReportDependency, ...]
    report_artifact_dependencies: tuple[ReportDependency, ...]


# Cache schemas only, never validated report content or authority decisions.
# FieldInfo carries the original metadata once; rebuilding an Annotated type
# as well would apply that metadata a second time in the installed Pydantic.
_IR_FIELD_MODELS: dict[str, type[BaseModel]] = {
    name: create_model(
        "_ReportIRField_" + name,
        __config__=ReportIR.model_config,
        **cast(dict[str, Any], {name: (field.annotation, field)}),
    )
    for name, field in ReportIR.model_fields.items()
}


_CITATION_FIELD_MODELS: dict[str, type[BaseModel]] = {
    name: create_model(
        "_CitationRegistryField_" + name,
        __config__=CitationRegistry.model_config,
        **cast(dict[str, Any], {name: (field.annotation, field)}),
    )
    for name, field in CitationRegistry.model_fields.items()
}


def _snapshot_basis_links(
    links: tuple[ClaimBasisLink, ...],
    basis: dict[str, ClaimBasisLink],
    *,
    strict: bool | None = True,
) -> tuple[ClaimBasisLink, ...]:
    """Validate every item; preserve every ordered occurrence and divergence."""
    snapshots: list[ClaimBasisLink] = []
    for proposed in links:
        link = ClaimBasisLink.model_validate_json(proposed.model_dump_json(), strict=strict)
        candidate = basis.get(canonical_json_digest(link.model_dump(mode="json")))
        snapshots.append(candidate if candidate is not None and candidate == link else link)
    return tuple(snapshots)


def _snapshot_citation_registry(
    registry: CitationRegistry,
    basis: dict[str, ClaimBasisLink],
    *,
    strict: bool | None = True,
) -> CitationRegistry:
    if any(
        name not in registry.__dict__
        for name, field in CitationRegistry.model_fields.items()
        if field.is_required()
    ):
        return CitationRegistry.model_validate_json(registry.model_dump_json(), strict=strict)
    values: dict[str, object] = {}
    for name, schema in _CITATION_FIELD_MODELS.items():
        if (
            name == "claim_basis_links"
            and type(registry.claim_basis_links) is tuple
            and all(type(link) is ClaimBasisLink for link in registry.claim_basis_links)
        ):
            values[name] = _snapshot_basis_links(registry.claim_basis_links, basis, strict=strict)
        else:
            field = schema.model_validate_json(
                registry.model_dump_json(include={name}), strict=strict
            )
            values[name] = getattr(field, name)
    return CitationRegistry.model_validate(values, strict=strict)


def _revalidate_report_ir(ir: ReportIR, *, strict: bool | None = True) -> ReportIR:
    """Strict serialized snapshots without retaining a complete wire copy.

    The closed IR has field schemas and no JSON-specific root transform. Every
    field uses the original serializer, metadata/config and nested validators;
    normal strict model construction then applies the complete root contract.
    The default remains strict for native IR validation; strict=None preserves
    the original field-level coercion policy at the enclosing report boundary.
    Subclasses retain the original full roundtrip so added serialized fields
    cannot disappear through projection.
    """
    if type(ir) is not ReportIR or any(
        name not in ir.__dict__
        for name, field in ReportIR.model_fields.items()
        if field.is_required()
    ):
        return ReportIR.model_validate_json(ir.model_dump_json(), strict=strict)
    values: dict[str, object] = {}
    basis: dict[str, ClaimBasisLink] = {}
    strings: dict[str, str] = {}
    for name, schema in _IR_FIELD_MODELS.items():
        if name == "claim_basis_links" or name == "citation_registry":
            sections = cast(tuple[ReportSection, ...], values["sections"])
            if not basis:
                basis = {
                    canonical_json_digest(link.model_dump(mode="json")): link
                    for section in sections
                    for block in section.blocks
                    for link in block.basis_links
                }
        if (
            name == "sections"
            and type(ir.sections) is tuple
            and all(type(section) is ReportSection for section in ir.sections)
        ):
            value = tuple(
                cast(
                    ReportSection,
                    share_validated_strings(
                        ReportSection.model_validate_json(section.model_dump_json(), strict=strict),
                        section,
                        strings,
                    ),
                )
                for section in ir.sections
            )
        elif (
            name == "claim_basis_links"
            and type(ir.claim_basis_links) is tuple
            and all(type(link) is ClaimBasisLink for link in ir.claim_basis_links)
        ):
            value = _snapshot_basis_links(ir.claim_basis_links, basis, strict=strict)
        elif name == "citation_registry" and type(ir.citation_registry) is CitationRegistry:
            value = _snapshot_citation_registry(ir.citation_registry, basis, strict=strict)
        else:
            field = schema.model_validate_json(ir.model_dump_json(include={name}), strict=strict)
            value = getattr(field, name)
            del field
        if name == "material_claims":
            sections = cast(tuple[ReportSection, ...], values["sections"])
            projected = tuple(
                claim for section in sections for block in section.blocks for claim in block.claims
            )
            # Share only already validated private objects after full equality;
            # never repair an omitted/extra/reordered caller collection.
            if value == projected:
                value = projected
        values[name] = value
    return ReportIR.model_validate(values, strict=strict)


class CompiledAssessmentReport(ReportScoped):
    contract_kind: Literal["phase8-compiled-assessment-report-v1"] = (
        "phase8-compiled-assessment-report-v1"
    )
    report_id: NonBlank
    ir: ReportIR
    dependencies: tuple[ReportDependency, ...]
    approved_versions: tuple[NonBlank, ...]
    configuration_refs: tuple[NonBlank, ...]
    execution_refs: tuple[NonBlank, ...]
    accepted_at: UTCDateTime


# Schemas only; each proposal is independently serialized and revalidated.
_COMPILED_FIELD_MODELS: dict[str, type[BaseModel]] = {
    name: create_model(
        "_CompiledReportField_" + name,
        __config__=CompiledAssessmentReport.model_config,
        **cast(dict[str, Any], {name: (field.annotation, field)}),
    )
    for name, field in CompiledAssessmentReport.model_fields.items()
}


def snapshot_compiled_report(report: CompiledAssessmentReport) -> CompiledAssessmentReport:
    """The original JSON boundary, with only one field/section wire retained.

    Preserve the original default coercion policy, including explicitly strict
    nested fields. Closed models have no JSON-specific root transform. Unknown
    subclasses and missing fields retain the original enclosing roundtrip.
    Native authority validation remains the repository's responsibility.
    """
    if (
        type(report) is not CompiledAssessmentReport
        or any(
            name not in report.__dict__
            for name, field in CompiledAssessmentReport.model_fields.items()
            if field.is_required()
        )
        or type(report.ir) is not ReportIR
    ):
        return CompiledAssessmentReport.model_validate_json(report.model_dump_json())
    values: dict[str, object] = {}
    for name, schema in _COMPILED_FIELD_MODELS.items():
        if name == "ir":
            values[name] = _revalidate_report_ir(report.ir, strict=None)
        else:
            field = schema.model_validate_json(report.model_dump_json(include={name}))
            values[name] = getattr(field, name)
    return CompiledAssessmentReport.model_validate(values)


def report_id(report: CompiledAssessmentReport) -> str:
    """Realized text, dependency and execution hashes stay semantic; observations do not."""
    observation_fields = {
        "accepted_at",
        "observations",
        "observed_at",
        "retrieved_at",
        "discovered_at",
    }

    def semantic(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {
                key: semantic(item) for key, item in value.items() if key not in observation_fields
            }
        if isinstance(value, list):
            return [semantic(item) for item in value]
        return value

    return "p8report_" + canonical_json_digest(
        semantic(report.model_dump(mode="json", exclude={"report_id"}))
    )


def _members(documents: tuple[BaseModel, ...]) -> tuple[str, ...]:
    return tuple(sorted(canonical_hash(d) for d in documents))


def _execution(
    artifact: ReportArtifact,
    role: ReportSemanticRole,
    compilation: ReportCompilationRecord,
    artifacts: tuple[ReportArtifact, ...],
) -> None:
    selected = next((c for c in compilation.configuration.roles if c.role == role), None)
    execution = next(
        (a.document for a in artifacts if a.artifact_id == artifact.execution_ref), None
    )
    if (
        selected is None
        or not isinstance(execution, ReportExecutionRecord)
        or (
            execution.role,
            execution.configuration_id,
            execution.method_version,
            execution.validated_proposal_hash,
            execution.outcome,
        )
        != (
            role,
            selected.configuration_id,
            selected.method_version,
            canonical_hash(artifact.document),
            "VALIDATED",
        )
    ):
        raise ReportProposalError(
            "accepted generative document lacks its matching actual execution"
        )
    registrations = tuple(
        a.document
        for a in artifacts
        if isinstance(a.document, ReportMethodRegistration)
        and a.document.role == role
        and a.document.recovery == execution.recovery
        and a.document.instruction_hash == execution.actual_instruction_hash
    )
    if len(registrations) != 1:
        raise ReportProposalError("actual instruction lacks one approved registration")
    validate_method_registration(registrations[0])
    if not any(
        isinstance(a.document, ReportRoleConfiguration) and a.document == selected
        for a in artifacts
    ):
        raise ReportProposalError("actual invocation configuration is not committed")


def _section_sources(
    section: VerifiedSection,
    bundle: ReportInputBundle,
    compilation: ReportCompilationRecord,
    plan: ReportPlan,
    artifacts: tuple[ReportArtifact, ...],
) -> tuple[str, ...]:
    if set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}:
        validate_fallback_section(section, bundle, compilation)
        matching = tuple(
            a
            for a in artifacts
            if isinstance(a.document, FallbackRecord) and a.document.section == section
        )
        if len(matching) != 1:
            raise ReportProposalError("fallback label lacks its exact committed transformation")
        return (matching[0].artifact_id,)
    if "DETERMINISTIC_FALLBACK" in section.block_origins.values():
        raise ReportProposalError("mixed local fallback has no registered complete transformation")
    sources = set(section.source_artifact_refs)
    if not sources or not sources <= {a.artifact_id for a in artifacts}:
        raise ReportProposalError("generative section source artifacts do not resolve")
    drafts = tuple(
        a for a in artifacts if isinstance(a.document, SectionDraft) and a.document == section.draft
    )
    extractions = tuple(
        a
        for a in artifacts
        if isinstance(a.document, ClaimExtractionProposal)
        and a.document.draft_digest == canonical_hash(section.draft)
        and _members(a.document.claims) == _members(section.claims)
        and _members(a.document.basis_links) == _members(section.basis_links)
    )
    if (
        len(drafts) != 1
        or len(extractions) != 1
        or not {drafts[0].artifact_id, extractions[0].artifact_id} <= sources
    ):
        raise ReportProposalError(
            "generative section lacks exact public draft and independent extraction"
        )
    extraction = extractions[0].document
    assert isinstance(extraction, ClaimExtractionProposal)
    _execution(extractions[0], ReportSemanticRole.EXTRACTOR, compilation, artifacts)
    if drafts[0].method_version == "p8-write-v1":
        _execution(drafts[0], ReportSemanticRole.WRITER, compilation, artifacts)
        if any(o != "GENERATIVE_ACCEPTED" for o in section.block_origins.values()):
            raise ReportProposalError("unrepaired writer draft cannot claim repaired origin")
    else:
        fragments = tuple(
            a
            for a in artifacts
            if isinstance(a.document, SectionDraftFragment) and a.artifact_id in sources
        )
        repaired = {
            b.block_id
            for a in fragments
            if isinstance(a.document, SectionDraftFragment)
            for b in a.document.blocks
        }
        if (
            not fragments
            or {b for b, origin in section.block_origins.items() if origin == "GENERATIVE_REPAIRED"}
            != repaired
        ):
            raise ReportProposalError("repaired origins lack exact consumed fragment ownership")
        for fragment in fragments:
            _execution(fragment, ReportSemanticRole.REPAIR, compilation, artifacts)
    expected_firewall = check_report_claims(section.draft, extraction, bundle, plan)
    firewalls = tuple(
        a
        for a in artifacts
        if isinstance(a.document, FirewallResult) and a.document == expected_firewall
    )
    if (
        not expected_firewall.accepted
        or len(firewalls) != 1
        or firewalls[0].artifact_id not in sources
    ):
        raise ReportProposalError("generative section lacks exact accepted mechanical firewall")
    checks = tuple(
        a
        for a in artifacts
        if a.artifact_id in section.verification_refs
        and isinstance(a.document, ClaimVerificationBatch)
    )
    if (
        len(checks) != 1
        or tuple(a.artifact_id for a in checks) != section.verification_refs
        or checks[0].artifact_id not in sources
    ):
        raise ReportProposalError(
            "generative section lacks exact independent verification references"
        )
    context = build_claim_verification_context(section.draft, extraction, bundle, plan)
    batch = checks[0].document
    assert isinstance(batch, ClaimVerificationBatch)
    validate_verification_batch(context, batch, expected_firewall)
    if not batch.accepted:
        raise ReportProposalError("unresolved or rejected material text cannot enter ReportIR")
    _execution(checks[0], ReportSemanticRole.VERIFIER, compilation, artifacts)
    return tuple(sorted(sources))


def _composition(
    sections: tuple[VerifiedSection, ...],
    bundle: ReportInputBundle,
    compilation: ReportCompilationRecord,
    artifacts: tuple[ReportArtifact, ...],
) -> None:
    if all(set(s.block_origins.values()) == {"DETERMINISTIC_FALLBACK"} for s in sections):
        return
    contexts = tuple(a.document for a in artifacts if isinstance(a.document, CompositionContext))
    checks = tuple(a for a in artifacts if isinstance(a.document, CompositionCheck))
    if len(contexts) != 1 or len(checks) != 1:
        raise ReportProposalError("generative report lacks its single committed composition check")
    context = contexts[0]
    check = checks[0].document
    assert isinstance(check, CompositionCheck)
    validate_composition_check(context, check)
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
        raise ReportProposalError("composition changes frozen scope or permissions")
    _execution(checks[0], ReportSemanticRole.COMPOSITION, compilation, artifacts)
    affected: set[int] = set(check.implicated_question_ids)
    affected.update(
        d.question_id
        for d in context.drafts
        if any(b.block_id in check.implicated_block_ids for b in d.blocks)
    )
    if check.indeterminate_scope:
        affected = set(range(1, 10))
    for section, original, extraction in zip(
        sections, context.drafts, context.extractions, strict=True
    ):
        fallback = set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}
        if section.draft.question_id in affected and not fallback:
            raise ReportProposalError("composition-rejected section was not replaced by fallback")
        if not fallback and (
            section.draft != original
            or _members(section.claims) != _members(extraction.claims)
            or _members(section.basis_links) != _members(extraction.basis_links)
        ):
            raise ReportProposalError("composition never checked the actual final generative text")


def _validated_ir_artifacts(
    artifacts: tuple[ReportArtifact, ...], compilation: ReportCompilationRecord
) -> tuple[ReportArtifact, ...]:
    """Strict private snapshots, with identity checks before retaining each one."""
    validated: list[ReportArtifact] = []
    strings: dict[str, str] = {}
    identities: set[str] = set()
    for proposed in artifacts:
        artifact = ReportArtifact.model_validate_json(proposed.model_dump_json(), strict=True)
        artifact = cast(ReportArtifact, share_validated_strings(artifact, proposed, strings))
        if (
            artifact.artifact_id in identities
            or artifact.artifact_id != report_artifact_snapshot_id(artifact)
            or (artifact.scope, artifact.compilation_id)
            != (compilation.scope, compilation.compilation_id)
        ):
            raise ReportProposalError("IR artifact identity, scope or multiplicity differs")
        identities.add(artifact.artifact_id)
        validated.append(artifact)
    return tuple(validated)


def build_report_ir(
    bundle: ReportInputBundle,
    compilation: ReportCompilationRecord,
    sections: tuple[VerifiedSection, ...],
    citations: CitationRegistry,
    artifacts: tuple[ReportArtifact, ...],
) -> ReportIR:
    if (compilation.scope, compilation.bundle_digest) != (bundle.scope, bundle.bundle_digest):
        raise ReportProposalError("IR compilation does not match its upstream bundle")
    artifacts = _validated_ir_artifacts(artifacts, compilation)
    try:
        policy = bundle_policy_version(compilation.configuration)
    except ValueError as exc:
        raise ReportProposalError("IR policy version is not approved") from exc
    if policy != bundle.bundle_version:
        raise ReportProposalError("IR bundle policy differs from its pinned configuration")
    plans = tuple(a.document for a in artifacts if isinstance(a.document, ReportPlan))
    if len(plans) != 1:
        raise ReportProposalError("IR requires one committed coverage-validated plan")
    plan = plans[0]
    if (plan.scope, plan.compilation_id, plan.bundle_digest) != (
        bundle.scope,
        compilation.compilation_id,
        bundle.bundle_digest,
    ):
        raise ReportProposalError("IR plan scope differs")
    if plan.origin == "COVERAGE_FALLBACK" and plan != build_coverage_plan(bundle, compilation):
        raise ReportProposalError("IR fallback plan does not recompute")
    satisfaction = check_report_coverage(sections, bundle)
    validate_citation_registry(citations, sections, bundle)
    accepted: list[ReportSection] = []
    for section in sections:
        sources = _section_sources(section, bundle, compilation, plan, artifacts)
        blocks: list[AcceptedBlock] = []
        for block in section.draft.blocks:
            claims = tuple(c for c in section.claims if c.block_id == block.block_id)
            claim_ids = {c.claim_id for c in claims}
            blocks.append(
                AcceptedBlock(
                    scope=bundle.scope,
                    compilation_id=compilation.compilation_id,
                    draft_block=block,
                    claims=claims,
                    basis_links=tuple(
                        link for link in section.basis_links if link.claim_id in claim_ids
                    ),
                    verification_refs=section.verification_refs,
                    obligation_satisfaction=tuple(
                        h for h in section.obligation_satisfaction if block.block_id in h.block_ids
                    ),
                    origin=section.block_origins[block.block_id],
                    source_artifact_refs=sources,
                )
            )
        accepted.append(
            ReportSection(
                scope=bundle.scope,
                compilation_id=compilation.compilation_id,
                question_id=section.draft.question_id,
                question_label=CANONICAL_QUESTIONS[section.draft.question_id - 1],
                question_plan=plan.questions[section.draft.question_id - 1],
                blocks=tuple(blocks),
            )
        )
    _composition(sections, bundle, compilation, artifacts)
    ordered = tuple(sorted(artifacts, key=lambda a: a.artifact_id))
    provenance = ReportGenerationProvenance(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        options=compilation.options,
        configuration=compilation.configuration,
        approved_versions=tuple(
            dict.fromkeys(
                (
                    *compilation.configuration.deterministic_versions,
                    *(a.method_version for a in ordered),
                )
            )
        ),
        method_refs=tuple(
            a.artifact_id for a in ordered if isinstance(a.document, ReportMethodRegistration)
        ),
        configuration_refs=tuple(
            a.artifact_id for a in ordered if isinstance(a.document, ReportRoleConfiguration)
        ),
        execution_refs=tuple(
            a.artifact_id for a in ordered if isinstance(a.document, ReportExecutionRecord)
        ),
    )
    wording = safe_claim_wording(bundle)
    uncertainty = project_uncertainty(bundle)
    ir = ReportIR(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        as_of=bundle.as_of,
        bundle_digest=bundle.bundle_digest,
        overall_finding=bundle.overall_finding,
        target_findings=bundle.target_findings,
        sections=tuple(accepted),
        material_claims=tuple(
            c for section in accepted for block in section.blocks for c in block.claims
        ),
        claim_basis_links=tuple(
            link for section in accepted for block in section.blocks for link in block.basis_links
        ),
        verification_refs=tuple(sorted({ref for s in sections for ref in s.verification_refs})),
        coverage_obligations=bundle.coverage_obligations,
        coverage_satisfaction=satisfaction,
        citation_registry=citations,
        coverage_summary=bundle.judge_resolutions_and_limitations.phase6_view.coverage,
        uncertainty_summary=uncertainty,
        supported_and_qualified_wording=tuple(w for w in wording if w.use != "UNSUPPORTED_EXAMPLE"),
        unsupported_wording_examples=tuple(w for w in wording if w.use == "UNSUPPORTED_EXAMPLE"),
        validation_requirements=minimum_validation_requirements(bundle),
        value_availability=bundle.value_projection,
        compact_summary=None,
        generation_provenance=provenance,
        report_limitations=tuple(
            dict.fromkeys(
                (
                    *bundle.overall_finding.limiting_factors,
                    *(
                        limit
                        for envelope in bundle.language_envelopes
                        for limit in envelope.required_limitations
                    ),
                )
            )
        ),
        source_dependency_manifest=bundle.dependency_manifest,
        report_artifact_dependencies=tuple(
            ReportDependency(
                dependency_kind="REPORT_ARTIFACT",
                dependency_id=a.artifact_id,
                expected_digest=canonical_json_digest(report_artifact_semantic_content(a)),
                report_artifact_id=a.artifact_id,
            )
            for a in ordered
        ),
    )
    return (
        ir.model_copy(update={"compact_summary": derive_compact_summary(ir)})
        if compilation.options.compact_summary
        else ir
    )


def derive_compact_summary(ir: ReportIR) -> CompactSummary:
    return CompactSummary(
        scope=ir.scope,
        compilation_id=ir.compilation_id,
        overall_finding=ir.overall_finding,
        targets=tuple(
            SummaryTarget(
                target=TargetRef(kind=f.target_kind, id=f.target_id),
                claim_scope=f.claim_scope,
                verdict=f.verdict,
                permitted_classes=f.language_permission,
                limitations=tuple(
                    dict.fromkeys(
                        (
                            *f.limiting_factors,
                            *(
                                limit
                                for w in ir.supported_and_qualified_wording
                                if w.target.id == f.target_id
                                for limit in w.necessary_limitations
                            ),
                        )
                    )
                ),
            )
            for f in ir.target_findings
        ),
        principal_conclusions=ir.supported_and_qualified_wording,
        value_availability=ir.value_availability,
        uncertainty=ir.uncertainty_summary,
        limitations=ir.report_limitations,
    )


def validate_report_ir(
    ir: ReportIR,
    bundle: ReportInputBundle,
    compilation: ReportCompilationRecord,
    artifacts: tuple[ReportArtifact, ...],
) -> None:
    try:
        ir = _revalidate_report_ir(ir)
    except ValueError as error:
        raise ReportProposalError("IR fails strict serialized validation") from error
    sections: list[VerifiedSection] = []
    for section in ir.sections:
        blocks = section.blocks
        indexed_homes: dict[tuple[str, int], ObligationSatisfaction] = {}
        for block in blocks:
            for home in block.obligation_satisfaction:
                key = (home.obligation_id, home.question_id)
                if key in indexed_homes and indexed_homes[key] != home:
                    raise ReportProposalError("IR block repeats a conflicting obligation home")
                indexed_homes[key] = home
        homes = tuple(indexed_homes[key] for key in sorted(indexed_homes))
        fallback = all(b.origin == "DETERMINISTIC_FALLBACK" for b in blocks)
        sections.append(
            VerifiedSection(
                scope=section.scope,
                compilation_id=section.compilation_id,
                draft=SectionDraft(
                    scope=section.scope,
                    compilation_id=section.compilation_id,
                    question_id=section.question_id,
                    blocks=tuple(b.draft_block for b in blocks),
                ),
                claims=tuple(c for b in blocks for c in b.claims),
                basis_links=tuple(link for b in blocks for link in b.basis_links),
                verification_refs=tuple(
                    dict.fromkeys(ref for b in blocks for ref in b.verification_refs)
                ),
                obligation_satisfaction=homes,
                block_origins={b.draft_block.block_id: b.origin for b in blocks},
                source_artifact_refs=()
                if fallback
                else tuple(sorted({ref for b in blocks for ref in b.source_artifact_refs})),
            )
        )
    expected = build_report_ir(
        bundle, compilation, tuple(sections), ir.citation_registry, artifacts
    )
    if ir != expected:
        raise ReportProposalError(
            "IR differs from exact frozen projections, actual proofs or deterministic summary"
        )


# Preserve the prepared internal entrypoint; snapshots never confer authority.
_revalidate_compiled_report = snapshot_compiled_report

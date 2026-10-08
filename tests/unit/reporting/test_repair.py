"""Original failure ownership survives replacement segmentation and crash replay."""

import pytest

from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


class SimulatedCrash(BaseException):
    pass


class ScriptedSections:
    def __init__(self, *, repair_mode="split", repair_supported=False):
        self.repair_mode = repair_mode
        self.repair_supported = repair_supported
        self.calls = []
        self.repair_contexts = []

    @property
    def configuration(self):
        from novelty_harness.reporting.execution import ReportPortConfiguration

        return ReportPortConfiguration(
            mode="PORT_PROTOCOL",
            implementation=type(self).__module__ + "." + type(self).__qualname__,
        )

    async def write(self, context):
        from novelty_harness.reporting.drafts import DraftBlock, SectionDraft

        self.calls.append(("write", context))
        basis = next(r for r in context.selected_basis_refs if r.kind == "PASSAGE")
        return SectionDraft(
            scope=context.scope,
            compilation_id=context.compilation_id,
            question_id=context.question_id,
            blocks=(
                DraftBlock(
                    block_id="bad",
                    kind="PARAGRAPH",
                    text="The source establishes the revised mechanism.",
                    basis_candidate_refs=(basis,),
                    obligation_ids=context.question_plan.obligation_ids,
                ),
                DraftBlock(
                    block_id="neighbor",
                    kind="PARAGRAPH",
                    text="The source has an admitted passage.",
                    basis_candidate_refs=(basis,),
                ),
            ),
        )

    async def repair(self, context):
        from novelty_harness.reporting.drafts import SectionDraftFragment

        self.calls.append(("repair", context))
        self.repair_contexts.append(context)
        if self.repair_mode == "crash":
            raise SimulatedCrash()
        if self.repair_mode == "transport":
            raise RuntimeError("recorded transport failure")
        if self.repair_mode == "malformed":
            return {"complete": True}
        block = context.original_blocks[0]
        texts = (
            "The source establishes the revised mechanism.",
            "Its configuration is independently established.",
        )
        if self.repair_supported:
            texts = ("The source has an admitted passage.",)
        return SectionDraftFragment(
            scope=context.scope,
            compilation_id=context.compilation_id,
            question_id=context.cluster.question_id,
            cluster_origin_id=context.cluster.origin_id,
            replaced_block_ids=context.cluster.original_block_ids,
            blocks=tuple(
                block.model_copy(update={"block_id": f"replacement-{i}", "text": text})
                for i, text in enumerate(texts)
            ),
        )

    async def extract(self, context):
        from novelty_harness.reporting.claims import (
            BlockClaimAccount,
            ClaimBasisLink,
            ClaimExtractionProposal,
            ClaimTarget,
            ReportClaim,
            TextSpan,
        )
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        self.calls.append(("extract", context))
        claims, links, accounts = [], [], []
        for i, block in enumerate(context.draft.blocks):
            basis = block.basis_candidate_refs[0]
            envelope = next(e for e in context.language_envelopes if e.target == basis.target)
            label = str(i)
            claim = ReportClaim(
                scope=context.scope,
                compilation_id=context.compilation_id,
                claim_id=label,
                block_id=block.block_id,
                block_text_digest=canonical_hash(block.text),
                spans=(TextSpan(start=0, end=len(block.text)),),
                normalized_assertion=block.text,
                category="SOURCE_FACT",
                use="ASSERTION",
                target_scopes=(
                    ClaimTarget(target=envelope.target, claim_scope=envelope.claim_scope),
                ),
                basis_candidates=(basis,),
                citation_candidates=(basis,),
            )
            claims.append(claim)
            links.append(
                ClaimBasisLink(
                    scope=context.scope,
                    compilation_id=context.compilation_id,
                    claim_id=label,
                    authority_ref=basis,
                    proposition=block.text,
                    use="ASSERTION",
                )
            )
            accounts.append(
                BlockClaimAccount(
                    block_id=block.block_id,
                    block_text_digest=canonical_hash(block.text),
                    claim_ids=(label,),
                )
            )
        return ClaimExtractionProposal(
            scope=context.scope,
            compilation_id=context.compilation_id,
            question_id=context.question_id,
            draft_digest=canonical_hash(context.draft),
            claims=tuple(claims),
            basis_links=tuple(links),
            block_accounts=tuple(accounts),
        )

    async def verify(self, context):
        from novelty_harness.reporting.verification import VerificationDisposition
        from tests.unit.reporting.test_verification import scripted_batch

        self.calls.append(("verify", context))
        batch = scripted_batch(context)
        by_id = {b.block_id: b for b in context.draft.blocks}
        rejected = {bid for bid, b in by_id.items() if "establish" in b.text}
        return batch.model_copy(
            update={
                "dispositions": tuple(
                    d.model_copy(
                        update={
                            "disposition": VerificationDisposition.REJECTED,
                            "reason_codes": ("UNSUPPORTED_PROPOSITION",),
                        }
                    )
                    if next(
                        c.block_id for c in context.extraction.claims if c.claim_id == d.claim_id
                    )
                    in rejected
                    else d
                    for d in batch.dispositions
                ),
                "blocks": tuple(
                    b.model_copy(
                        update={
                            "disposition": VerificationDisposition.REJECTED,
                            "reason_codes": ("UNSUPPORTED_PROPOSITION",),
                        }
                    )
                    if b.block_id in rejected
                    else b
                    for b in batch.blocks
                ),
            }
        )


def setup_case(case, port, token):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.drafts import build_section_context
    from novelty_harness.reporting.execution import (
        ReportCompilationConfiguration,
        approved_role_configuration,
    )
    from novelty_harness.reporting.models import (
        ReportGenerationLimits,
        ReportOptions,
        ReportSemanticRole,
    )
    from novelty_harness.reporting.plan import build_coverage_plan

    config = ReportCompilationConfiguration(
        roles=tuple(
            approved_role_configuration(case.bundle.scope, "pending", role, port.configuration)
            for role in (
                ReportSemanticRole.WRITER,
                ReportSemanticRole.REPAIR,
                ReportSemanticRole.EXTRACTOR,
                ReportSemanticRole.VERIFIER,
            )
        )
    )
    c = case.repository.begin_report_compilation(
        case.bundle.scope.assessment_id,
        adjudication_id=case.frozen.adjudication_id,
        options=ReportOptions(
            limits=ReportGenerationLimits(
                max_context_chars=10000000,
                max_question_chars=2000000,
                max_blocks_per_question=1000,
                max_tokens=10000000000,
            )
        ),
        configuration=config,
        attempt_token=token,
    )
    plan = build_coverage_plan(case.bundle, c)
    artifact = make_report_artifact(
        c, ReportArtifactKind.PLAN, plan, method_version="p8-plan-firewall-v1"
    )
    case.repository.record_report_artifact(c.compilation_id, artifact)
    context = build_section_context(case.bundle, plan, question_id=2, compilation=c)
    assert not context.requires_fallback
    return c, plan, context


async def run_case(case, port, token, *, missing=None):
    from novelty_harness.application.phase8_sections import assure_report_section
    from novelty_harness.ports.reporting import ReportPorts

    c, plan, context = setup_case(case, port, token)
    ports = ReportPorts(
        writer=port,
        extractor=None if missing == "extractor" else port,
        verifier=None if missing == "verifier" else port,
    )
    section = await assure_report_section(
        c, context, bundle=case.bundle, plan=plan, ports=ports, repository=case.repository
    )
    return section, c, plan, context, ports


async def test_resegmentation_cannot_reset_one_repair_origin(report_case):
    from novelty_harness.reporting.fallback import validate_fallback_section
    from novelty_harness.reporting.repair import repair_available

    port = ScriptedSections()
    section, c, _, _, _ = await run_case(report_case, port, "repair-origin")
    assert sum(name == "repair" for name, _ in port.calls) == 1
    assert sum(name == "extract" for name, _ in port.calls) == 2
    assert sum(name == "verify" for name, _ in port.calls) == 2
    artifacts = report_case.repository.load_report_artifacts(c.compilation_id)
    cluster = port.repair_contexts[0].cluster
    fragments = [
        a.document
        for a in artifacts
        if a.document.contract_kind == "phase8-section-draft-fragment-v1"
    ]
    assert fragments[0].cluster_origin_id == cluster.origin_id
    assert not repair_available(cluster, artifacts)
    assert set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}
    validate_fallback_section(section, report_case.bundle, c)
    repair_input = port.repair_contexts[0]
    assert tuple(b.block_id for b in repair_input.neighboring_blocks) == ("neighbor",)


async def test_overlapping_rejections_merge_before_repair(report_case):
    from novelty_harness.reporting.claims import TextSpan
    from novelty_harness.reporting.repair import ReportViolation, select_repair_clusters

    port = ScriptedSections()
    c, _, context = setup_case(report_case, port, "repair-overlap")
    draft = await port.write(context)
    violations = tuple(
        ReportViolation(
            scope=c.scope,
            compilation_id=c.compilation_id,
            question_id=2,
            block_id="bad",
            spans=(TextSpan(start=start, end=end),),
            reason_codes=("UNSUPPORTED_PROPOSITION",),
        )
        for start, end in ((0, 20), (15, 40))
    )
    clusters = select_repair_clusters(draft, violations)
    assert len(clusters) == 1
    assert clusters[0].original_block_ids == ("bad",)
    assert clusters[0].original_spans[0].start == 0
    assert clusters[0].original_spans[0].end == 40


@pytest.mark.parametrize("attack", ["neighbor", "obligations", "origin", "basis"])
async def test_repair_cannot_edit_neighbors_or_drop_limits(report_case, attack):
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.reporting.repair import (
        LocalRepairContext,
        ReportViolation,
        select_repair_clusters,
        validate_repair_fragment,
    )

    port = ScriptedSections()
    c, _, context = setup_case(report_case, port, "repair-owned-" + attack)
    draft = await port.write(context)
    cluster = select_repair_clusters(
        draft,
        (
            ReportViolation(
                scope=c.scope,
                compilation_id=c.compilation_id,
                question_id=2,
                block_id="bad",
                obligation_ids=draft.blocks[0].obligation_ids,
                reason_codes=("UNSUPPORTED_PROPOSITION",),
            ),
        ),
    )[0]
    local = LocalRepairContext(
        scope=c.scope,
        compilation_id=c.compilation_id,
        section_context=context,
        cluster=cluster,
        original_blocks=(draft.blocks[0],),
        neighboring_blocks=(draft.blocks[1],),
        relevant_basis_refs=context.selected_basis_refs,
        required_qualification_refs=(),
    )
    fragment = await port.repair(local)
    assert validate_repair_fragment(fragment, cluster, local) == fragment
    changes = (
        {"replaced_block_ids": ("neighbor",)}
        if attack == "neighbor"
        else {"cluster_origin_id": "foreign"}
    )
    if attack in {"obligations", "basis"}:
        block_changes = (
            {"obligation_ids": ()}
            if attack == "obligations"
            else {
                "basis_candidate_refs": (
                    fragment.blocks[0]
                    .basis_candidate_refs[0]
                    .model_copy(update={"native_id": "foreign"}),
                )
            }
        )
        changes = {"blocks": tuple(b.model_copy(update=block_changes) for b in fragment.blocks)}
    with pytest.raises(ReportProposalError):
        validate_repair_fragment(fragment.model_copy(update=changes), cluster, local)


async def test_repair_reextracts_and_reverifies_actual_replacement(report_case):
    port = ScriptedSections(repair_supported=True)
    section, _, _, _, _ = await run_case(report_case, port, "repair-fresh")
    verify_contexts = [context for name, context in port.calls if name == "verify"]
    assert len(verify_contexts) == 2
    assert verify_contexts[0].draft != verify_contexts[1].draft
    assert "establish" not in verify_contexts[1].draft.blocks[0].text
    assert verify_contexts[0].draft.blocks[1] == verify_contexts[1].draft.blocks[-1]
    assert "GENERATIVE_REPAIRED" in section.block_origins.values()


@pytest.mark.parametrize("missing", ["extractor", "verifier"])
async def test_missing_extractor_or_verifier_never_accepts_generative_text(report_case, missing):
    section, _, _, _, _ = await run_case(
        report_case, ScriptedSections(), "missing-" + missing, missing=missing
    )
    assert set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}


@pytest.mark.parametrize("mode", ["transport", "malformed"])
async def test_transport_retry_cannot_double_semantic_repair(
    report_case, mode, *, attempt_prefix="repair-failure-"
):
    port = ScriptedSections(repair_mode=mode)
    section, c, _, _, _ = await run_case(report_case, port, attempt_prefix + mode)
    assert sum(name == "repair" for name, _ in port.calls) == 1
    assert set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}
    actual = [
        a.document
        for a in report_case.repository.load_report_artifacts(c.compilation_id)
        if a.kind == "EXECUTION" and a.document.role == "REPAIR"
    ]
    assert len(actual) == 1
    assert actual[0].outcome == ("INVALID" if mode == "malformed" else "PROVIDER_FAILURE")
    assert not actual[0].recovery
    if mode == "malformed":
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        assert actual[0].raw_response_hash == canonical_hash({"complete": True})


async def test_malformed_repair_goes_directly_to_fallback(report_case):
    await test_transport_retry_cannot_double_semantic_repair(
        report_case, "malformed", attempt_prefix="repair-malformed-direct-"
    )


async def test_repair_attempt_committed_before_crash_resumes_to_fallback(report_case):
    from novelty_harness.application.phase8_sections import assure_report_section
    from novelty_harness.ports.reporting import ReportPorts
    from novelty_harness.reporting.repair import RepairCluster

    port = ScriptedSections(repair_mode="crash")
    c, plan, context = setup_case(report_case, port, "repair-crash")
    ports = ReportPorts(writer=port, extractor=port, verifier=port)
    with pytest.raises(SimulatedCrash):
        await assure_report_section(
            c,
            context,
            bundle=report_case.bundle,
            plan=plan,
            ports=ports,
            repository=report_case.repository,
        )
    assert any(
        isinstance(a.document, RepairCluster)
        for a in report_case.repository.load_report_artifacts(c.compilation_id)
    )
    calls = len(port.calls)
    section = await assure_report_section(
        c,
        context,
        bundle=report_case.bundle,
        plan=plan,
        ports=ports,
        repository=report_case.repository,
    )
    assert len(port.calls) == calls
    assert set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}


async def test_independent_verifier_rejects_writer_self_certification(report_case):
    port = ScriptedSections()
    section, _, _, _, _ = await run_case(report_case, port, "writer-certification")
    assert any(name == "verify" for name, _ in port.calls)
    assert set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}


async def test_persisted_replacement_cannot_seed_a_new_repair_origin(report_case):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.claims import ClaimExtractionProposal
    from novelty_harness.reporting.drafts import SectionDraft
    from novelty_harness.reporting.firewall import FirewallResult
    from novelty_harness.reporting.repair import report_violations, select_repair_clusters
    from novelty_harness.reporting.repository import ReportAuthorityError
    from novelty_harness.reporting.verification import ClaimVerificationBatch
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    _, c, _, _, _ = await run_case(report_case, ScriptedSections(), "repair-origin")
    artifacts = report_case.repository.load_report_artifacts(c.compilation_id)
    draft = next(
        a.document
        for a in artifacts
        if isinstance(a.document, SectionDraft) and a.method_version == "p8-repair-v1"
    )
    extraction = next(
        a.document
        for a in artifacts
        if isinstance(a.document, ClaimExtractionProposal)
        and a.document.draft_digest == canonical_hash(draft)
    )
    firewall = next(
        a.document
        for a in artifacts
        if isinstance(a.document, FirewallResult)
        and a.document.draft_digest == canonical_hash(draft)
    )
    batch = next(
        a.document
        for a in artifacts
        if isinstance(a.document, ClaimVerificationBatch)
        and a.document.draft_digest == canonical_hash(draft)
    )
    clusters = select_repair_clusters(draft, report_violations(draft, extraction, firewall, batch))
    assert clusters
    with pytest.raises(ReportAuthorityError, match="original public draft"):
        report_case.repository.record_report_artifact(
            c.compilation_id,
            make_report_artifact(
                c, ReportArtifactKind.REPAIR, clusters[0], method_version="p8-repair-v1"
            ),
        )

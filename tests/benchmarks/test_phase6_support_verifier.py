"""Deterministic support-verifier benchmark (diagnostic baseline, not calibration).

Inspired by claim/evidence benchmarks (FEVER/SciFact structure): each case pairs
material commitments with exact passages and an expected support state. The
judgment is produced by a documented lexical baseline judge running through the
real deterministic verification pipeline.

This is a deterministic fixture benchmark. Its reported metrics describe
support-state agreement of this lexical baseline plus the deterministic gates;
the `citation_presence_and_bundle_integrity` metric only checks that reported
citations/references belong to the supplied bundle. It does **not** establish
model rationale faithfulness, entailment quality or semantic calibration.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.mapping.models import (
    ComparisonDimension,
    EvidenceProposition,
    PropositionCommitment,
)
from novelty_harness.evidence.passages.models import (
    PassageLocator,
    PassageLocatorKind,
    PassageRecord,
)
from novelty_harness.evidence.verification.prompts import VERIFIER_PROMPT_VERSION
from novelty_harness.evidence.verification.verifier import (
    VERIFIER_TASK,
    IndependentSupportVerifier,
    verify_with_context_retry,
)
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase5 import make_passage, phase5_provenance
from tests.fixtures.phase6 import StubLLMProvider, context_payload

NOW = phase5_provenance("phase6-benchmark")
VERSION = "srcv_bench_v1"
BASELINE_PATH = Path(__file__).parents[1] / "fixtures/phase6_support_benchmark.json"
ORIGIN = phase5_provenance("support-benchmark")

_NEGATION = re.compile(r"\b(not|no|never|fails?|ineffective|unable|without)\b")
_QUALIFIER_TERMS = frozenset(
    {
        "above",
        "adults",
        "all",
        "cache",
        "children",
        "condition",
        "degrees",
        "eighty",
        "environment",
        "group",
        "mice",
        "offline",
        "period",
        "rats",
        "temperature",
        "threshold",
        "trial",
        "workload",
        "workloads",
    }
)
_CONDITION = re.compile(r"\b(if|when|provided|assuming|requires?|only (?:for|in|when|if))\b")
_POPULATION = re.compile(r"\b(mice|rats|animals|adults|children)\b")


@dataclass(frozen=True, slots=True)
class SupportCase:
    case_id: str
    commitment_id: str
    commitment_text: str
    dimension: ComparisonDimension
    passages: tuple[str, ...]
    expected_state: str
    expanded_passages: tuple[str, ...] = ()
    relationship: tuple[str, str, str] | None = None


CASES: tuple[SupportCase, ...] = (
    SupportCase(
        case_id="support",
        commitment_id="c1",
        commitment_text="the controller reduces operator checks",
        dimension=ComparisonDimension.INTENDED_OUTCOME,
        passages=("The controller reduces operator checks in the field trial.",),
        expected_state="SUPPORTED",
    ),
    SupportCase(
        case_id="contradiction",
        commitment_id="c1",
        commitment_text="the controller reduces operator checks",
        dimension=ComparisonDimension.INTENDED_OUTCOME,
        passages=("The controller does not reduce operator checks in the field trial.",),
        expected_state="CONTRADICTED",
    ),
    SupportCase(
        case_id="insufficient-evidence",
        commitment_id="c1",
        commitment_text="the controller raises an alert above eighty degrees",
        dimension=ComparisonDimension.MECHANISM,
        passages=("The controller raises an alert in the field trial.",),
        expected_state="INSUFFICIENT_CONTEXT",
    ),
    SupportCase(
        case_id="special-case-only",
        commitment_id="c1",
        commitment_text="the method works for all workloads",
        dimension=ComparisonDimension.CONSTRAINTS,
        passages=("The method works only for read-only workloads.",),
        expected_state="PARTIALLY_SUPPORTED",
    ),
    SupportCase(
        case_id="negative-qualifier",
        commitment_id="c1",
        commitment_text="the treatment was effective in adults",
        dimension=ComparisonDimension.INTENDED_OUTCOME,
        passages=("The treatment was effective.",),
        expanded_passages=("However, it was not effective in adults.",),
        expected_state="CONTRADICTED",
    ),
    SupportCase(
        case_id="conditional-claim",
        commitment_id="c1",
        commitment_text="the system works offline",
        dimension=ComparisonDimension.CONSTRAINTS,
        passages=("If the cache is warm, the system works offline.",),
        expected_state="INSUFFICIENT_CONTEXT",
    ),
    SupportCase(
        case_id="context-population-mismatch",
        commitment_id="c1",
        commitment_text="the drug reduces mortality in adults",
        dimension=ComparisonDimension.CONTEXT,
        passages=("The drug reduced mortality in mice.",),
        expected_state="NOT_SUPPORTED",
    ),
    SupportCase(
        case_id="dispersed-relationship",
        commitment_id="c1",
        commitment_text="sensor controls relay",
        dimension=ComparisonDimension.RELATIONSHIPS,
        relationship=("sensor", "controls", "relay"),
        passages=("The sensor is mounted on the panel. The relay is a standard part.",),
        expected_state="NOT_SUPPORTED",
    ),
)


def _significant(text: str) -> list[str]:
    stop = {"the", "a", "an", "and", "or", "for", "with", "that", "this", "was", "were"}
    return [token for token in re.findall(r"[a-z0-9]+", text.casefold()) if token not in stop]


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _missing_terms(terms: Sequence[str], text: str) -> list[str]:
    available = {_stem(token) for token in re.findall(r"[a-z0-9]+", text.casefold())}

    def present(term: str) -> bool:
        stem = _stem(term)
        for other in available:
            if stem == other:
                return True
            if min(len(stem), len(other)) >= 4 and (
                stem.startswith(other) or other.startswith(stem)
            ):
                return True
        return False

    return sorted({_stem(term) for term in terms if not present(term)})


class BaselineJudgment(NamedTuple):
    state: str
    rationale: str
    supported_subset: str | None = None
    unsupported_remainder: str | None = None


def baseline_judge(
    commitment_text: str,
    passages: Sequence[str],
    relationship: tuple[str, str, str] | None = None,
) -> BaselineJudgment:
    """Documented lexical baseline judgment; no model or network is involved."""

    combined = " ".join(passages).casefold()
    terms = _significant(commitment_text)
    missing_terms = _missing_terms(terms, combined)
    if relationship is not None:
        subject, relation, obj = (part.casefold() for part in relationship)
        if not all(part in combined for part in (subject, relation, obj)):
            return BaselineJudgment(
                "NOT_SUPPORTED", "relationship subject/relation/object is not stated"
            )
        if re.search(
            rf"\b{re.escape(subject)}\b[^.]*?\b{re.escape(relation)}\b[^.]*?"
            rf"\b{re.escape(obj)}\b",
            combined,
        ):
            return BaselineJudgment("SUPPORTED", "directed relationship stated")
        return BaselineJudgment("NOT_SUPPORTED", "relationship direction is not stated")
    if missing_terms:
        population_terms = _POPULATION.findall(commitment_text.casefold())
        passage_population = _POPULATION.findall(combined)
        if (
            population_terms
            and passage_population
            and not set(population_terms) & set(passage_population)
        ):
            return BaselineJudgment("NOT_SUPPORTED", "population/context mismatch")
        # A known narrower scope is scoped partial support, not missing context:
        # preserve the supported subset and the unsupported universal remainder.
        scope = re.search(r"\bonly (?:for|in|with|when|if)\s+([^.;]+)", combined)
        if scope is not None:
            return BaselineJudgment(
                "PARTIALLY_SUPPORTED",
                "passage supports a narrower scope than the commitment",
                supported_subset=f"only {scope.group(1).strip()}",
                unsupported_remainder="unrestricted claim; missing " + ", ".join(missing_terms),
            )
        if _CONDITION.search(combined):
            return BaselineJudgment(
                "INSUFFICIENT", "claim condition is not satisfied by the passages"
            )
        if {_stem(term) for term in missing_terms} & {_stem(term) for term in _QUALIFIER_TERMS}:
            return BaselineJudgment(
                "INSUFFICIENT", "claim qualifier is not satisfied by the passages"
            )
        return BaselineJudgment("NOT_SUPPORTED", f"missing claim terms: {missing_terms}")
    if _NEGATION.search(combined):
        return BaselineJudgment("CONTRADICTED", "passage negates the claimed commitment")
    if _CONDITION.search(combined):
        return BaselineJudgment("INSUFFICIENT", "claim condition is not satisfied by the passages")
    return BaselineJudgment("SUPPORTED", "passage states the claimed commitment")


def _response_for(context) -> Mapping[str, object]:
    payload = json.loads(str(context_payload(context, "verification_input")))
    texts = [item["text"] for item in payload["passages"]]
    commitments = payload["commitments"]
    judgments = []
    for commitment in commitments:
        relationship = (
            (
                commitment["relationship"]["subject"],
                commitment["relationship"]["relation"],
                commitment["relationship"]["object"],
            )
            if commitment.get("relationship")
            else None
        )
        judgment = baseline_judge(commitment["text"], texts, relationship=relationship)
        entry: dict[str, object] = {
            "commitment_id": commitment["commitment_id"],
            "state": judgment.state,
            "rationale": judgment.rationale,
            "passage_ids": [payload["passages"][0]["passage_id"]],
        }
        if judgment.state == "PARTIALLY_SUPPORTED":
            entry["supported_subset"] = judgment.supported_subset
            entry["unsupported_remainder"] = judgment.unsupported_remainder
        judgments.append(entry)
    return {
        "prompt_version": VERIFIER_PROMPT_VERSION,
        "judgments": judgments,
        "context_needed": ["additional same-source context"],
    }


def _verifier() -> IndependentSupportVerifier:
    return IndependentSupportVerifier(
        SemanticRunner(StubLLMProvider({VERIFIER_TASK: _response_for}))
    )


async def run_case(case: SupportCase) -> dict[str, object]:
    selected_text = " ".join(case.passages)
    passage = make_passage(
        "src_bench",
        text=selected_text,
        passage_id="pass_bench",
        source_version_id=VERSION,
        locator=(
            PassageLocator(
                kind=PassageLocatorKind.RESOLVED_CONTENT,
                char_start=0,
                char_end=len(selected_text),
            )
            if not case.expanded_passages
            else PassageLocator(kind=PassageLocatorKind.BLOCK)
        ),
    )
    available: list[PassageRecord] = [passage]
    if case.expanded_passages:
        available.append(
            make_passage(
                "src_bench",
                text=" ".join(case.passages + case.expanded_passages),
                passage_id="pass_document",
                source_version_id=VERSION,
            )
        )
    commitment = PropositionCommitment(
        commitment_id=case.commitment_id,
        dimension=case.dimension,
        text=case.commitment_text,
        relationship=(
            {
                "subject": case.relationship[0],
                "relation": case.relationship[1],
                "object": case.relationship[2],
            }
            if case.relationship
            else None
        ),
    )
    proposition = EvidenceProposition(
        proposition_id="prop_bench",
        mcu_id="mcu_bench",
        statement=case.commitment_text,
        commitments=(commitment,),
        provenance=ORIGIN,
    )
    from novelty_harness.evidence.verification.models import PassageSupportClaim

    claim = PassageSupportClaim(
        claim_id="claim_" + case.case_id,
        mapping_id="map_bench",
        source_id="src_bench",
        source_version_id=VERSION,
        mcu_id="mcu_bench",
        proposition_id=proposition.proposition_id,
        proposition_statement=proposition.statement,
        commitments=(commitment,),
        claimed_dimensions=(case.dimension,),
        passage_ids=("pass_bench",),
    )
    bundle = SupportEvidenceBundle(claim=claim, passages=(passage,))
    result = await verify_with_context_retry(
        _verifier(),
        bundle,
        available_passages=tuple(available),
        clock=lambda: datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    supplied = {item.passage_id for item in available}
    return {
        "case_id": case.case_id,
        "state": result.verification.state.value,
        "expected": case.expected_state,
        "relied_on": list(result.verification.relied_on_passage_ids),
        "citation_bundle_ok": set(result.verification.relied_on_passage_ids) <= supplied
        and all(record.rationale.strip() for record in result.verification.commitment_states),
        "expansions": len(result.expansions),
    }


def _metrics(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    total = len(rows)
    correct = sum(row["state"] == row["expected"] for row in rows)
    predicted_supported = [row for row in rows if row["state"] == "SUPPORTED"]
    true_supported = [row for row in predicted_supported if row["expected"] == "SUPPORTED"]
    expected_contradictions = [row for row in rows if row["expected"] == "CONTRADICTED"]
    caught_contradictions = [
        row for row in expected_contradictions if row["state"] == "CONTRADICTED"
    ]
    expected_insufficient = [row for row in rows if row["expected"] == "INSUFFICIENT_CONTEXT"]
    abstained = [row for row in expected_insufficient if row["state"] == "INSUFFICIENT_CONTEXT"]
    citation_integrity = sum(bool(row["citation_bundle_ok"]) for row in rows)
    return {
        "support_state_accuracy": correct / total,
        "supported_precision": (len(true_supported) / len(predicted_supported))
        if predicted_supported
        else 1.0,
        "contradiction_recall": (len(caught_contradictions) / len(expected_contradictions))
        if expected_contradictions
        else 1.0,
        "insufficient_context_abstention": (len(abstained) / len(expected_insufficient))
        if expected_insufficient
        else 1.0,
        "citation_presence_and_bundle_integrity": citation_integrity / total,
    }


async def test_support_verifier_benchmark_matches_baseline() -> None:
    rows = [await run_case(case) for case in CASES]
    metrics = _metrics(rows)
    baseline = json.loads(BASELINE_PATH.read_text())
    assert {row["case_id"]: row["state"] for row in rows} == baseline["cases"]
    assert metrics == baseline["metrics"]
    assert all(row["citation_bundle_ok"] for row in rows)
    assert any(row["expansions"] for row in rows), "context cases must exercise expansion"


def test_baseline_judge_is_documented_and_deterministic() -> None:
    first = baseline_judge(
        "the controller reduces operator checks",
        ("The controller reduces operator checks in the field trial.",),
    )
    second = baseline_judge(
        "the controller reduces operator checks",
        ("The controller reduces operator checks in the field trial.",),
    )
    assert first == second == BaselineJudgment("SUPPORTED", "passage states the claimed commitment")

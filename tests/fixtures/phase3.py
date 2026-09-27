"""Deterministic semantic recordings for Phase 3; production never imports these."""

from novelty_harness.domain.enums import EvidenceFamily
from tests.fixtures.phase1 import make_fixture


def applicability_response():
    return {
        "prompt_version": "family-applicability-v1",
        "assessments": [
            {
                "mcu_id": m.mcu_id,
                "evidence_family": family.value,
                "applicability": "POSSIBLY_APPLICABLE",
                "rationale": "This contribution may occur in this evidence ecosystem",
                "exclusion_reason": None,
                "exclusion_basis": None,
                "exclusion_support": [],
            }
            for m in make_fixture().graph.mcus
            for family in EvidenceFamily
        ],
    }

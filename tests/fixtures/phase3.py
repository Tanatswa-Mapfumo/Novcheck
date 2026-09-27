"""Deterministic semantic recordings for Phase 3; production never imports these."""

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.research.query_taxonomy import QueryFamily
from tests.fixtures.phase1 import make_fixture


def planning_response():
    intents, omissions = [], []
    texts = {
        "DIRECT_CANONICAL": "temperature sensor relay control",
        "SYNONYM_ACRONYM": "thermal transducer switching regulator",
        "FUNCTIONAL": "regulate switching using measured temperature",
        "MECHANISM": "temperature measurement controls relay switching",
        "RELATIONSHIP": "temperature sensor CONTROLS relay",
        "OUTCOME_OBJECTIVE": "reduce control operator workload",
        "HISTORICAL_TERMINOLOGY": "thermostatic switch regulator",
        "ADJACENT_DOMAIN": "process instrumentation measurement driven switching",
        "COMPONENT": "temperature transducer relay status indicator",
    }
    for row in applicability_response()["assessments"]:
        for family in QueryFamily:
            base = {
                "mcu_id": row["mcu_id"],
                "evidence_family": row["evidence_family"],
                "query_family": family.value,
                "rationale": "Investigate this search perspective",
            }
            if family.value not in texts:
                omissions.append(
                    {**base, "rationale": "No combination or discovered named entities yet"}
                )
            else:
                text = texts[family.value]
                if row["mcu_id"] == "mcu_status":
                    text = {
                        "DIRECT_CANONICAL": "separate status indicator operator checks",
                        "SYNONYM_ACRONYM": "operating state display annunciator",
                        "FUNCTIONAL": "display operating status to reduce operator checks",
                        "MECHANISM": "separate status indicator reduces operator checks",
                        "RELATIONSHIP": "status indicator REDUCES operator checks",
                        "OUTCOME_OBJECTIVE": "reduce operator workload through status display",
                        "HISTORICAL_TERMINOLOGY": "annunciator operator checks",
                        "ADJACENT_DOMAIN": "industrial process annunciator operator workload",
                        "COMPONENT": "status indicator display",
                    }[family.value]
                intents.append(
                    {
                        **base,
                        "query_id": f"qry_{len(intents)}",
                        "text": text,
                        "concepts": ["temperature", "relay"]
                        if row["mcu_id"] == "mcu_control"
                        else ["status indicator", "operator checks"],
                        "relationship_terms": [
                            "CONTROLS" if row["mcu_id"] == "mcu_control" else "REDUCES"
                        ]
                        if family.value == "RELATIONSHIP"
                        else [],
                        "historical_terms": [
                            "thermostatic" if row["mcu_id"] == "mcu_control" else "annunciator"
                        ]
                        if family.value == "HISTORICAL_TERMINOLOGY"
                        else [],
                    }
                )
    return {"prompt_version": "search-strategist-v1", "intents": intents, "omissions": omissions}


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

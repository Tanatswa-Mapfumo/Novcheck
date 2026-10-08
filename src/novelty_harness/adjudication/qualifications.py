"""Repository-referenced future robustness and domain qualifications."""

from typing import Literal

from novelty_harness.adjudication.models import TargetScoped


class RobustnessQualification(TargetScoped):
    contract_kind: Literal["phase7-robustness-qualification-v1"] = (
        "phase7-robustness-qualification-v1"
    )
    qualification_id: str
    status: Literal["NOT_YET_QUALIFIED", "QUALIFIED", "FAILED"] = "NOT_YET_QUALIFIED"
    method_version: str | None = None
    validation_artifact_id: str | None = None
    issuer: str | None = None


class DomainQualification(TargetScoped):
    contract_kind: Literal["phase7-domain-qualification-v1"] = "phase7-domain-qualification-v1"
    qualification_id: str
    status: Literal["NOT_QUALIFIED", "QUALIFIED", "FAILED"] = "NOT_QUALIFIED"
    domain: str | None = None
    method_version: str | None = None
    evidence_ref: str | None = None
    issuer: str | None = None

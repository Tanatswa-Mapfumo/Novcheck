"""Value availability is independent of novelty and input attribution."""

from typing import TYPE_CHECKING, Literal

from pydantic import model_validator

from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.enums import ValueMaturity
from novelty_harness.reporting.models import AuthorityRef, NonBlank, ReportContract, ReportScope


class ValueProjection(ReportContract):
    contract_kind: Literal["phase8-value-projection-v1"] = "phase8-value-projection-v1"
    scope: ReportScope
    kind: Literal["AUTHORITATIVE_VALUE_FINDING", "ATTRIBUTED_INPUT_CLAIM", "NO_VALUE_ASSESSMENT"]
    target: TargetRef | None = None
    claim: NonBlank | None = None
    maturity: ValueMaturity | None = None
    attributed_maturity_label: ValueMaturity | None = None
    basis_refs: tuple[AuthorityRef, ...] = ()

    @model_validator(mode="after")
    def value_basis(self) -> "ValueProjection":
        if self.kind == "AUTHORITATIVE_VALUE_FINDING":
            if self.maturity is None or not any(
                ref.kind == "VALUE_BASIS" for ref in self.basis_refs
            ):
                raise ValueError("assessed value requires maturity and a value-validation basis")
        elif self.maturity is not None:
            raise ValueError("input attribution/absence cannot assert assessed maturity")
        return self


def project_value(bundle: "ReportInputBundle") -> tuple[ValueProjection, ...]:
    """The accepted upstream path has no assessed-value issuer or validation basis."""
    from novelty_harness.reporting.bundle import field_ref, native_ref
    from novelty_harness.reporting.models import AuthorityKind

    cir_ref = native_ref(bundle, AuthorityKind.CIR)
    projected = [
        ValueProjection(
            scope=bundle.scope,
            kind="ATTRIBUTED_INPUT_CLAIM",
            claim=claim.statement,
            attributed_maturity_label=claim.maturity,
            basis_refs=(field_ref(cir_ref, claim, "claimed_advantages", index),),
        )
        for index, claim in enumerate(bundle.cir.claimed_advantages)
    ]
    # Even a frozen value entry joined only to CIR is input attribution, not an
    # independent assessment. No caller-supplied VALUE_BASIS can create an issuer.
    if any(
        not any(
            c.statement == v.claim and c.maturity == v.maturity
            for c in bundle.cir.claimed_advantages
        )
        for v in bundle.frozen_adjudication.value_findings
    ):
        raise ValueError("frozen value attribution differs from sealed CIR")
    projected.append(
        ValueProjection(
            scope=bundle.scope,
            kind="NO_VALUE_ASSESSMENT",
            basis_refs=(
                field_ref(
                    native_ref(bundle, AuthorityKind.FROZEN),
                    bundle.frozen_adjudication.value_findings,
                    "value_findings",
                ),
            ),
        )
    )
    return tuple(projected)


if TYPE_CHECKING:
    from novelty_harness.reporting.bundle import ReportInputBundle

from enum import StrEnum

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import TraceStatus
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.models import ProviderCallMetadata


class FailureCategory(StrEnum):
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    BAD_REQUEST = "BAD_REQUEST"
    SERVER_FAILURE = "SERVER_FAILURE"
    PARSE_FAILURE = "PARSE_FAILURE"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class ProviderFailure(ContractModel):
    model_config = ConfigDict(frozen=True)
    provider_name: NonBlankText
    query_id: str | None = None
    category: FailureCategory
    detail: NonBlankText
    call: ProviderCallMetadata | None = None


class ProviderError(RuntimeError):
    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__(f"{failure.provider_name}: {failure.category.value}: {failure.detail}")


def provider_error(
    provider: str,
    category: FailureCategory,
    detail: str,
    query_id: str | None = None,
    call: ProviderCallMetadata | None = None,
) -> ProviderError:
    if call is not None:
        call = ProviderCallMetadata.model_validate(
            {
                **call.model_dump(),
                "status": TraceStatus.FAILURE,
                "failure_code": category.value,
            }
        )
    return ProviderError(
        ProviderFailure(
            provider_name=provider, query_id=query_id, category=category, detail=detail, call=call
        )
    )

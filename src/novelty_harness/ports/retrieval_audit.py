from collections.abc import Callable
from typing import Literal, Protocol, runtime_checkable

from pydantic import ConfigDict, JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.ports.models import ProviderCallMetadata
from novelty_harness.research.provider_queries import CompiledProviderQuery


class BudgetExhausted(RuntimeError):
    pass


class RetrievalRequestEvent(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["retrieval-request-event-v1"] = "retrieval-request-event-v1"
    compiled_query: CompiledProviderQuery
    call: ProviderCallMetadata | None = None
    attempts: tuple[dict[str, JsonValue], ...] = ()
    failure_code: str | None = None


@runtime_checkable
class BudgetedRetrievalProvider(Protocol):
    def set_request_guard(self, guard: Callable[[], None] | None) -> None: ...
    def set_document_limit(self, limit: Callable[[], int | None] | None) -> None: ...
    def retrieval_request_events(self) -> tuple[RetrievalRequestEvent, ...]: ...

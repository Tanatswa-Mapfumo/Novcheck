from typing import Protocol, runtime_checkable

from pydantic import ConfigDict, JsonValue

from novelty_harness.domain.base import ContractModel


class ScreeningDiagnostics(ContractModel):
    model_config = ConfigDict(frozen=True)
    attempts: tuple[dict[str, JsonValue], ...] = ()
    limitations: tuple[str, ...] = ()
    had_failed_attempts: bool = False
    complete: bool = True


@runtime_checkable
class SearchAuditSource(Protocol):
    def screening_diagnostics(self, query_id: str) -> ScreeningDiagnostics: ...

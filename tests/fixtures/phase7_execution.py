"""Deterministic protocol executions for repository authority fixtures."""

import asyncio

from novelty_harness.application.phase7_execution import (
    completed_invocation,
    invocation_configuration,
)
from novelty_harness.application.phase7_roles import make_phase7_artifact


async def executed_artifact_async(repository, run_id, kind, proposal):
    class RecordedPort:
        async def propose(self):
            return proposal

    port = RecordedPort()
    config = invocation_configuration(port, kind, proposal)
    registration = make_phase7_artifact(run_id, "SEMANTIC_CONFIGURATION", config)
    repository.record_phase7_artifact(run_id, registration)
    result = await port.propose()
    execution = completed_invocation(
        port, result, config, registration.artifact_id, {"fixture_invocation": result.target_id}
    )
    return make_phase7_artifact(run_id, kind, result, execution=execution)


def executed_artifact(repository, run_id, kind, proposal):
    return asyncio.run(executed_artifact_async(repository, run_id, kind, proposal))

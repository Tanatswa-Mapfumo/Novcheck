import inspect
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from novelty_harness.application import ports
from novelty_harness.application.models import VerticalSliceComponents

PORT_METHODS = [
    ("IdeaNormalizer", "normalize"),
    ("SufficiencyAnalyzer", "analyze"),
    ("MCUDecomposer", "decompose"),
    ("MCUReconciler", "reconcile"),
    ("SearchPlanner", "plan"),
    ("SearchPlanReviewer", "review"),
    ("EvidenceMapper", "map"),
    ("EvidenceVerifier", "verify"),
    ("AdjudicationEngine", "adjudicate"),
]


@pytest.mark.parametrize("port_name,method_name", PORT_METHODS)
async def test_semantic_ports_are_replaceable_runtime_checkable_and_async(port_name, method_name):
    async def operation(self, value):
        return value

    fake = type("LocalFake", (), {method_name: operation})()
    protocol = getattr(ports, port_name)
    assert isinstance(fake, protocol)
    assert not isinstance(object(), protocol)
    assert inspect.iscoroutinefunction(getattr(protocol, method_name))
    payload = object()
    assert await getattr(fake, method_name)(payload) is payload


def test_components_are_a_frozen_dataclass_not_a_persisted_model():
    values = {
        name: object()
        for name in (
            "normalizer",
            "sufficiency_analyzer",
            "decomposer",
            "reconciler",
            "planner",
            "plan_reviewer",
            "mapper",
            "verifier",
            "adjudicator",
        )
    }
    bundle = VerticalSliceComponents(**values)
    assert is_dataclass(bundle)
    assert not hasattr(bundle, "model_dump")
    with pytest.raises(FrozenInstanceError):
        bundle.normalizer = object()


def test_application_ports_do_not_import_fixtures():
    assert "tests.fixtures" not in inspect.getsource(ports)

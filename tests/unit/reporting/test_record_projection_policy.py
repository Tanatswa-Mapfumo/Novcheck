"""V2 attributed-record projection is deterministic; v1 formatting remains exact."""

import json
import os
import subprocess
import sys

from novelty_harness.reporting.fallback import _record_text, attributed_text

_CHILD = """
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.research.coverage import CoverageCell, CoverageState
from novelty_harness.research.query_taxonomy import QueryFamily
from novelty_harness.reporting.fallback import _record_text
from pytest_socket import disable_socket

disable_socket(allow_unix_socket=True)
cell = CoverageCell(mcu_id='mcu_record_projection', evidence_family=EvidenceFamily.SCHOLARLY,
    state=CoverageState.DEGRADED, planned_query_families=frozenset(QueryFamily),
    configured_providers=('second', 'first'), limitations=('missing family', 'budget limit'))
print(_record_text('Actual coverage state', cell, bundle_version='p8-bundle-v2'))
"""


def test_v2_record_projection_is_stable_across_hash_seeds_and_retains_order():
    texts = []
    for seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-B", "-c", _CHILD],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        texts.append(result.stdout)
    assert texts[0] == texts[1]
    assert texts[0].index("second") < texts[0].index("first")
    assert texts[0].index("missing family") < texts[0].index("budget limit")
    from novelty_harness.research.query_taxonomy import QueryFamily

    assert all(family.value in texts[0] for family in QueryFamily)


def test_legacy_record_projection_keeps_original_json_mode_bytes():
    from novelty_harness.domain.enums import EvidenceFamily
    from novelty_harness.research.coverage import CoverageCell, CoverageState
    from novelty_harness.research.query_taxonomy import QueryFamily

    cell = CoverageCell(
        mcu_id="mcu_record_projection",
        evidence_family=EvidenceFamily.SCHOLARLY,
        state=CoverageState.DEGRADED,
        planned_query_families=frozenset(QueryFamily),
        configured_providers=("second", "first"),
        limitations=("missing family", "budget limit"),
    )
    original = cell.model_dump(mode="json")
    original.pop("schema_version")
    expected = attributed_text(
        "Actual coverage state", json.dumps(original, ensure_ascii=False, sort_keys=True)
    )
    assert _record_text("Actual coverage state", cell) == expected
    assert _record_text("Actual coverage state", cell, bundle_version="p8-bundle-v1") == expected


def test_v2_projection_retains_json_field_serializers_and_all_nested_values():
    from pydantic import BaseModel, field_serializer

    class RecordedShape(BaseModel):
        value: int
        families: frozenset[str]
        ordered: tuple[str, ...]
        nested: dict[str, tuple[str, ...]]

        @field_serializer("value", when_used="json")
        def formatted_value(self, value):
            return f"recorded:{value}"

    document = RecordedShape(
        value=7, families={"z", "a"}, ordered=("z", "a"), nested={"all": ("z", "a")}
    )
    text = _record_text("Recorded shape", document, bundle_version="p8-bundle-v2")
    expected = {
        "value": "recorded:7",
        "families": ["a", "z"],
        "ordered": ["z", "a"],
        "nested": {"all": ["z", "a"]},
    }
    assert text == attributed_text(
        "Recorded shape", json.dumps(expected, ensure_ascii=False, sort_keys=True)
    )

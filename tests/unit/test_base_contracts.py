def test_package_exposes_version() -> None:
    import novelty_harness

    assert novelty_harness.__version__ == "0.1.0"


def test_versioned_contract_rejects_unknown_fields() -> None:
    import json
    from datetime import UTC, timedelta

    import pytest
    from pydantic import ValidationError

    from novelty_harness.domain.base import ContractModel, utc_now

    class ExampleContract(ContractModel):
        value: str

    model = ExampleContract(value="x")
    assert model.schema_version == "0.1"
    assert json.loads(json.dumps(model.model_dump(mode="json"))) == {
        "schema_version": "0.1",
        "value": "x",
    }
    for extra in ({"other": 1}, {"schema_version": "0.2"}):
        with pytest.raises(ValidationError):
            ExampleContract.model_validate({"value": "x", **extra})
    assert utc_now().tzinfo == UTC
    assert utc_now().utcoffset() == timedelta(0)

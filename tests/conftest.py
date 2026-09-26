import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for group in ("unit", "contract", "integration"):
            if group in item.path.parts:
                item.add_marker(getattr(pytest.mark, group))

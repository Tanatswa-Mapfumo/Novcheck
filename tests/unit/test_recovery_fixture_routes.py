"""Route selection controls; native authority remains an independent required gate."""

from pathlib import Path

import pytest


def api():
    from tests.fixtures.native_baselines import fixture_route

    return fixture_route


def test_only_verified_projection_owners_can_use_reusable_baselines():
    route = api()
    for owner in ("tests.unit.reporting.test_obligations", "tests.unit.reporting.test_uncertainty"):
        assert route(owner, "cached") == "cached"
        assert route(owner, "original") == "original"
    for owner in (
        "tests.unit.reporting.test_attempts",
        "tests.unit.evidence.graph.test_phase7_store",
        "unknown",
    ):
        assert route(owner, "cached") == "original"


@pytest.mark.parametrize("mode", ["", "unknown", "CACHED", None])
def test_unknown_fixture_mode_cannot_silently_select_cache(mode):
    with pytest.raises(ValueError, match="fixture mode"):
        api()("tests.unit.reporting.test_obligations", mode)


def test_owner_route_retains_private_destination_and_original_builder(tmp_path, monkeypatch):
    import tests.fixtures.native_baselines as native
    import tests.fixtures.phase8 as phase8

    builds = []
    calls = []
    case = object()

    def build(path, **kwargs):
        builds.append((path, kwargs))
        return case

    def reuse(cache, destination, **kwargs):
        calls.append((cache, destination, kwargs))
        return kwargs["builder"](tmp_path / "source")

    monkeypatch.setattr(phase8, "make_report_case", build)
    monkeypatch.setattr(native, "reusable_report_case", reuse)
    monkeypatch.setattr(native, "execution_identity", lambda *_: ("a" * 64, "b" * 64, {}))

    def observe(event):
        pass

    destination = tmp_path / "private"
    assert (
        native.owned_report_case(
            "tests.unit.reporting.test_obligations",
            destination,
            mode="cached",
            cache_root=tmp_path / "cache",
            observe=observe,
        )
        is case
    )
    assert calls[0][0] == tmp_path / "cache"
    assert calls[0][1] == destination / "evidence_graph.sqlite3"
    assert builds[0][0] == tmp_path / "source"
    assert builds[0][1]["observe"] is observe
    assert callable(builds[0][1]["observation_clock"])
    assert (
        native.owned_report_case(
            "tests.unit.reporting.test_attempts",
            tmp_path / "independent",
            mode="cached",
            cache_root=tmp_path / "cache",
            observe=observe,
        )
        is case
    )
    assert len(calls) == 1
    assert builds[-1][0] == tmp_path / "independent"
    assert "observation_clock" not in builds[-1][1]
    assert all(isinstance(path, Path) for path, _ in builds)

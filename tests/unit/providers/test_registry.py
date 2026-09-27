import pytest

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.providers.errors import ProviderError
from novelty_harness.providers.registry import CredentialRef, ProviderDescriptor, ProviderRegistry
from tests.fixtures.phase1 import make_fixture


def descriptor():
    return ProviderDescriptor(
        name=make_fixture().search_provider.name,
        evidence_families=frozenset({EvidenceFamily.SCHOLARLY}),
        search_capabilities=frozenset({"text"}),
        auth_mode="none",
        supports_pagination=True,
    )


def test_registry_lookup_duplicates_unavailable_and_explicit_fallback():
    registry = ProviderRegistry()
    provider = make_fixture().search_provider
    registry.register(provider, descriptor())
    assert registry.providers_for(EvidenceFamily.PATENT) == ()
    assert registry.providers_for(EvidenceFamily.SCHOLARLY)[0].provider is provider
    with pytest.raises(ValueError):
        registry.register(provider, descriptor())
    with pytest.raises(ProviderError):
        registry.get("missing")
    registry.record_fallback("missing", provider.name, reason="Unavailable configured primary")
    assert registry.fallbacks[0].reason


def test_credential_reference_is_only_an_environment_name(monkeypatch):
    monkeypatch.setenv("NOVCHECK_TEST_TOKEN", "secret")
    ref = CredentialRef(env_name="NOVCHECK_TEST_TOKEN")
    assert ref.resolve() == "secret"
    assert "secret" not in ref.model_dump_json()
    with pytest.raises(ValueError):
        CredentialRef(env_name="token=value")

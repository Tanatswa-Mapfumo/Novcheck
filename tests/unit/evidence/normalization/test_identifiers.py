import pytest

from novelty_harness.evidence.normalization.identifiers import (
    ArxivIdentity,
    merge_identifiers,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_patent_number,
    normalize_repository,
    normalize_semantic_scholar_id,
    normalize_url,
)
from novelty_harness.evidence.normalization.models import CanonicalIdentifiers


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10.1234/ABC", "10.1234/abc"),
        ("https://doi.org/10.1234/AbC", "10.1234/abc"),
        ("http://dx.doi.org/10.1234/abc", "10.1234/abc"),
        ("doi:10.1234/abc", "10.1234/abc"),
        ("  DOI:10.1234/abc  ", "10.1234/abc"),
    ],
)
def test_doi_forms_normalize_to_the_same_value(value, expected):
    assert normalize_doi(value) == expected


@pytest.mark.parametrize("value", ["", "not-a-doi", "10.1/x", "https://example.org/10.1234/x"])
def test_invalid_dois_are_rejected(value):
    assert normalize_doi(value) is None


def test_openalex_ids_normalize_from_urls():
    assert normalize_openalex_id("https://openalex.org/W123456") == "W123456"
    assert normalize_openalex_id("w123456") == "W123456"
    assert normalize_openalex_id("openalex:W123456") == "W123456"
    assert normalize_openalex_id("W123456") == "W123456"
    assert normalize_openalex_id("W") is None
    assert normalize_openalex_id("12345") is None


def test_semantic_scholar_ids_normalize_from_api_and_web_forms():
    digest = "a" * 40
    assert normalize_semantic_scholar_id(digest.upper()) == digest
    assert (
        normalize_semantic_scholar_id(f"https://www.semanticscholar.org/paper/Title/{digest}")
        == digest
    )
    assert normalize_semantic_scholar_id("not-a-paper-id") is None


def test_arxiv_versions_are_the_same_work_with_distinct_versions():
    v1 = normalize_arxiv_id("arXiv:2001.00001v1")
    v3 = normalize_arxiv_id("https://arxiv.org/abs/2001.00001v3")
    bare = normalize_arxiv_id("2001.00001")
    assert v1 == ArxivIdentity(base_id="2001.00001", version=1)
    assert v3 == ArxivIdentity(base_id="2001.00001", version=3)
    assert bare == ArxivIdentity(base_id="2001.00001")
    assert v1 is not None and v3 is not None and bare is not None
    assert v1.base_id == v3.base_id == bare.base_id
    assert {v1.canonical(), v3.canonical()} == {"2001.00001v1", "2001.00001v3"}
    old = normalize_arxiv_id("https://arxiv.org/pdf/hep-th/9901001v2.pdf")
    assert old == ArxivIdentity(base_id="hep-th/9901001", version=2)
    assert normalize_arxiv_id("2001.000001") is None
    assert normalize_arxiv_id("not-an-id") is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://github.com/Owner/Repo", "owner/repo"),
        ("https://github.com/Owner/Repo.git", "owner/repo"),
        ("git@github.com:Owner/Repo.git", "owner/repo"),
        ("github.com/Owner/Repo/tree/main/src", "owner/repo"),
        ("Owner/Repo", "owner/repo"),
    ],
)
def test_github_forms_normalize(value, expected):
    assert normalize_repository(value) == expected


@pytest.mark.parametrize("value", ["Owner", "https://gitlab.com/Owner/Repo", "  ", "a/b/c/d"])
def test_non_repository_forms_are_rejected(value):
    assert normalize_repository(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("US 10,123,456 B2", "US10123456B2"),
        ("US10123456B2", "US10123456B2"),
        ("WO2020/123456 A1", "WO2020123456A1"),
        ("EP 3 456 789 A1", "EP3456789A1"),
    ],
)
def test_patent_forms_normalize_conservatively(value, expected):
    assert normalize_patent_number(value) == expected


@pytest.mark.parametrize("value", ["", "12345", "PAPER-1", "US123"])
def test_invalid_patent_forms_are_rejected(value):
    assert normalize_patent_number(value) is None


def test_canonical_url_normalization_is_deterministic():
    assert (
        normalize_url("HTTPS://Example.ORG:443/Path?b=2&a=1&utm_source=x#frag")
        == "https://example.org/Path?a=1&b=2"
    )
    assert normalize_url("http://example.org:80/") == "http://example.org/"
    assert normalize_url("https://user:pass@example.org/a") is None
    assert normalize_url("ftp://example.org/a") is None
    assert normalize_url("not a url") is None


def test_merge_identifiers_preserves_conflicts_and_unresolved_fields():
    first = CanonicalIdentifiers(
        doi="10.1234/one", openalex_id="W1", repository="owner/repo", other={"pmid": "1"}
    )
    second = CanonicalIdentifiers(doi="10.1234/two", openalex_id="W1")
    merge = merge_identifiers((first, second))
    assert merge.identifiers.doi is None
    assert merge.identifiers.openalex_id == "W1"
    assert merge.identifiers.repository == "owner/repo"
    assert merge.identifiers.other == {"pmid": "1"}
    assert [(c.field, c.observed_values) for c in merge.conflicts] == [
        ("doi", ("10.1234/one", "10.1234/two"))
    ]
    assert "doi" in merge.unresolved


def test_merge_identifiers_ignores_absent_observations():
    merge = merge_identifiers((CanonicalIdentifiers(), CanonicalIdentifiers(doi="10.1234/one")))
    assert merge.identifiers.doi == "10.1234/one"
    assert not merge.conflicts
    assert not merge.unresolved
    assert merge_identifiers(()).identifiers.is_empty()


def test_same_title_different_doi_has_no_shared_identity():
    first = merge_identifiers((CanonicalIdentifiers(doi="10.1234/one"),))
    second = merge_identifiers((CanonicalIdentifiers(doi="10.1234/two"),))
    assert first.identifiers.doi != second.identifiers.doi

"""Deterministic identifier normalization.

Every function returns a canonical form or ``None``. Nothing here guesses
identity from titles or fuzzy similarity, and every ambiguity is surfaced
instead of being silently resolved.
"""

import re
from collections.abc import Sequence
from typing import Literal, Self
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.evidence.normalization.models import CanonicalIdentifiers

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_OPENALEX = re.compile(r"^W\d+$")
_SEMANTIC_SCHOLAR = re.compile(r"^[0-9a-f]{40}$")
_ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(?:v(\d+))?$")
_ARXIV_OLD = re.compile(r"^([A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z]{2})?/\d{7})(?:v(\d+))?$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_PATENT = re.compile(r"^[A-Z]{2}\d{5,}(?:[A-Z]\d?)?$")
_TRACKING_PARAMETERS = frozenset(
    {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src", "source"}
)


class ArxivIdentity(ContractModel):
    """arXiv identity with its version suffix kept separate."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["arxiv-identity-v1"] = "arxiv-identity-v1"

    base_id: NonBlankText
    version: int | None = Field(default=None, ge=1)

    def canonical(self) -> str:
        return f"{self.base_id}v{self.version}" if self.version is not None else self.base_id


class IdentifierConflict(ContractModel):
    """One field where independent observations disagree."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["identifier-conflict-v1"] = "identifier-conflict-v1"

    field: NonBlankText
    observed_values: tuple[NonBlankText, ...] = Field(min_length=2)


class IdentifierMerge(ContractModel):
    """Merged identifiers plus every disagreement that blocked a merge."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["identifier-merge-v1"] = "identifier-merge-v1"

    identifiers: CanonicalIdentifiers
    conflicts: tuple[IdentifierConflict, ...] = ()
    unresolved: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def conflicts_are_unresolved(self) -> Self:
        if not {conflict.field for conflict in self.conflicts} <= set(self.unresolved):
            raise ValueError("Every conflict must leave its field unresolved")
        return self


def _strip(value: str) -> str:
    return value.strip()


def normalize_doi(value: str) -> str | None:
    """Canonicalize DOI URLs, ``doi:`` prefixes and casing."""

    text = _strip(value).casefold()
    for prefix in _DOI_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text if _DOI.fullmatch(text) else None


def normalize_openalex_id(value: str) -> str | None:
    text = _strip(value)
    for prefix in ("https://openalex.org/", "http://openalex.org/", "openalex:"):
        if text.casefold().startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    text = text.upper()
    return text if _OPENALEX.fullmatch(text) else None


def normalize_semantic_scholar_id(value: str) -> str | None:
    text = _strip(value).casefold()
    if "semanticscholar.org/paper/" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return text if _SEMANTIC_SCHOLAR.fullmatch(text) else None


def normalize_arxiv_id(value: str) -> ArxivIdentity | None:
    """Canonicalize arXiv IDs and split an explicit version suffix."""

    text = _strip(value)
    lowered = text.casefold()
    for prefix in (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://arxiv.org/pdf/",
        "http://arxiv.org/pdf/",
        "arxiv:",
    ):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if text.casefold().endswith(".pdf"):
        text = text[: -len(".pdf")]
    text = text.rstrip("/").strip()
    if match := _ARXIV_NEW.fullmatch(text):
        base, version = match.groups()
        return ArxivIdentity(base_id=base, version=int(version) if version else None)
    if match := _ARXIV_OLD.fullmatch(text):
        base, version = match.groups()
        return ArxivIdentity(base_id=base.casefold(), version=int(version) if version else None)
    return None


def normalize_repository(value: str) -> str | None:
    """Canonicalize GitHub ``owner/repository`` identity; forks stay distinct."""

    text = _strip(value)
    deep_ok = False
    if text.casefold().startswith("git@github.com:"):
        text = text[len("git@github.com:") :]
        deep_ok = True
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if text.casefold().startswith(prefix):
            text = text[len(prefix) :]
            deep_ok = True
            break
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    if text.casefold().endswith(".git"):
        text = text[: -len(".git")]
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2 or (not deep_ok and len(parts) != 2):
        return None
    candidate = parts[0] + "/" + parts[1]
    return candidate.casefold() if _REPOSITORY.fullmatch(candidate) else None


def normalize_patent_number(value: str) -> str | None:
    """Conservatively compact patent publication/application identifiers."""

    compact = re.sub(r"[^A-Z0-9]", "", _strip(value).upper())
    return compact if _PATENT.fullmatch(compact) else None


def normalize_url(value: str) -> str | None:
    """Canonicalize an HTTP(S) URL for deterministic identity comparison."""

    text = _strip(value)
    try:
        split = urlsplit(text)
        if split.scheme.casefold() not in {"http", "https"} or not split.hostname:
            return None
        if split.username or split.password:
            return None
        hostname = split.hostname.casefold()
        port = split.port
        netloc = hostname
        if port is not None and not (
            (split.scheme.casefold() == "http" and port == 80)
            or (split.scheme.casefold() == "https" and port == 443)
        ):
            netloc = f"{hostname}:{port}"
        query = [
            (key, item)
            for key, item in parse_qsl(split.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
        ]
        query.sort()
        path = split.path or "/"
        return urlunsplit((split.scheme.casefold(), netloc, path, urlencode(query), ""))
    except ValueError:
        return None


def merge_identifiers(values: Sequence[CanonicalIdentifiers]) -> IdentifierMerge:
    """Merge identifier observations, preserving every disagreement.

    A field with disagreeing values is left unset and reported as both a
    conflict and an unresolved field. Empty observations cannot establish
    identity and are not treated as conflicts.
    """

    conflicts: list[IdentifierConflict] = []
    unresolved: list[str] = []
    merged: dict[str, object] = {}

    def scalar(field: str) -> None:
        observed = sorted({value for item in values if (value := getattr(item, field)) is not None})
        if len(observed) == 1:
            merged[field] = observed[0]
        elif len(observed) > 1:
            conflicts.append(IdentifierConflict(field=field, observed_values=tuple(observed)))
            unresolved.append(field)

    for field in ("doi", "openalex_id", "semantic_scholar_id", "arxiv_id", "repository"):
        scalar(field)

    patents = sorted({number for item in values for number in item.patent_numbers})
    merged["patent_numbers"] = tuple(patents)

    other: dict[str, set[str]] = {}
    for item in values:
        for key, value in item.other.items():
            other.setdefault(key, set()).add(value)
    agreed_other: dict[str, str] = {}
    for key, observed in sorted(other.items()):
        if len(observed) == 1:
            agreed_other[key] = next(iter(observed))
        else:
            conflict_field = f"other.{key}"
            conflicts.append(
                IdentifierConflict(field=conflict_field, observed_values=tuple(sorted(observed)))
            )
            unresolved.append(conflict_field)
    merged["other"] = agreed_other

    return IdentifierMerge(
        identifiers=CanonicalIdentifiers.model_validate(merged),
        conflicts=tuple(conflicts),
        unresolved=tuple(unresolved),
    )

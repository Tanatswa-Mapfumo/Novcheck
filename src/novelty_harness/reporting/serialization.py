"""Bounded digests of already serialized report JSON projections.

Callers supply JSON-mode model dumps, not arbitrary Python/model values. The
encoder preserves the existing canonical JSON options and rejects nonfinite
numbers. This does not validate a proposal or certify native authority.
"""

import hashlib
import json
from typing import cast

from pydantic import BaseModel, JsonValue


def canonical_json_digest(value: JsonValue) -> str:
    encoder = json.JSONEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    digest = hashlib.sha256()
    for chunk in encoder.iterencode(value):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def share_validated_strings(
    value: object, original: object, strings: dict[str, str] | None = None
) -> object:
    """Reuse equal immutable strings only AFTER a complete schema validation.

    The pool is private to one operation. Models and mutable containers remain
    private snapshots; normalization, field values and canonical bytes never
    change. A mismatching input type/value cannot replace validated data.
    """
    if strings is None:
        strings = {}
    if type(value) is str:
        text = value
        selected = original if type(original) is str and original == text else text
        return strings.setdefault(selected, selected)
    if type(value) is not type(original):
        return value
    if isinstance(value, BaseModel):
        source = cast(BaseModel, original)
        updates: dict[str, object] = {}
        for name in type(value).model_fields:
            validated = getattr(value, name)
            shared = share_validated_strings(validated, getattr(source, name, None), strings)
            if shared is not validated:
                updates[name] = shared
        return value.model_copy(update=updates) if updates else value
    if type(value) is tuple:
        items, source_items = cast(tuple[object, ...], value), cast(tuple[object, ...], original)
        if len(items) != len(source_items):
            return items
        return tuple(
            share_validated_strings(item, source, strings)
            for item, source in zip(items, source_items, strict=True)
        )
    if type(value) is list:
        items, source_items = cast(list[object], value), cast(list[object], original)
        if len(items) != len(source_items):
            return items
        return [
            share_validated_strings(item, source, strings)
            for item, source in zip(items, source_items, strict=True)
        ]
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        source_mapping = cast(dict[object, object], original)
        if not all(type(key) is str for key in source_mapping):
            return mapping
        return {
            key: share_validated_strings(item, source_mapping.get(key), strings)
            for key, item in mapping.items()
        }
    return value


# Preserve the existing internal name; neither entrypoint certifies authority.
_share_validated_strings = share_validated_strings

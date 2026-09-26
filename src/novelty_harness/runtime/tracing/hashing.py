import hashlib
import json
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel, JsonValue
from pydantic_core import to_jsonable_python


def _canonical_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {key: _canonical_value(item) for key, item in mapping.items()}
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in cast(set[object], value)]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, allow_nan=False))
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in cast(list[object], value)]
    return to_jsonable_python(value)


def canonical_json(value: JsonValue | BaseModel, *, ensure_ascii: bool = True) -> str:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        allow_nan=False,
    )


def canonical_hash(value: JsonValue | BaseModel) -> str:
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

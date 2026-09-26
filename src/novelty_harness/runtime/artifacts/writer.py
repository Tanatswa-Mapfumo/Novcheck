from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, JsonValue, TypeAdapter

from novelty_harness.domain.ids import AssessmentId
from novelty_harness.runtime.tracing.hashing import canonical_json

_ASSESSMENT_ID: TypeAdapter[str] = TypeAdapter(AssessmentId)


class RunArtifactWriter:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def assessment_dir(self, assessment_id: AssessmentId) -> Path:
        identity = _ASSESSMENT_ID.validate_python(assessment_id)
        if "/" in identity or "\\" in identity:
            raise ValueError("assessment ID must be a single directory component")
        path = self._root / identity
        if path.is_symlink():
            raise ValueError("assessment directory cannot be a symlink")
        return path

    def _path(self, assessment_id: AssessmentId, relative_name: str) -> Path:
        relative = Path(relative_name)
        if (
            not relative_name
            or "\\" in relative_name
            or relative.is_absolute()
            or ".." in relative.parts
            or relative == Path(".")
        ):
            raise ValueError("artifact path must stay within its assessment directory")
        directory = self.assessment_dir(assessment_id)
        target = directory / relative
        if not target.resolve().is_relative_to(directory):
            raise ValueError("artifact path escapes its assessment directory")
        if any(path.is_symlink() for path in (target, *target.parents) if path != self._root):
            raise ValueError("artifact path cannot traverse symlinks")
        return target

    def write_json(
        self, assessment_id: AssessmentId, relative_name: str, value: BaseModel | JsonValue
    ) -> Path:
        return self.write_text(
            assessment_id, relative_name, canonical_json(value, ensure_ascii=False) + "\n"
        )

    def write_jsonl(
        self,
        assessment_id: AssessmentId,
        relative_name: str,
        values: Sequence[BaseModel | JsonValue],
    ) -> Path:
        lines: list[str] = []
        for value in values:
            if not isinstance(value, (BaseModel, dict)):
                raise ValueError("JSONL rows must be objects")
            line = canonical_json(value, ensure_ascii=False)
            if not line.startswith("{"):
                raise ValueError("JSONL rows must serialize as objects")
            lines.append(line + "\n")
        return self.write_text(assessment_id, relative_name, "".join(lines))

    def write_text(self, assessment_id: AssessmentId, relative_name: str, text: str) -> Path:
        target = self._path(assessment_id, relative_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return target

from pathlib import Path

from novelty_harness.research.coverage import CoveragePolicy


def load_coverage_policy(path: Path | None = None) -> CoveragePolicy:
    if path is None:
        return CoveragePolicy.standard()
    return CoveragePolicy.model_validate_json(path.read_text(encoding="utf-8"))

import json
from pathlib import Path

import pytest

from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.ports.models import ProviderCapabilities
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter


def test_run_directories_are_lazy(tmp_path):
    root = tmp_path / "runs"
    writer = RunArtifactWriter(root)
    directory = writer.assessment_dir("asm_test")
    assert directory == root / "asm_test"
    assert not root.exists()
    assert (
        writer.write_text("asm_test", "input/original.txt", "exact\ninput").read_text()
        == "exact\ninput"
    )
    assert directory.is_dir()


@pytest.mark.parametrize(
    "name", ["../escape.json", "/escape.json", "nested/../../escape", "", ".", "a\\..\\escape"]
)
def test_artifact_paths_cannot_escape(tmp_path, name):
    writer = RunArtifactWriter(tmp_path / "runs")
    with pytest.raises(ValueError):
        writer.write_json("asm_test", name, {"schema_version": "0.1"})


@pytest.mark.parametrize(
    "identity", ["asm_../escape", "asm_a/../../escape", "asm_a\\escape", "wrong"]
)
def test_assessment_ids_are_safe_directory_components(tmp_path, identity):
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path).write_text(identity, "report.md", "text")


def test_existing_symlink_cannot_escape_assessment(tmp_path):
    writer = RunArtifactWriter(tmp_path / "runs")
    directory = writer.assessment_dir("asm_test")
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (directory / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        writer.write_text("asm_test", "linked/report.md", "text")
    assert not (outside / "report.md").exists()


def test_assessment_directory_symlink_cannot_escape(tmp_path):
    (tmp_path / "asm_test").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path).write_text("asm_test", "report.md", "text")


def test_json_is_deterministic_utf8_and_round_trips_models(tmp_path):
    writer = RunArtifactWriter(tmp_path)
    path = writer.write_json("asm_test", "data.json", {"z": chr(233), "a": {"y": 2, "x": 1}})
    first = path.read_bytes()
    writer.write_json("asm_test", "data.json", {"a": {"x": 1, "y": 2}, "z": chr(233)})
    assert path.read_bytes() == first
    assert chr(233).encode("utf-8") in first
    request = AssessmentRequest(idea_id="idea_test", input_text="Exact input", as_of="2026-09-26")
    path = writer.write_json("asm_test", "request.json", request)
    assert AssessmentRequest.model_validate_json(path.read_text()) == request
    caps = ProviderCapabilities(evidence_families={EvidenceFamily.PATENT, EvidenceFamily.SOFTWARE})
    path = writer.write_json("asm_test", "caps.json", caps)
    assert json.loads(path.read_text())["evidence_families"] == ["PATENT", "SOFTWARE"]


def test_jsonl_has_one_versioned_object_per_line(tmp_path):
    writer = RunArtifactWriter(tmp_path)
    request = AssessmentRequest(idea_id="idea_test", input_text="Two\nlines", as_of="2026-09-26")
    path = writer.write_jsonl("asm_test", "items.jsonl", [request, request])
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert all(AssessmentRequest.model_validate_json(line) == request for line in lines)


def test_jsonl_empty_sequence_is_empty_file(tmp_path):
    assert (
        RunArtifactWriter(tmp_path).write_jsonl("asm_test", "items.jsonl", []).read_bytes() == b""
    )


@pytest.mark.parametrize("value", [None, "text", [1, 2], 3])
def test_jsonl_rejects_non_object_rows(tmp_path, value):
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path).write_jsonl("asm_test", "items.jsonl", [value])


def test_replace_is_atomic_and_temporary_file_is_same_directory(tmp_path, monkeypatch):
    writer = RunArtifactWriter(tmp_path)
    target = writer.write_text("asm_test", "report.md", "old")
    original_replace = Path.replace
    observed = []

    def check_replace(temporary, destination):
        observed.append(temporary)
        assert temporary.parent == target.parent
        assert target.read_text() == "old"
        assert temporary.read_text() == "new"
        return original_replace(temporary, destination)

    monkeypatch.setattr(Path, "replace", check_replace)
    assert writer.write_text("asm_test", "report.md", "new") == target
    assert target.read_text() == "new"
    assert len(observed) == 1
    assert not observed[0].exists()


def test_failed_replace_preserves_old_artifact_and_cleans_temp(tmp_path, monkeypatch):
    writer = RunArtifactWriter(tmp_path)
    target = writer.write_text("asm_test", "report.md", "old")

    def fail_replace(*args):
        raise OSError("fixture replacement failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="fixture replacement failure"):
        writer.write_text("asm_test", "report.md", "new")
    assert target.read_text() == "old"
    assert list(target.parent.iterdir()) == [target]


def test_nonfinite_json_is_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError):
        RunArtifactWriter(tmp_path).write_json("asm_test", "bad.json", {"value": float("inf")})
    assert not (tmp_path / "asm_test").exists()

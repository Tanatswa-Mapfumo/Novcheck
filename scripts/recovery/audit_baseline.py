"""Read-only forensic integrity/source-cost inventory; imports no application code."""

import argparse
import ast
import hashlib
import json
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

BASELINE = "d0589769407061b6bf00b8f7f4fadb3c966ac1dc"
EXPENSIVE_CALLS = {
    "model_validate",
    "model_validate_json",
    "model_dump",
    "model_dump_json",
    "canonical_hash",
    "canonical_json",
    "deepcopy",
    "backup",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing audit record")
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").is_file():
        parser.error("run only in the persistent linked recovery worktree")
    started = time.perf_counter()
    git = ["git", "--no-optional-locks", "-C", str(root)]
    checkpoint = subprocess.check_output(
        [*git, "rev-parse", "refs/heads/recovery/d058976"], text=True
    ).strip()
    if checkpoint != BASELINE:
        parser.error("immutable recovery checkpoint differs")
    manifest = json.loads(args.manifest.read_text())
    counts = Counter()
    mismatch = []
    rows = []
    for row in manifest["files"]:
        path = root / row["path"]
        expected = row["current_sha256"]
        actual = sha256(path) if path.is_file() else None
        counts[row["status"]] += 1
        if actual != expected:
            mismatch.append(row["path"])
        rows.append({"path": row["path"], "status": row["status"], "sha256": actual})
    calls = []
    fixtures = []
    syntax_errors = []
    python_count = 0
    for parent in [root / "src", root / "tests"]:
        for path in sorted(parent.rglob("*.py")):
            python_count += 1
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError as exc:
                syntax_errors.append({"path": str(path.relative_to(root)), "line": exc.lineno})
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = (
                        node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else node.func.id
                        if isinstance(node.func, ast.Name)
                        else None
                    )
                    if name in EXPENSIVE_CALLS:
                        calls.append(
                            {
                                "path": str(path.relative_to(root)),
                                "line": node.lineno,
                                "operation": name,
                            }
                        )
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        target = decorator.func if isinstance(decorator, ast.Call) else decorator
                        if isinstance(target, ast.Attribute) and target.attr == "fixture":
                            scope = "function"
                            if isinstance(decorator, ast.Call):
                                for keyword in decorator.keywords:
                                    if keyword.arg == "scope" and isinstance(
                                        keyword.value, ast.Constant
                                    ):
                                        scope = keyword.value.value
                            fixtures.append(
                                {
                                    "path": str(path.relative_to(root)),
                                    "line": node.lineno,
                                    "name": node.name,
                                    "scope": scope,
                                }
                            )
    missing = [r["path"] for r in rows if r["status"] == "MISSING_OR_PARTIAL_CONTENT"]
    result = {
        "checkpoint": checkpoint,
        "manifest_sha256": sha256(args.manifest),
        "manifest_paths": len(rows),
        "classification_counts": dict(counts),
        "manifest_hash_mismatches": mismatch,
        "file_audit": rows,
        "missing_goldens": missing,
        "original_tested_tree_equivalence": "UNPROVED",
        "python_version": sys.version.split()[0],
        "python_files_parsed": python_count,
        "syntax_errors": syntax_errors,
        "static_call_sites": calls,
        "static_call_site_counts": dict(Counter(c["operation"] for c in calls)),
        "fixture_definitions": fixtures,
        "elapsed_seconds": time.perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "measurement_scope": (
            "stdlib-only integrity/AST scan; NOT report execution, fixture profiling "
            "or functional tests"
        ),
        "application_imports": False,
        "tests_run": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "checkpoint",
                    "manifest_paths",
                    "classification_counts",
                    "manifest_hash_mismatches",
                    "python_files_parsed",
                    "syntax_errors",
                    "static_call_site_counts",
                    "elapsed_seconds",
                    "peak_rss_bytes",
                    "measurement_scope",
                    "tests_run",
                ]
            },
            indent=2,
        )
    )
    return 1 if mismatch or syntax_errors or len(rows) != 518 else 0


if __name__ == "__main__":
    raise SystemExit(main())

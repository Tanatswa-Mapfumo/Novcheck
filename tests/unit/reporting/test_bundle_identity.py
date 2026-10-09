"""Cross-process native report-input identity; subprocesses never use live network."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_NATIVE_BUILD = """
import asyncio, json, sys
from pathlib import Path
from pytest_socket import disable_socket
from tests.integration.test_phase8_slice import _run_real_slice
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
from novelty_harness.reporting.execution import ReportCompilationConfiguration
from novelty_harness.reporting.models import ReportOptions
from novelty_harness.reporting.plan import build_coverage_plan

disable_socket(allow_unix_socket=True)
async def build():
    result, sink = await _run_real_slice(Path(sys.argv[1]))
    assessment_id = result.record.assessment_id
    adjudication_id = result.adjudication.adjudication_id
    source = result.run_dir / 'phase5/evidence_graph.sqlite3'
    del result, sink
    repository = SqlAlchemyEvidenceGraphRepository(source)
    try:
        bundle = repository.load_report_input_bundle(assessment_id, adjudication_id=adjudication_id)
        record = repository.begin_report_compilation(
            assessment_id, adjudication_id=adjudication_id, options=ReportOptions(),
            configuration=ReportCompilationConfiguration(), attempt_token='hash-seed-replay',
        )
        plan = build_coverage_plan(bundle, record)
        artifact = make_report_artifact(record, ReportArtifactKind.PLAN, plan,
                                       method_version='p8-plan-firewall-v1')
        repository.record_report_artifact(record.compilation_id, artifact)
        print(json.dumps({'assessment_id': assessment_id, 'adjudication_id': adjudication_id,
                          'compilation_id': record.compilation_id, 'source': str(source)}))
    finally:
        repository.close()
asyncio.run(build())
"""


_NATIVE_RELOAD = """
import json, sys
from pathlib import Path
from pytest_socket import disable_socket
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.reporting.execution import bundle_policy_version
from novelty_harness.evidence.graph.report_store import load_report_compilation_in_session
from sqlalchemy.orm import Session

disable_socket(allow_unix_socket=True)
repository = SqlAlchemyEvidenceGraphRepository(Path(sys.argv[1]))
try:
    frozen = repository.load_frozen_adjudication(sys.argv[2], adjudication_id=sys.argv[3])
    bundle = repository.load_report_input_bundle(sys.argv[2], adjudication_id=sys.argv[3])
    assert bundle.frozen_adjudication == frozen
    with Session(repository.engine) as session:
        session.connection().exec_driver_sql('BEGIN')
        record = load_report_compilation_in_session(session, sys.argv[4])
        session.commit()
    assert bundle_policy_version(record.configuration) == bundle.bundle_version == 'p8-bundle-v2'
    replay = repository.begin_report_compilation(
        sys.argv[2], adjudication_id=sys.argv[3], options=record.options,
        configuration=record.configuration, attempt_token=record.attempt_token,
    )
    assert replay == record
    artifacts = repository.load_report_artifacts(record.compilation_id)
    assert len(artifacts) == 2 and {a.kind.value for a in artifacts} == {'STATUS', 'PLAN'}
    print(json.dumps({
        'scope': bundle.scope.model_dump(mode='json'),
        'bundle_digest': bundle.bundle_digest,
        'canonical_native_projection': canonical_hash(
            bundle.model_dump(mode='python', exclude={'bundle_digest'})
        ),
        'frozen_digest': canonical_hash(frozen),
        'obligation_count': len(bundle.coverage_obligations),
        'compilation_id': record.compilation_id,
        'artifact_ids': sorted(a.artifact_id for a in artifacts),
    }))
finally:
    repository.close()
"""


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_real_native_bundle_digest_is_stable_across_process_hash_seeds(tmp_path):
    build = subprocess.run(
        [sys.executable, "-B", "-c", _NATIVE_BUILD, str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    )
    metadata = json.loads(build.stdout)
    source = Path(metadata["source"])
    source.relative_to(tmp_path)
    assessment_id = metadata["assessment_id"]
    adjudication_id = metadata["adjudication_id"]
    compilation_id = metadata["compilation_id"]
    sidecars = tuple(
        source.with_name(source.name + suffix) for suffix in ("-wal", "-shm", "-journal")
    )
    assert not any(path.exists() for path in sidecars)
    before = _file_digest(source)
    observations = []
    for seed in ("1", "2"):
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                _NATIVE_RELOAD,
                str(source),
                assessment_id,
                adjudication_id,
                compilation_id,
            ],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        observations.append(json.loads(child.stdout))
        assert _file_digest(source) == before
        assert not any(path.exists() for path in sidecars)
    first, second = observations
    assert first["scope"] == second["scope"]
    assert first["scope"]["assessment_id"] == assessment_id
    assert first["scope"]["adjudication_id"] == adjudication_id
    assert first["compilation_id"] == second["compilation_id"] == compilation_id
    assert first["artifact_ids"] == second["artifact_ids"]
    assert first["frozen_digest"] == second["frozen_digest"]
    assert first["canonical_native_projection"] == second["canonical_native_projection"]
    assert first["obligation_count"] == second["obligation_count"] > 0
    assert first["bundle_digest"] == second["bundle_digest"]

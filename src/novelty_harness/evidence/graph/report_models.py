"""Exactly four additive schema v9 report tables on the shared SQLite engine."""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from novelty_harness.evidence.graph.sqlalchemy_models import Base

_COMPILATION_SCOPE = [
    "compilation_id",
    "assessment_id",
    "adjudication_id",
    "context_id",
    "snapshot_id",
]
_SCOPE_PARENT = [f"report_compilations.{column}" for column in _COMPILATION_SCOPE]


class ReportCompilationRow(Base):
    __tablename__ = "report_compilations"
    __table_args__ = (
        UniqueConstraint("compilation_key", "attempt_token"),
        UniqueConstraint(*_COMPILATION_SCOPE),
    )
    compilation_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    compilation_key: Mapped[str] = mapped_column(String(512), nullable=False)
    attempt_token: Mapped[str] = mapped_column(String(512), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    adjudication_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_frozen_manifests.adjudication_id"), nullable=False
    )
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    bundle_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    options_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    configuration_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class ReportArtifactRow(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (ForeignKeyConstraint(_COMPILATION_SCOPE, _SCOPE_PARENT),)
    artifact_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    compilation_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("report_compilations.compilation_id"), nullable=False, index=True
    )
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    adjudication_id: Mapped[str] = mapped_column(String(512), nullable=False)
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cluster_origin_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    execution_artifact_id: Mapped[str | None] = mapped_column(
        String(512), ForeignKey("report_artifacts.artifact_id"), nullable=True
    )
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class CompiledReportRow(Base):
    __tablename__ = "compiled_reports"
    __table_args__ = (ForeignKeyConstraint(_COMPILATION_SCOPE, _SCOPE_PARENT),)
    report_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    compilation_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("report_compilations.compilation_id"), nullable=False, unique=True
    )
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    adjudication_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_frozen_manifests.adjudication_id"), nullable=False
    )
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    bundle_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    ir_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ReportDependencyRow(Base):
    __tablename__ = "report_dependencies"
    __table_args__ = (
        CheckConstraint(
            "(dependency_kind='UPSTREAM' AND upstream_kind IS NOT NULL "
            "AND native_id IS NOT NULL AND path_json IS NOT NULL AND scope_json IS NOT NULL "
            "AND report_artifact_id IS NULL) OR "
            "(dependency_kind='REPORT_ARTIFACT' AND report_artifact_id IS NOT NULL "
            "AND dependency_id=report_artifact_id AND upstream_kind IS NULL "
            "AND native_id IS NULL AND path_json IS NULL AND scope_json IS NULL)",
            name="report_dependency_exact_arm",
        ),
    )
    report_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("compiled_reports.report_id"), primary_key=True
    )
    dependency_kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    dependency_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    expected_digest: Mapped[str] = mapped_column(String(512), nullable=False)
    upstream_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    native_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    path_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_artifact_id: Mapped[str | None] = mapped_column(
        String(512), ForeignKey("report_artifacts.artifact_id"), nullable=True
    )
    document_json: Mapped[str] = mapped_column(Text, nullable=False)

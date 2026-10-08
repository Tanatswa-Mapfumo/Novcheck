"""Additive schema v8 rows in the existing evidence graph database."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from novelty_harness.evidence.graph.sqlalchemy_models import Base


class Phase7InputManifestRow(Base):
    __tablename__ = "phase7_input_manifests"
    __table_args__ = (UniqueConstraint("manifest_id", "assessment_id"),)

    manifest_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7AssessmentContextRow(Base):
    __tablename__ = "phase7_assessment_contexts"
    __table_args__ = (
        UniqueConstraint("context_id", "assessment_id", "snapshot_id"),
        ForeignKeyConstraint(
            ["snapshot_id", "assessment_id"],
            [
                "phase6_assessment_snapshots.snapshot_id",
                "phase6_assessment_snapshots.assessment_id",
            ],
        ),
        ForeignKeyConstraint(
            ["manifest_id", "assessment_id"],
            ["phase7_input_manifests.manifest_id", "phase7_input_manifests.assessment_id"],
        ),
    )

    context_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest_id: Mapped[str] = mapped_column(String(512), nullable=False)
    parent_context_id: Mapped[str | None] = mapped_column(
        String(512), ForeignKey("phase7_assessment_contexts.context_id"), nullable=True
    )
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7RunRow(Base):
    __tablename__ = "phase7_runs"
    __table_args__ = (
        UniqueConstraint("context_id", "attempt_token"),
        ForeignKeyConstraint(
            ["context_id", "assessment_id", "snapshot_id"],
            [
                "phase7_assessment_contexts.context_id",
                "phase7_assessment_contexts.assessment_id",
                "phase7_assessment_contexts.snapshot_id",
            ],
        ),
    )

    run_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    attempt_token: Mapped[str] = mapped_column(String(512), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7RunTransitionRow(Base):
    __tablename__ = "phase7_run_transitions"

    transition_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_runs.run_id"), nullable=False, index=True
    )
    predecessor_id: Mapped[str | None] = mapped_column(
        String(512), ForeignKey("phase7_run_transitions.transition_id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7ArtifactRow(Base):
    __tablename__ = "phase7_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_id", "assessment_id", "snapshot_id"],
            [
                "phase7_assessment_contexts.context_id",
                "phase7_assessment_contexts.assessment_id",
                "phase7_assessment_contexts.snapshot_id",
            ],
        ),
    )

    artifact_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_runs.run_id"), nullable=False, index=True
    )
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7QualificationRefRow(Base):
    __tablename__ = "phase7_qualification_refs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_id", "assessment_id", "snapshot_id"],
            [
                "phase7_assessment_contexts.context_id",
                "phase7_assessment_contexts.assessment_id",
                "phase7_assessment_contexts.snapshot_id",
            ],
        ),
    )

    qualification_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7FrozenManifestRow(Base):
    __tablename__ = "phase7_frozen_manifests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_id", "assessment_id", "snapshot_id"],
            [
                "phase7_assessment_contexts.context_id",
                "phase7_assessment_contexts.assessment_id",
                "phase7_assessment_contexts.snapshot_id",
            ],
        ),
    )

    adjudication_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_runs.run_id"), nullable=False, unique=True
    )
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(512), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(512), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)


class Phase7FrozenDependencyRow(Base):
    __tablename__ = "phase7_frozen_dependencies"

    adjudication_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_frozen_manifests.adjudication_id"), primary_key=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(512), ForeignKey("phase7_artifacts.artifact_id"), primary_key=True
    )

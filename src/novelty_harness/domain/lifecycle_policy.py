"""One transition policy for both operations and serialized lifecycle artifacts."""

from novelty_harness.domain.enums import AssessmentStage, AssessmentStatus

_STAGES = tuple(AssessmentStage)
REPORTABLE_STATUSES = frozenset(
    {
        AssessmentStatus.ACTIVE,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.ABSTAINED,
    }
)
_STATUS_TARGETS: dict[AssessmentStatus, set[AssessmentStatus]] = {
    AssessmentStatus.ACTIVE: {
        AssessmentStatus.PARTIAL,
        AssessmentStatus.ABSTAINED,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.PARTIAL: {
        AssessmentStatus.ACTIVE,
        AssessmentStatus.ABSTAINED,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.ABSTAINED: {
        AssessmentStatus.ACTIVE,
        AssessmentStatus.PARTIAL,
        AssessmentStatus.BLOCKED,
        AssessmentStatus.FAILED,
    },
    AssessmentStatus.BLOCKED: {AssessmentStatus.ACTIVE, AssessmentStatus.FAILED},
    AssessmentStatus.FAILED: set(),
    AssessmentStatus.COMPLETED: set(),
}


def can_advance_stage(current: AssessmentStage, target: AssessmentStage) -> bool:
    return _STAGES.index(target) == _STAGES.index(current) + 1


def can_change_status(current: AssessmentStatus, target: AssessmentStatus) -> bool:
    return target in _STATUS_TARGETS[current]

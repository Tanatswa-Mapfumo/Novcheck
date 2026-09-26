from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import VerdictState
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import AssessmentId

CANONICAL_QUESTIONS = (
    "What exactly is being proposed?",
    "What already exists that is closest?",
    "Which parts are already established?",
    "Where does novelty appear to live?",
    "What is the strongest evidence against the novelty claim?",
    "Does the remaining difference create a meaningful advantage?",
    "What would need to be demonstrated?",
    "What can defensibly be claimed today?",
    "What remains uncertain or insufficiently researched?",
)


class ReportAnswers(ContractModel):
    model_config = ConfigDict(frozen=True)
    q1: NonBlankText
    q2: NonBlankText
    q3: NonBlankText
    q4: NonBlankText
    q5: NonBlankText
    q6: NonBlankText
    q7: NonBlankText
    q8: NonBlankText
    q9: NonBlankText


class CompiledReport(ContractModel):
    model_config = ConfigDict(frozen=True)
    assessment_id: AssessmentId
    adjudication_hash: NonBlankText
    overall_verdict: VerdictState
    answers: ReportAnswers
    markdown: NonBlankText
    provenance: ArtifactProvenance

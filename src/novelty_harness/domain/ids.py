from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

AssessmentId = Annotated[str, StringConstraints(pattern=r"^asm_[^\s]+$")]
IdeaId = Annotated[str, StringConstraints(pattern=r"^idea_[^\s]+$")]
MCUId = Annotated[str, StringConstraints(pattern=r"^mcu_[^\s]+$")]
SourceId = Annotated[str, StringConstraints(pattern=r"^src_[^\s]+$")]
SourceVersionId = Annotated[str, StringConstraints(pattern=r"^srcv_[^\s]+$")]
PassageId = Annotated[str, StringConstraints(pattern=r"^pass_[^\s]+$")]
EvidenceEdgeId = Annotated[str, StringConstraints(pattern=r"^edge_[^\s]+$")]
ProvenanceEdgeId = Annotated[str, StringConstraints(pattern=r"^prov_[^\s]+$")]
LineageClusterId = Annotated[str, StringConstraints(pattern=r"^lin_[^\s]+$")]
QueryId = Annotated[str, StringConstraints(pattern=r"^qry_[^\s]+$")]
SearchRunId = Annotated[str, StringConstraints(pattern=r"^run_[^\s]+$")]
TraceEventId = Annotated[str, StringConstraints(pattern=r"^trace_[^\s]+$")]
LifecycleEventId = Annotated[str, StringConstraints(pattern=r"^life_[^\s]+$")]


def new_assessment_id() -> AssessmentId:
    return "asm_" + uuid4().hex


def new_idea_id() -> IdeaId:
    return "idea_" + uuid4().hex


def new_mcu_id() -> MCUId:
    return "mcu_" + uuid4().hex


def new_source_id() -> SourceId:
    return "src_" + uuid4().hex


def new_passage_id() -> PassageId:
    return "pass_" + uuid4().hex


def new_evidence_edge_id() -> EvidenceEdgeId:
    return "edge_" + uuid4().hex


def new_query_id() -> QueryId:
    return "qry_" + uuid4().hex


def new_search_run_id() -> SearchRunId:
    return "run_" + uuid4().hex


def new_trace_event_id() -> TraceEventId:
    return "trace_" + uuid4().hex


def new_lifecycle_event_id() -> LifecycleEventId:
    return "life_" + uuid4().hex

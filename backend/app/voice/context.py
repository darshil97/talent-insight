"""Interviewer context from server-owned job data and verified assessment results."""

from app.api.jobs import JobDetail
from app.pipeline.contracts import CATEGORIES, Assessment, Status
from app.voice.contracts import ContextFact, InterviewContext, Topic, VoiceFailure
from app.voice.envelope import EnvelopePayload

# Probe weak or missing evidence first; confirm strong evidence only if time remains.
STATUS_ORDER: dict[Status, int] = {
    "unknown": 0,
    "partial": 1,
    "transferable": 2,
    "not_met": 3,
    "met": 4,
}
MAX_PROMPT_FACTS = 20


def _context(
    job: JobDetail,
    kind: str,
    statuses: dict[str, Status] | None,
    facts: list[ContextFact],
) -> InterviewContext:
    seeds: dict[str, str] = {}
    for question in job.questions:
        for requirement_id in question.requirement_ids:
            seeds.setdefault(requirement_id, question.text)
    known = statuses or {}
    topics = [
        Topic(
            requirement_id=requirement.id,
            category=requirement.category,
            description=requirement.description,
            status=known.get(requirement.id, "unknown"),
            question=seeds.get(requirement.id),
        )
        for requirement in sorted(job.requirements, key=lambda item: item.sort_order)
    ]
    # Stable sort keeps the authored requirement order within each status and category.
    topics.sort(key=lambda topic: (STATUS_ORDER[topic.status], CATEGORIES.index(topic.category)))
    return InterviewContext(
        job_id=job.id,
        job_title=job.title,
        candidate_kind=kind,
        assessment_available=statuses is not None,
        topics=topics,
        facts=facts[:MAX_PROMPT_FACTS],
    )


def demo_context(job: JobDetail, assessment: Assessment | None) -> InterviewContext:
    """A missing or stale snapshot still allows a screening, with every topic unknown."""
    if assessment is None:
        return _context(job, "demo", None, [])
    return _context(
        job,
        "demo",
        {item.requirement_id: item.status for item in assessment.judgments},
        [ContextFact(kind=fact.kind, value=fact.value) for fact in assessment.structured.facts],
    )


def upload_context(job: JobDetail, payload: EnvelopePayload) -> InterviewContext:
    requirement_ids = {requirement.id for requirement in job.requirements}
    judged = [item.requirement_id for item in payload.judgments]
    if len(set(judged)) != len(judged) or not set(judged) <= requirement_ids:
        raise VoiceFailure("invalid_screening_context")
    return _context(
        job,
        "upload",
        {item.requirement_id: item.status for item in payload.judgments},
        payload.facts,
    )

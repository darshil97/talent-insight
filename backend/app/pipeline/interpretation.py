"""Evidence-linked requirement interpretation; invalid judgments become unknown, never matches."""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from app.config import Settings
from app.llm.base import get_provider
from app.llm.factory import MOCK_MODE
from app.llm.invoke import invoke_structured
from app.pipeline.attempts import Outcome, run_attempts
from app.pipeline.contracts import (
    MAX_CITATIONS,
    MAX_FACTS,
    MAX_QUOTE_CHARACTERS,
    MAX_QUOTES_PER_FACT,
    MAX_REASON_CHARACTERS,
    MAX_VALUE_CHARACTERS,
    STATUSES,
    ExtractionFailure,
    Interpretation,
    InterpretationOutput,
    Judgment,
    StructuredResume,
    VerifiedFact,
    provider_json_schema,
)
from app.pipeline.evidence import salvage_facts
from app.prompts.loader import load_prompt

logger = logging.getLogger(__name__)
REVIEW_REASON = "Requires review of source meaning and requirement fit."
UNVERIFIED_REASON = "No verifiable model judgment was returned; review the source manually."
MISSING_REASON = (
    "The cited text only says this information is missing; verify it with the candidate."
)
# A line saying information is missing is not contrary evidence, so it cannot support not_met.
MISSING_INFORMATION = re.compile(
    r"\bnot\s+(?:stated|described|provided|specified|documented|mentioned|listed)\b", re.IGNORECASE
)
# Issues that forced a requirement to unknown, as opposed to tidy-ups of a usable judgment.
FORCED_UNKNOWN = {"missing_judgment", "conflicting_judgments", "uncited_judgment"}


@dataclass
class JudgmentSalvage:
    interpretation: Interpretation
    returned: int
    issues: list[str] = field(default_factory=list)
    # Verified mentions plus any resume quotes the judging step added and the backend verified.
    facts: list[VerifiedFact] = field(default_factory=list)
    added: int = 0

    @property
    def forced_unknown(self) -> int:
        return sum(1 for issue in self.issues if issue.rpartition(": ")[2] in FORCED_UNKNOWN)

    def counts(self) -> dict[str, int]:
        return dict(Counter(issue.rpartition(": ")[2] for issue in self.issues))


def _add_evidence(
    row: dict, label: str, facts: list[VerifiedFact], structured: StructuredResume, issues: list
) -> list[int]:
    """Verify resume quotes the model added; return indices of the matching verified facts."""
    added = row.get("new_evidence")
    if not isinstance(added, list):
        return []
    indices = []
    for position, item in enumerate(added[:MAX_QUOTES_PER_FACT]):
        result = salvage_facts({"facts": [item]}, structured.source)
        prefix = f"{label}.new_evidence[{position}]"
        issues.extend(prefix + issue.removeprefix("facts[0]") for issue in result.issues)
        for fact in result.facts:
            key = (fact.kind, fact.value.casefold())
            match = next(
                (i for i, known in enumerate(facts) if (known.kind, known.value.casefold()) == key),
                None,
            )
            if match is None and len(facts) < MAX_FACTS:
                facts.append(fact)
                match = len(facts) - 1
            if match is not None:
                indices.append(match)
    return indices


def _candidate(
    row: dict,
    facts: list[VerifiedFact],
    fact_count: int,
    added: list[int],
    label: str,
    issues: list,
) -> Judgment | None:
    status, indices, reason = row.get("status"), row.get("fact_indices", []), row.get("reason")
    if status not in STATUSES or not isinstance(indices, list) or not isinstance(reason, str):
        issues.append(f"{label}: invalid_judgment")
        return None
    valid = list(
        dict.fromkeys(
            [index for index in indices if type(index) is int and 0 <= index < fact_count] + added
        )
    )
    if len(valid) != len(set(indices) | set(added)):
        issues.append(f"{label}: invalid_fact_index")
    if len(valid) > MAX_CITATIONS:
        issues.append(f"{label}: too_many_citations")
        valid = valid[:MAX_CITATIONS]
    reason = reason.strip() or REVIEW_REASON
    if len(reason) > MAX_REASON_CHARACTERS:
        issues.append(f"{label}: reason_too_long")
        reason = reason[: MAX_REASON_CHARACTERS - 1].rstrip() + "…"
    if (
        status == "not_met"
        and valid
        and all(
            all(MISSING_INFORMATION.search(item.quote) for item in facts[index].evidence)
            for index in valid
        )
    ):
        issues.append(f"{label}: missing_information_not_contrary")
        return Judgment(
            requirement_id=row["requirement_id"],
            status="unknown",
            fact_indices=[],
            reason=MISSING_REASON,
        )
    if status == "unknown":
        valid = []
    elif not valid:
        issues.append(f"{label}: uncited_judgment")
        return Judgment(
            requirement_id=row["requirement_id"],
            status="unknown",
            fact_indices=[],
            reason=UNVERIFIED_REASON,
        )
    return Judgment(
        requirement_id=row["requirement_id"], status=status, fact_indices=valid, reason=reason
    )


def salvage_judgments(value: object, structured: StructuredResume) -> JudgmentSalvage:
    """One judgment per canonical requirement, in job order, citing only verified facts."""
    if not isinstance(value, dict) or not isinstance(value.get("judgments"), list):
        raise ExtractionFailure(
            "invalid_model_output",
            retryable=True,
            issues=("response: return one JSON object whose only property is a judgments array",),
        )
    rows = value["judgments"]
    requirement_ids = [row.id for row in structured.job.requirements]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ExtractionFailure("invalid_interpretation")
    issues: list[str] = []
    facts = list(structured.facts)
    candidates: dict[str, list[Judgment]] = {key: [] for key in requirement_ids}
    for index, row in enumerate(rows):
        label = f"judgments[{index}]"
        if not isinstance(row, dict) or not isinstance(row.get("requirement_id"), str):
            issues.append(f"{label}: invalid_judgment")
        elif row["requirement_id"] not in candidates:
            issues.append(f"{label}: unknown_requirement")
        else:
            added = _add_evidence(row, label, facts, structured, issues)
            judgment = _candidate(row, facts, len(structured.facts), added, label, issues)
            if judgment is not None:
                candidates[row["requirement_id"]].append(judgment)
    judgments = []
    for requirement_id in requirement_ids:
        found = candidates[requirement_id]
        distinct = {(row.status, tuple(row.fact_indices)) for row in found}
        if len(distinct) == 1:
            judgments.append(found[0])
            continue
        issues.append(
            f"requirement {requirement_id}: "
            + ("missing_judgment" if not found else "conflicting_judgments")
        )
        judgments.append(
            Judgment(
                requirement_id=requirement_id,
                status="unknown",
                fact_indices=[],
                reason=UNVERIFIED_REASON,
            )
        )
    return JudgmentSalvage(
        interpretation=Interpretation(judgments=judgments),
        returned=len(rows),
        issues=issues,
        facts=facts,
        added=len(facts) - len(structured.facts),
    )


def mock_interpretation(structured: StructuredResume) -> Interpretation:
    """Mock extraction cannot establish criterion satisfaction from word mentions."""
    return Interpretation(
        judgments=[
            Judgment(requirement_id=row.id, status="unknown", fact_indices=[], reason=REVIEW_REASON)
            for row in structured.job.requirements
        ]
    )


def interpretation_prompt(
    settings: Settings, structured: StructuredResume, issues: tuple[str, ...] = ()
) -> str:
    return load_prompt(
        "interpretation",
        "system",
        with_mentions=True,
        fact_count=len(structured.facts),
        max_citations=MAX_CITATIONS,
        max_reason=MAX_REASON_CHARACTERS,
        max_quotes=MAX_QUOTES_PER_FACT,
        max_value=MAX_VALUE_CHARACTERS,
        max_quote=MAX_QUOTE_CHARACTERS,
        method=get_provider(settings.ai_mode).structured_method(settings),
        output_name="Interpretation",
        schema_json=json.dumps(provider_json_schema(InterpretationOutput), ensure_ascii=False),
        issues=list(issues),
    )


def interpretation_payload(structured: StructuredResume) -> str:
    return json.dumps(
        {
            "job_context": structured.job.model_dump(),
            "untrusted_resume_pages": [page.model_dump() for page in structured.source.pages],
            "verified_text_mentions": [fact.model_dump() for fact in structured.facts],
        },
        ensure_ascii=False,
    )


async def _interpret_once(
    structured: StructuredResume, settings: Settings, attempt: int, issues: tuple[str, ...]
) -> Outcome[tuple[Interpretation, list[VerifiedFact]]]:
    value = await invoke_structured(
        settings,
        stage="interpretation",
        attempt=attempt,
        system=interpretation_prompt(settings, structured, issues),
        payload=interpretation_payload(structured),
        schema=provider_json_schema(InterpretationOutput),
        output_name="Interpretation",
        root_key="judgments",
    )
    result = salvage_judgments(value, structured)
    if result.issues or result.added:
        logger.info(
            "interpretation attempt %d: %d verified resume quotes added; "
            "%d of %d requirements forced to unknown; issues %s",
            attempt,
            result.added,
            result.forced_unknown,
            len(structured.job.requirements),
            result.counts(),
        )
    # Retry only when the model failed for most requirements; otherwise unknown is honest.
    retry = (
        tuple(result.issues) if result.forced_unknown * 2 > len(structured.job.requirements) else ()
    )
    return Outcome(
        (result.interpretation, result.facts), quality=-result.forced_unknown, retry_issues=retry
    )


async def interpret_resume(
    structured: StructuredResume, settings: Settings
) -> tuple[Interpretation, list[VerifiedFact]]:
    """Judgments plus the verified facts they cite, including any resume quotes added here."""
    if settings.ai_mode == MOCK_MODE:
        return mock_interpretation(structured), list(structured.facts)
    if len(interpretation_payload(structured)) > settings.ai_max_input_characters:
        raise ExtractionFailure("ai_input_too_large")
    return await run_attempts(
        "interpretation",
        settings,
        lambda attempt, issues: _interpret_once(structured, settings, attempt, issues),
    )

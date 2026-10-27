"""Source verification: a model quote becomes an exact source span or is rejected.

Quotes are located after normalizing whitespace runs, compatibility characters (ligatures,
non-breaking spaces) and typographic quotes/dashes, because PDF text and model output differ
there. The stored quote is always the original source substring at the computed offsets.
"""

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from app.pipeline.contracts import (
    FACT_KINDS,
    MAX_FACTS,
    MAX_NAME_CHARACTERS,
    MAX_QUOTE_CHARACTERS,
    MAX_QUOTES_PER_FACT,
    MAX_TITLE_CHARACTERS,
    MAX_VALUE_CHARACTERS,
    CandidateIdentity,
    ExtractionFailure,
    ExtractionSource,
    StructuredResume,
    VerifiedEvidence,
    VerifiedFact,
    VerifiedText,
    word_pattern,
)

_TYPOGRAPHY = str.maketrans(
    {
        **dict.fromkeys("‘’‚‛′", "'"),
        **dict.fromkeys("“”„‟″", '"'),
        **dict.fromkeys("‐‑‒–—―−", "-"),
        "­": None,
    }
)
# Issue codes caused by unverifiable output, as opposed to limits on otherwise valid facts.
VERIFICATION_FAILURES = {
    "invalid_fact",
    "value_too_long",
    "no_verified_quote",
    "value_not_in_quote",
}


def _normalize(text: str) -> tuple[str, list[int]]:
    """Comparable text plus the source code-point index of every normalized character."""
    chars: list[str] = []
    origin: list[int] = []
    space_at = None
    for index, char in enumerate(text):
        for item in unicodedata.normalize("NFKD", char).translate(_TYPOGRAPHY):
            if item.isspace():
                if space_at is None:
                    space_at = index
                continue
            if space_at is not None and chars:
                chars.append(" ")
                origin.append(space_at)
            space_at = None
            chars.append(item)
            origin.append(index)
    return "".join(chars), origin


def locate_quote(text: str, quote: str, *, unique: bool = True) -> tuple[int, int] | str:
    """Return a source span for the quote (unique unless disabled), or an issue code."""
    start = text.find(quote)
    if start >= 0:
        if unique and text.find(quote, start + 1) >= 0:
            return "quote_ambiguous"
        return start, start + len(quote)
    needle, _ = _normalize(quote)
    haystack, origin = _normalize(text)
    if not needle:
        return "quote_not_found"
    found = haystack.find(needle)
    if found < 0:
        return "quote_not_found"
    if unique and haystack.find(needle, found + 1) >= 0:
        return "quote_ambiguous"
    return origin[found], origin[found + len(needle) - 1] + 1


def value_in_quote(value: str, quote: str) -> bool:
    return bool(word_pattern(_normalize(value)[0]).search(_normalize(quote)[0]))


@dataclass
class FactSalvage:
    """Verified facts plus server-written issue codes for everything that was dropped."""

    facts: list[VerifiedFact]
    returned: int
    issues: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(1 for issue in self.issues if issue.split(": ", 1)[-1] in VERIFICATION_FAILURES)

    def counts(self) -> dict[str, int]:
        return dict(Counter(issue.split(": ", 1)[-1] for issue in self.issues))


def _citation(raw: object, source: ExtractionSource) -> VerifiedEvidence | str:
    if not isinstance(raw, dict):
        return "invalid_citation"
    page_number, quote = raw.get("page_number"), raw.get("quote")
    if type(page_number) is not int or not isinstance(quote, str) or not quote.strip():
        return "invalid_citation"
    if not 1 <= page_number <= len(source.pages):
        return "page_out_of_range"
    if len(quote) > MAX_QUOTE_CHARACTERS:
        return "quote_too_long"
    text = source.pages[page_number - 1].text
    span = locate_quote(text, quote)
    if isinstance(span, str):
        return span
    start, end = span
    return VerifiedEvidence(page_number=page_number, quote=text[start:end], start=start, end=end)


def salvage_facts(value: object, source: ExtractionSource) -> FactSalvage:
    """Keep each fact whose value and quotes verify against the source; drop the rest.

    Only an unusable response shape fails the whole extraction. Dropped facts are never
    repaired into evidence; their categories stay unknown unless another fact verifies.
    """
    if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
        raise ExtractionFailure(
            "invalid_model_output",
            retryable=True,
            issues=("response: return one JSON object whose only property is a facts array",),
        )
    rows = value["facts"]
    result = FactSalvage(facts=[], returned=len(rows))
    seen = set()
    for index, row in enumerate(rows):
        label = f"facts[{index}]"
        if (
            not isinstance(row, dict)
            or row.get("kind") not in FACT_KINDS
            or not isinstance(row.get("value"), str)
            or not row["value"].strip()
            or not isinstance(row.get("evidence"), list)
            or not row["evidence"]
        ):
            result.issues.append(f"{label}: invalid_fact")
            continue
        if len(row["value"]) > MAX_VALUE_CHARACTERS:
            result.issues.append(f"{label}: value_too_long")
            continue
        evidence = []
        for position, raw in enumerate(row["evidence"]):
            if len(evidence) == MAX_QUOTES_PER_FACT:
                result.issues.append(f"{label}: extra_quotes_ignored")
                break
            citation = _citation(raw, source)
            if isinstance(citation, str):
                result.issues.append(f"{label}.evidence[{position}]: {citation}")
            elif all(
                (citation.page_number, citation.start) != (item.page_number, item.start)
                for item in evidence
            ):
                evidence.append(citation)
        if not evidence:
            result.issues.append(f"{label}: no_verified_quote")
            continue
        if not any(value_in_quote(row["value"], item.quote) for item in evidence):
            result.issues.append(f"{label}: value_not_in_quote")
            continue
        key = (row["kind"], row["value"].casefold())
        if key in seen:
            result.issues.append(f"{label}: duplicate_fact")
            continue
        if len(result.facts) == MAX_FACTS:
            result.issues.append(f"{label}: over_fact_limit")
            continue
        seen.add(key)
        result.facts.append(VerifiedFact(kind=row["kind"], value=row["value"], evidence=evidence))
    return result


def _display_text(raw: object, limit: int, source: ExtractionSource) -> VerifiedText | None:
    """First occurrence on any page; a name may repeat in headers, so uniqueness is not needed."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > limit:
        return None
    for page in source.pages:
        span = locate_quote(page.text, raw.strip(), unique=False)
        if not isinstance(span, str):
            start, end = span
            return VerifiedText(
                value=page.text[start:end], page_number=page.page_number, start=start, end=end
            )
    return None


def verify_identity(value: object, source: ExtractionSource) -> CandidateIdentity | None:
    """Keep a name or title only when it occurs in the source; never repaired or inferred."""
    identity = value.get("identity") if isinstance(value, dict) else None
    if not isinstance(identity, dict):
        return None
    result = CandidateIdentity(
        name=_display_text(identity.get("name"), MAX_NAME_CHARACTERS, source),
        current_title=_display_text(identity.get("current_title"), MAX_TITLE_CHARACTERS, source),
    )
    return result if result.name or result.current_title else None


def verify_facts(value: object, source: ExtractionSource) -> list[VerifiedFact]:
    """All-or-nothing verification for trusted inputs such as stored or mock facts."""
    result = salvage_facts(value, source)
    if result.issues:
        raise ExtractionFailure("invalid_evidence")
    return result.facts


def reverify(structured: StructuredResume) -> bool:
    """Stored facts must still map to the identical exact source spans."""
    payload = {
        "facts": [
            {
                "kind": fact.kind,
                "value": fact.value,
                "evidence": [
                    {"page_number": item.page_number, "quote": item.quote} for item in fact.evidence
                ],
            }
            for fact in structured.facts
        ]
    }
    try:
        return verify_facts(payload, structured.source) == structured.facts
    except ExtractionFailure:
        return False

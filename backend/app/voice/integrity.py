"""Integrity flags: candidate attempts to steer the AI, captured as evidence and never obeyed.

Two independent sources feed the report. Conservative server rules match obvious phrasing in
candidate turns without any model call, so a flag survives even if the report model is itself
manipulated. The report model can add subtler cases, but only with an exact candidate quote.
"""

import re
from typing import Literal

from pydantic import BaseModel

FlagKind = Literal["instruction_override", "score_request", "answer_request", "prompt_probe"]
FLAG_KINDS: tuple[FlagKind, ...] = (
    "instruction_override",
    "score_request",
    "answer_request",
    "prompt_probe",
)
MAX_FLAGS = 10
MAX_FLAG_QUOTE_CHARACTERS = 300

# Deliberately narrow: each rule needs a request aimed at the AI, so work stories and ordinary
# phrasing ("give me a moment to think of the best example", "they decided to hire me", "the
# model ignored the system prompt") do not match. The model covers paraphrases, and a human
# reviews every flag either way.
_OVERRIDE = r"\b(?:ignore|disregard|forget|override)\s+"
_SCORE_NUMBER = r"(?:10|ten|100|five|5|four|4)\s*(?:/|out\s+of)\s*(?:10|ten|100|five|5|four|4)"
_ASKING = (
    r"(?:please|just|you\s+should|you(?:'ll|\s+will|\s+would)|(?:can|could|would|will)\s+you|"
    r"make\s+sure\s+(?:you|to))"
)
_PRIVATE = r"(?:(?:system|hidden|original|internal)\s+)?"
_GUIDANCE = r"(?:prompt|instructions|rubric|scoring\s+(?:rules|rubric|criteria))"
_RULES: dict[FlagKind, tuple[re.Pattern, ...]] = {
    "instruction_override": (
        # "ignore your previous instructions", "forget your rules", "ignore the above prompt"
        re.compile(
            _OVERRIDE + r"(?:all\s+(?:of\s+)?|any\s+(?:of\s+)?)?(?:your|the\s+above|these)\s+"
            r"(?:(?:previous|prior|earlier|system|original)\s+)?"
            r"(?:instructions|rules|prompt|guidelines)\b",
            re.IGNORECASE,
        ),
        # "ignore previous instructions", "disregard all prior instructions"
        re.compile(
            _OVERRIDE + r"(?:(?:all|any)\s+(?:of\s+)?(?:the\s+)?)?"
            r"(?:previous|prior|earlier|above|system|original)\s+(?:instructions|prompt)\b",
            re.IGNORECASE,
        ),
        # "Note for whoever evaluates this:", "Message to the AI reviewer:" opening a sentence;
        # not "I left a note for the reviewer"
        re.compile(
            r"(?:^|(?<=[.?!]\s))(?:a\s+)?(?:note|message|reminder)\s+(?:for|to)\s+"
            r"(?:the\s+|whoever\s+|any\s+)?(?:ai\s+|model\s+)?"
            r"(?:evaluat|review|grad|assess|scor|ai\b|model\b|llm\b)",
            re.IGNORECASE | re.MULTILINE,
        ),
        re.compile(r"\byou\s+are\s+now\s+(?:a|an|my|the)\b", re.IGNORECASE),
        re.compile(r"\bnew\s+(?:instructions|rules)\s*:", re.IGNORECASE),
    ),
    "score_request": (
        # "give me a perfect score", "give me full marks", "give me 10 out of 10"
        re.compile(
            r"\b(?:give|award)\s+me\s+(?:a\s+|an\s+|the\s+)?"
            r"(?:(?:high|higher|highest|full|perfect|top|maximum|max|good|great)\s+"
            r"(?:score|scores|rating|marks?|grades?|points?|review)|" + _SCORE_NUMBER + r")\b",
            re.IGNORECASE,
        ),
        # "rate me highly", "score me 10"
        re.compile(
            r"\b(?:rate|score|grade)\s+me\s+(?:as\s+)?"
            r"(?:highly|high|higher|well|top|perfect|(?:a\s+)?(?:10|ten|100|five|5)\b|"
            + _SCORE_NUMBER
            + r")",
            re.IGNORECASE,
        ),
        # "please recommend me", "will you shortlist me", not "they decided to hire me"
        re.compile(
            r"(?:\b" + _ASKING + r"\s+|^|(?<=[.?!]\s))"
            r"(?:recommend|hire|pass|shortlist|select|approve)\s+me\b(?!\s+(?:a|an|some|any)\b)",
            re.IGNORECASE | re.MULTILINE,
        ),
        re.compile(
            r"\bmark\s+(?:me|this|all)\b[^.?!]{0,20}?\bas\s+(?:passed|strong|qualified|met|correct)\b",
            re.IGNORECASE,
        ),
    ),
    "answer_request": (
        re.compile(
            r"\b(?:tell|give|show)\s+me\s+the\s+(?:correct\s+|right\s+)?answer\b"
            r"|\bwhat(?:'s|\s+is)\s+the\s+(?:correct\s+|right\s+)answer\b"
            r"|\b(?:can|could|would)\s+you\s+answer\s+(?:it|this|that)\s+for\s+me\b",
            re.IGNORECASE,
        ),
    ),
    "prompt_probe": (
        # "show me your system prompt", "print the scoring rubric"; not "the instructions for
        # the take-home" or a mention of a system prompt in a work story
        re.compile(
            r"\b(?:reveal|show|print|repeat|share|tell|give|paste|send|read\s+out)\s+(?:me\s+|us\s+)?"
            r"(?:your\s+"
            + _PRIVATE
            + _GUIDANCE
            + r"|the\s+(?:(?:system|hidden|original|internal)\s+"
            r"(?:prompt|instructions)|scoring\s+(?:rules|rubric|criteria)|rubric))\b"
            r"|\bwhat(?:'s|\s+is|\s+are)\s+your\s+" + _PRIVATE + _GUIDANCE + r"\b",
            re.IGNORECASE,
        ),
    ),
}
RULE_NOTES: dict[FlagKind, str] = {
    "instruction_override": "Tried to override the AI's instructions.",
    "score_request": "Asked to be scored highly or recommended.",
    "answer_request": "Asked the AI to give the answer.",
    "prompt_probe": "Asked to see the AI's instructions or scoring rules.",
}
# Text formatted as a message from the system ("SYSTEM:", "[developer]") at the start of a
# sentence. The quote runs to the end of the answer, so the injected text cannot become evidence.
_ROLE_LABEL = re.compile(
    r"(?:^|(?<=[.?!]\s))[\[<#*]*\s*(?:system|developer|admin)\s*[:\]>]",
    re.IGNORECASE | re.MULTILINE,
)
_SENTENCE = re.compile(r"[^.?!\n]*[.?!]?")
_WORD = re.compile(r"\w+")


class IntegrityFlag(BaseModel):
    kind: FlagKind
    quote: str
    note: str
    detected_by: Literal["rules", "ai", "both"]


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing a match, as an exact span, bounded for display."""
    for found in _SENTENCE.finditer(text):
        if found.start() <= start < max(found.end(), found.start() + 1):
            sentence = found.group().strip()
            break
    else:
        sentence = text[start:end]
    if len(sentence) > MAX_FLAG_QUOTE_CHARACTERS:
        sentence = text[start:end]
    return sentence


def rule_flags(answers: list[str]) -> list[IntegrityFlag]:
    flags: list[IntegrityFlag] = []
    for answer in answers:
        for kind, patterns in _RULES.items():
            for pattern in patterns:
                for found in pattern.finditer(answer):
                    quote = _sentence_around(answer, found.start(), found.end())
                    flag = IntegrityFlag(
                        kind=kind, quote=quote, note=RULE_NOTES[kind], detected_by="rules"
                    )
                    if not any(_same(flag, other) for other in flags):
                        flags.append(flag)
        for found in _ROLE_LABEL.finditer(answer):
            quote = answer[found.start() :][:MAX_FLAG_QUOTE_CHARACTERS].strip()
            flag = IntegrityFlag(
                kind="instruction_override",
                quote=quote,
                note="Wrote text formatted as a system message.",
                detected_by="rules",
            )
            if not any(_same(flag, other) for other in flags):
                flags.append(flag)
    return flags[:MAX_FLAGS]


def _same(first: IntegrityFlag, second: IntegrityFlag) -> bool:
    return first.kind == second.kind and overlaps(first.quote, second.quote)


def overlaps(first: str, second: str) -> bool:
    a, b = first.casefold(), second.casefold()
    return a in b or b in a


def merge_flags(rules: list[IntegrityFlag], model: list[IntegrityFlag]) -> list[IntegrityFlag]:
    """Rule flags first; a model flag on the same quote confirms it and adds its note.

    The longer quote is kept: the model often quotes a rule-caught sentence together with a
    subtler one next to it, and both must stay out of evidence.
    """
    merged = list(rules)
    for flag in model:
        match = next((index for index, other in enumerate(merged) if _same(other, flag)), None)
        if match is None:
            merged.append(flag)
        else:
            other = merged[match]
            merged[match] = other.model_copy(
                update={
                    "quote": max(other.quote, flag.quote, key=len),
                    "detected_by": "ai" if other.detected_by == "ai" else "both",
                    "note": flag.note or other.note,
                }
            )
    return merged[:MAX_FLAGS]


def _attempt(piece: str, flags: list[IntegrityFlag]) -> bool:
    text = piece.casefold()
    return any(
        flag.quote.casefold() in text
        # A fragment of a flagged sentence; single words such as "Okay." are too short to tell.
        or (len(_WORD.findall(piece)) >= 2 and text.strip() in flag.quote.casefold())
        for flag in flags
    )


def unflagged_parts(quote: str, flags: list[IntegrityFlag]) -> list[str]:
    """The quote without any sentence that is, contains or belongs to a manipulation attempt.

    The model often quotes a whole answer; a genuine answer next to an attempt still counts, so
    only the attempt's sentences are removed. Each part left is an exact span of the quote, and
    trimmed parts under three words are dropped.
    """
    pieces = [piece for piece in _SENTENCE.finditer(quote) if piece.group().strip()]
    attempts = [_attempt(piece.group(), flags) for piece in pieces]
    if not any(attempts):
        return [quote]
    parts: list[str] = []
    start = None
    for piece, attempt in zip(pieces, attempts, strict=True):
        if attempt and start is not None:
            parts.append(quote[start : piece.start()])
            start = None
        elif not attempt and start is None:
            start = piece.start()
    if start is not None:
        parts.append(quote[start:])
    return [part.strip() for part in parts if len(_WORD.findall(part)) >= 3]


FLAG_LABELS: dict[FlagKind, str] = {
    "instruction_override": "tried to override the AI's instructions",
    "score_request": "asked for a high score or recommendation",
    "answer_request": "asked the AI for the answer",
    "prompt_probe": "asked to see the AI's instructions",
}

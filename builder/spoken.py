"""Spoken-text check (F-047): text the agent says word for word must address the customer.

A spec field such as an outcome's ``say`` is spoken by a fixed line. An instruction copied
from a brief ("Thank the customer and say goodbye.") would be read aloud as it is. This
check finds text that talks to the agent instead of the customer. Generic English wording;
it never looks at brief values.
"""

from __future__ import annotations

import re

# Verbs that, opening a sentence, order the agent rather than speak to the customer.
# Customer-facing openers such as "Thank you", "Please ...", "Call us ..." stay allowed.
_AGENT_VERBS = tuple(
    "say|tell|ask|offer|inform|explain|state|mention|read|apologise|apologize|close|end|propose|record|"
    "remind|advise|direct|refer|transfer|acknowledge|greet|introduce|confirm that|let the|make sure|ensure|"
    "do not|never|avoid|use the|thank the|thank them|take no|make no".split("|")
)
_OPENER = re.compile(r"^(?:then |and |also |first |politely |briefly )?(" + "|".join(
    re.escape(verb) for verb in sorted(_AGENT_VERBS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_THIRD_PERSON = re.compile(
    r"\b(?:the|this|that) (?:customer|caller|debtor|client|person|third party)\b"
    r"(?! (?:support|service|services|care|team|centre|center)\b)|\bthe agent\b", re.IGNORECASE)
_TOOLING = re.compile(r"`|\b[a-z]+_[a-z_]+\b|\btool\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


_QUOTED_SPEECH = re.compile(
    r"^(?:then |first )?(?:say|tell (?:them|the customer|the caller)|ask(?: them)?)(?: this| exactly| word for word)?"
    r"\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)


def spoken_words(text: str) -> str:
    """The words to say when ``text`` wraps them in an instruction (Say: "..."); else ``text``."""
    stripped = text.strip()
    match = _QUOTED_SPEECH.match(stripped)
    if not match:
        return stripped
    words = match.group(1).strip()
    if len(words) >= 2 and words[0] in "\"“'" and words[-1] in "\"”'":
        words = words[1:-1].strip()
    return words or stripped


def agent_directed(text: str) -> str:
    """Why ``text`` addresses the agent rather than the customer; "" when it reads as speech."""
    stripped = text.strip().strip('"“”')
    if not stripped:
        return ""
    match = _THIRD_PERSON.search(stripped)
    if match:
        return f"it talks about {match.group(0)!r} instead of to them"
    if _TOOLING.search(stripped):
        return "it names a tool, field or code"
    for sentence in _SENTENCE.split(stripped):
        opener = _OPENER.match(sentence.strip().strip('"“”'))
        if opener:
            return f"it is an instruction to the agent (starts with {opener.group(1)!r})"
    return ""



_QUOTED = re.compile(r"\"([^\"]+)\"|“([^”]+)”")
# F-065 review: a quote is kept only when a speech verb introduces it directly ("Say:", "Tell
# them", "read this") and the quote ends that clause; a negated verb ("do not say") never counts.
_SPEECH_INTRO = re.compile(
    r"(?:^|[\s,;:(])(?:say|tell(?: [a-z]+){0,3}|read(?: out| aloud)?|state|answer)(?: this| exactly| word for word)?"
    r"\s*:?\s*$", re.IGNORECASE)
_NEGATED = re.compile(r"\b(?:not|never|don't|dont|no)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
# After the quote: the clause ends (punctuation, "then"/"and", or a new sentence with a capital).
_CLAUSE_END = re.compile(r"^\s*(?:[.!?;,]|$|(?i:then|and)\b|[A-Z])")
_SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def quoted_speech(text: str, reserved: frozenset[str] | set[str] = frozenset()) -> str:
    """The quoted words a speech verb introduces in an instruction (F-065): ``Say: "X." Then
    thank the customer`` gives "X.". "" (the safe goodbye-only fallback) when any quoted part
    is not clearly speech: not introduced by a speech verb, negated, not ending its clause,
    shorter than three words without end punctuation, a ``reserved`` spec value, or itself
    directed at the agent."""
    kept = []
    for match in _QUOTED.finditer(text):
        words = (match.group(1) or match.group(2) or "").strip()
        before = text[:match.start()]
        clause = re.split(r"[.!?]\s+", before)[-1]
        verb = _SPEECH_INTRO.search(clause)
        if (not words or not verb or _NEGATED.search(clause[:verb.start() + 1])
                or not _CLAUSE_END.match(text[match.end():])
                or (len(words.split()) < 3 and words[-1] not in ".!?")
                or words.strip(".!? ").lower() in {value.lower() for value in reserved}
                or _SNAKE.search(words) or agent_directed(words)):
            return ""
        kept.append(words if words[-1] in ".!?" else words + ".")
    return " ".join(kept)

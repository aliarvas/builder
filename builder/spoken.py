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

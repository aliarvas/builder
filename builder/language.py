"""T-041: the agent speaks the brief's language.

The builder's own customer-facing fixed lines (tts lines and code-built messages) are English
text in ``builder/prompts.py``. For a call in another language they are translated at build time
with one model call, each line checked to keep its placeholders exactly (otherwise the English
line stays), and swapped in while the workflow is rendered. The brief's own quoted lines are
already in its language and are not touched. English is the default and is never changed.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any, Callable, Iterator

from . import prompts
from .prompts import ACCOUNT_WAIT_LINE, PROMPTS, SPOKEN_TABLE_TRANSLATE_SYSTEM, PromptDefinition

ENGLISH = "en"
# Language words a spec may give in agent.language, by ISO code. Generic; extend per language.
LANGUAGE_WORDS = {
    "tr": ("tr", "tr-tr", "turkish", "türkçe", "turkce", "türkce"),
    "en": ("en", "en-us", "en-gb", "english"),
}
# Names for the prompts: the last word of each list, capitalised ("turkish" -> "Turkish").
LANGUAGE_NAMES = {code: words[-1].capitalize() for code, words in {"tr": ("turkish",), "en": LANGUAGE_WORDS["en"]}.items()}
# T-044: the recording notice said in the present, per language (T-026 for English).
RECORDING_NOTICE_BY_LANGUAGE = {"tr": "görüşmemiz kayıt altına alınıyor"}
RECORDED_WORD_BY_LANGUAGE = {"tr": "kaydedildi"}


# Turkish month names and day numbers in words, for the self-check's spoken dates (T-041).
TURKISH_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
                  "Kasım", "Aralık")
_TURKISH_UNITS = ("", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_TURKISH_TENS = ("", "on", "yirmi", "otuz")


def turkish_number(number: int) -> str:
    """1..31 in words: 27 -> "yirmi yedi"."""
    return " ".join(word for word in (_TURKISH_TENS[number // 10], _TURKISH_UNITS[number % 10]) if word)


def spoken_date_forms_for(code: str, day: Any) -> dict[str, str]:
    """Extra ways a customer says ``day`` in the call's language (none for English)."""
    if code != "tr":
        return {}
    month = TURKISH_MONTHS[day.month - 1]
    return {"tr_digits": f"{day.day} {month}", "tr_suffix": f"{day.day} {month}'de",
            "tr_words": f"{turkish_number(day.day)} {month}"}


_PLACEHOLDER = re.compile(r"\{\{[A-Za-z0-9_.]+\}\}|\{[A-Za-z0-9_]+\}|\[[A-Za-z0-9_]+\]")


def language_code(text: str | None) -> str:
    """The ISO code of ``agent.language`` ("Turkish", "tr", "Türkçe" -> "tr"); English by default."""
    word = str(text or "").strip().lower()
    for code, words in LANGUAGE_WORDS.items():
        if word in words or word.split("-")[0] == code:
            return code
    return ENGLISH


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def spoken_definitions() -> list[PromptDefinition]:
    """Every fixed line the builder itself makes the agent say (not the brief's quoted lines)."""
    found = [item for item in PROMPTS if "fixed spoken line" in item.receiver]
    return found + ([ACCOUNT_WAIT_LINE] if ACCOUNT_WAIT_LINE not in found else [])


def placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER.findall(text))


def _keys_of(text: str) -> list[str]:
    """OFFER_VERDICT_MESSAGES is "key: sentence" per line; the keys must survive."""
    return [line.partition(": ")[0].strip() for line in text.splitlines() if ": " in line]


def check_line(name: str, english: str, translated: Any) -> str:
    """"" when ``translated`` can replace ``english``, else why not."""
    if not isinstance(translated, str) or not translated.strip():
        return "empty"
    if placeholders(english) != placeholders(translated):
        return f"placeholders {placeholders(translated)} != {placeholders(english)}"
    if english.count("\n") != translated.count("\n"):
        return "line count changed"
    if name == "OFFER_VERDICT_MESSAGES" and _keys_of(english) != _keys_of(translated):
        return "message keys changed"
    return ""


# T-044: the words the generated code builds product names from, translated in the same call.
# Keys start with WORD_; the code falls back to the English word for a missing key.
WORD_PREFIX = "WORD_"
ORDINAL_WORDS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def product_word_entries(spec: Any = None) -> dict[str, str]:
    """English product-name words: the "<kind> ending <label>" pattern, the ordinal names, "and",
    and each product kind value the spec's offer rules name (credit_card -> "credit card")."""
    nth = "the {ordinal} product"
    entries = {
        WORD_PREFIX + "NAME_WITH_LABEL": "{kind} ending {label}",
        WORD_PREFIX + "PRODUCT": nth.split()[-1],
        WORD_PREFIX + "NTH": "\n".join(nth.replace("{ordinal}", word) for word in ORDINAL_WORDS),
        WORD_PREFIX + "AND": "and",
    }
    if spec is not None:
        for kind in product_kinds(spec):
            entries[WORD_PREFIX + "KIND_" + kind] = kind.replace("_", " ")
    return entries


def product_kinds(spec: Any) -> list[str]:
    """The kind values the spec's rules name for the account's kind field."""
    field = (spec.account.data or {}).get("product_kind_field")
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("field") == field:
                for item in [value.get("equals"), *(value.get("in") or [])]:
                    if isinstance(item, str) and item and item not in found:
                        found.append(item)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    if field:
        walk(spec.offer.data)
    return found


_CURRENT_WORDS: dict[str, str] = {}


def current_words() -> dict[str, str]:
    """The translated product words while ``localized`` is active ({} otherwise)."""
    return dict(_CURRENT_WORDS)


def _the_placeholders(name: str, text: str) -> str:
    """The generated code replaces "the [product]" and "the [next]" (T-044): a translated message
    keeps that form, so a name is put in whatever the word order."""
    if name != "OFFER_VERDICT_MESSAGES":
        return text
    return re.sub(r"(?<!the )\[(product|next)\]", r"the [\1]", text)


def translate_table(code: str, complete: Callable[[str, str], str],
                    extra: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """({name: translated text}, notes). ``complete(system, user)`` makes the one model call.
    A line that fails its check keeps the English text (a note says why). ``extra``: more
    entries in the same call (the product words)."""
    english = {item.name: item.text for item in spoken_definitions()}
    english.update(extra or {})
    notes: list[str] = []
    try:
        raw = complete(SPOKEN_TABLE_TRANSLATE_SYSTEM.text.replace("{language}", language_name(code)),
                       json.dumps(english, ensure_ascii=False, indent=1))
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        answer = json.loads(match.group(0) if match else raw)
    except Exception as exc:  # the call or its JSON failed: every line stays English
        return {}, [f"spoken-line translation to {code} failed ({type(exc).__name__}); English lines kept"]
    table = {}
    for name, text in english.items():
        problem = check_line(name, text, answer.get(name) if isinstance(answer, dict) else None)
        if problem:
            notes.append(f"spoken line {name} kept in English: {problem}")
        else:
            table[name] = _the_placeholders(name, answer[name])
    return table, notes


@contextlib.contextmanager
def localized(table: dict[str, str]) -> Iterator[None]:
    """Swap the translated texts into the prompt definitions while the workflow is rendered."""
    saved = {}
    _CURRENT_WORDS.clear()
    _CURRENT_WORDS.update({key: value for key, value in table.items() if key.startswith(WORD_PREFIX)})
    try:
        for item in spoken_definitions():
            if item.name in table:
                saved[item.name] = item.text
                object.__setattr__(item, "text", table[item.name])
        yield
    finally:
        for item in spoken_definitions():
            if item.name in saved:
                object.__setattr__(item, "text", saved[item.name])
        _CURRENT_WORDS.clear()


@contextlib.contextmanager
def spoken_language(spec: Any, trace: Any, client: Any = None) -> Iterator[None]:
    """build.py: render inside this. English: nothing happens. Another language: one model call
    translates the fixed lines (cached in the trace), then they are swapped in."""
    code = language_code(getattr(spec.agent, "language", ""))
    if code == ENGLISH:
        yield
        return
    if client is None:
        from .llm import AnthropicClient

        def log_call(purpose: str, result: Any) -> None:
            trace.add_model_call(result.model, purpose, result.duration_seconds,
                                 result.input_tokens, result.output_tokens, result.cache_read_tokens)

        client = AnthropicClient(log=log_call, note=lambda message: trace.add("warning", message))
    from .llm import text_block

    def complete(system: str, user: str) -> str:
        return client.complete(system, [{"role": "user", "content": [text_block(user)]}], "spoken_lines").text

    table, notes = translate_table(code, complete, product_word_entries(spec))
    for note in notes:
        trace.add("warning", note)
    trace.add("spoken_lines", json.dumps({"language": code, "table": table}, ensure_ascii=False))
    with localized(table):
        yield

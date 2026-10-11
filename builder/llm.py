"""Minimal Anthropic Messages API client over stdlib ``urllib`` (builder-time model calls).

The key is read from ``ANTHROPIC_API_KEY`` at call time and never logged, traced or
written anywhere. The model name is pinned here and written to the trace for every call.
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# The one place the extraction model is pinned (docs/ARCHITECTURE.md, "Builder model").
EXTRACTION_MODEL = "claude-sonnet-5-5"
# Sampling temperature sent with each request; None sends none. The pinned model rejects the
# setting ("temperature is deprecated for this model", live run T-006), so none is sent.
EXTRACTION_TEMPERATURE: float | None = None
# Raw bank material makes long replies (evidence quotes): one outcomes reply passed 16000 in the
# organizer rehearsal, which stopped the build. The limit is only a ceiling; replies are billed by use.
MAX_OUTPUT_TOKENS = 48000
REQUEST_TIMEOUT_SECONDS = 600
# T-052: a reply cut at the output limit is continued at most this many times.
MAX_CONTINUATIONS = 2
CONTINUE_NOTE = ("Your reply was cut at the output limit. Continue exactly where you stopped: write only the "
                 "remaining text, starting with the next character, with no repetition and no comment.")
KEY_ENV = "ANTHROPIC_API_KEY"
ANTHROPIC_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]+")
RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504, 529})


class LLMError(RuntimeError):
    """A model call failed; the message never contains the key."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    duration_seconds: float
    stop_reason: str


# (purpose, result) -> None; build.py writes it to the trace.
CallLog = Callable[[str, LLMResult], None]


def text_block(text: str, *, cache: bool = False) -> dict[str, Any]:
    """One text content block; ``cache`` marks the end of a reusable prompt prefix."""
    block: dict[str, Any] = {"type": "text", "text": text}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def redact(text: str) -> str:
    key = os.environ.get(KEY_ENV)
    if key:
        text = text.replace(key, "[REDACTED]")
    return ANTHROPIC_KEY_PATTERN.sub("[REDACTED]", text)


class AnthropicClient:
    """``complete()`` sends one Messages request; one retry on transport errors."""

    def __init__(
        self, *, model: str = EXTRACTION_MODEL, max_tokens: int = MAX_OUTPUT_TOKENS,
        timeout: float = REQUEST_TIMEOUT_SECONDS, log: CallLog | None = None,
        opener: Callable[..., Any] = urllib.request.urlopen,
        temperature: float | None = EXTRACTION_TEMPERATURE,
        note: Callable[[str], None] | None = None,
        stream: bool = False,
        continuations: int = MAX_CONTINUATIONS,
    ) -> None:
        if not os.environ.get(KEY_ENV):
            raise LLMError(f"{KEY_ENV} is not set; the spec cannot be extracted (use --spec for a written spec)")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.log = log
        self._opener = opener
        self.temperature = temperature
        self.note = note
        # T-046: long replies (a whole workflow) stream, so a reply longer than the timeout is
        # not cut: the timeout then applies to each silent gap, not to the whole reply.
        self.stream = stream
        self.continuations = continuations
        # T-052: continue with the cut text as an assistant prefill; a model that rejects a
        # prefill gets the cut text as an assistant turn plus a user note instead.
        self._prefill = True
        # Shared by parallel calls: read and cleared under the lock.
        self._lock = threading.Lock()

    def settings(self) -> str:
        """One trace line describing the request settings."""
        sent = "not sent" if self.temperature is None else str(self.temperature)
        return (f"model={self.model} temperature={sent} max_tokens={self.max_tokens} timeout_seconds={self.timeout:g}"
                + (" stream=yes" if self.stream else ""))

    def _drop_temperature(self) -> None:
        with self._lock:
            if self.temperature is None:
                return
            self.temperature = None
        if self.note is not None:
            self.note(f"model {self.model} rejected the temperature setting; requests are sent without it")

    def _payload(self, system: str, messages: list[dict[str, Any]], max_tokens: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": system,
            "messages": messages,
        }
        with self._lock:
            temperature = self.temperature
        if temperature is not None:
            payload["temperature"] = temperature
        if self.stream:
            payload["stream"] = True
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": os.environ.get(KEY_ENV, ""),
                "anthropic-version": API_VERSION,
            },
            method="POST",
        )
        with self._opener(request, timeout=self.timeout) as response:
            if payload.get("stream"):
                return _read_stream(response)
            return json.loads(response.read().decode("utf-8"))

    def complete(self, system: str, messages: list[dict[str, Any]], purpose: str, *, max_tokens: int | None = None,
                 continuations: int | None = None) -> LLMResult:
        """One reply; a reply cut at the output limit is continued (T-052) and the parts joined.
        Still cut after the last continuation: LLMError."""
        limit = max_tokens or self.max_tokens
        allowed = self.continuations if continuations is None else continuations
        result = self._once(system, messages, purpose, limit)
        text, results = result.text, [result]
        while result.stop_reason == "max_tokens" and len(results) <= allowed:
            prefill = text.rstrip()
            purpose_next = f"{purpose}_continue_{len(results)}"
            if self._prefill:
                try:
                    result = self._once(system, [*messages, {"role": "assistant", "content": prefill}],
                                        purpose_next, limit)
                    text = prefill + _rejoin(text[len(prefill):], result.text)
                    results.append(result)
                    continue
                except LLMError as exc:
                    if "HTTP 400" not in str(exc):
                        raise
                    self._prefill = False
                    if self.note is not None:
                        self.note(f"model {self.model} rejected an assistant prefill; continuing with a user note")
            result = self._once(system, [*messages, {"role": "assistant", "content": prefill},
                                         {"role": "user", "content": CONTINUE_NOTE}], purpose_next, limit)
            text = prefill + _rejoin(text[len(prefill):], _without_overlap(prefill, result.text))
            results.append(result)
        if result.stop_reason == "max_tokens":
            raise LLMError(f"model call {purpose!r} hit the output limit ({limit} tokens"
                           + (f", {len(results) - 1} continuation(s))" if len(results) > 1 else ")"))
        if len(results) == 1:
            return result
        return LLMResult(
            text=text, model=result.model,
            input_tokens=sum(item.input_tokens for item in results),
            output_tokens=sum(item.output_tokens for item in results),
            cache_read_tokens=sum(item.cache_read_tokens for item in results),
            duration_seconds=sum(item.duration_seconds for item in results),
            stop_reason=result.stop_reason)

    def _once(self, system: str, messages: list[dict[str, Any]], purpose: str, max_tokens: int) -> LLMResult:
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            payload = self._payload(system, messages, max_tokens)
            try:
                body = self._post(payload)
                break
            except urllib.error.HTTPError as exc:
                try:
                    detail = redact(exc.read().decode("utf-8", "replace"))[:300]
                finally:
                    exc.close()
                if exc.code == 400 and "temperature" in payload and "temperature" in detail:
                    # This request carried a temperature the model rejects: resend it without one.
                    # Decided by this request's payload, not by the shared setting, so every
                    # parallel call that sent it is resent; it does not use up the transport retry.
                    self._drop_temperature()
                    attempt -= 1
                    continue
                if exc.code == 400 and "max_tokens" in detail and max_tokens > MAX_OUTPUT_TOKENS:
                    # T-052: a model with a smaller output cap; the continuations make up the rest.
                    if self.note is not None:
                        self.note(f"model {self.model} refused max_tokens={max_tokens}; using {MAX_OUTPUT_TOKENS}")
                    max_tokens = MAX_OUTPUT_TOKENS
                    attempt -= 1
                    continue
                if exc.code in RETRY_STATUS and attempt == 1:
                    time.sleep(_retry_delay(exc))
                    continue
                raise LLMError(f"model call {purpose!r} failed: HTTP {exc.code}: {detail}") from None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                if attempt == 1:
                    time.sleep(2)
                    continue
                raise LLMError(f"model call {purpose!r} failed: {redact(str(exc))[:300]}") from None
            except json.JSONDecodeError:
                raise LLMError(f"model call {purpose!r} returned a non-JSON HTTP body") from None
        text = "".join(
            block.get("text", "") for block in body.get("content", []) if isinstance(block, dict)
            and block.get("type") == "text"
        )
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        result = LLMResult(
            text=text,
            model=str(body.get("model") or self.model),
            input_tokens=int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
            duration_seconds=time.monotonic() - started,
            stop_reason=str(body.get("stop_reason") or ""),
        )
        if self.log is not None:
            self.log(purpose, result)
        return result


def _rejoin(trimmed: str, continuation: str) -> str:
    """The whitespace trimmed from the prefill (the API refuses it) comes back, unless the
    continuation starts with its own."""
    return continuation if continuation[:1].isspace() else trimmed + continuation


def _without_overlap(before: str, after: str) -> str:
    """A continuation that repeats the end of the cut text (20+ characters) loses the repeat."""
    for size in range(min(len(before), len(after), 400), 19, -1):
        if before.endswith(after[:size]):
            return after[size:]
    return after


def _read_stream(response: Any) -> dict[str, Any]:
    """A streamed Messages reply (server-sent events) as the body a plain reply would have."""
    text: list[str] = []
    body: dict[str, Any] = {"usage": {}, "stop_reason": ""}
    for raw in response:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message") or {}
            body["model"] = message.get("model")
            body["usage"].update(message.get("usage") or {})
        elif kind == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
            text.append(event["delta"].get("text", ""))
        elif kind == "message_delta":
            body["stop_reason"] = (event.get("delta") or {}).get("stop_reason") or body["stop_reason"]
            body["usage"].update({key: value for key, value in (event.get("usage") or {}).items() if value is not None})
        elif kind == "error":
            raise json.JSONDecodeError(f"stream error: {event.get('error')}", "", 0)
    body["content"] = [{"type": "text", "text": "".join(text)}]
    return body


def _retry_delay(error: urllib.error.HTTPError) -> float:
    try:
        return min(max(float(error.headers.get("retry-after", 3)), 1.0), 20.0)
    except (TypeError, ValueError):
        return 3.0

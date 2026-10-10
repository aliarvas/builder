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
MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 300
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
        # Shared by parallel calls: read and cleared under the lock.
        self._lock = threading.Lock()

    def settings(self) -> str:
        """One trace line describing the request settings."""
        sent = "not sent" if self.temperature is None else str(self.temperature)
        return f"model={self.model} temperature={sent} max_tokens={self.max_tokens} timeout_seconds={self.timeout:g}"

    def _drop_temperature(self) -> None:
        with self._lock:
            if self.temperature is None:
                return
            self.temperature = None
        if self.note is not None:
            self.note(f"model {self.model} rejected the temperature setting; requests are sent without it")

    def _payload(self, system: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        with self._lock:
            temperature = self.temperature
        if temperature is not None:
            payload["temperature"] = temperature
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
            return json.loads(response.read().decode("utf-8"))

    def complete(self, system: str, messages: list[dict[str, Any]], purpose: str) -> LLMResult:
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            payload = self._payload(system, messages)
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
        if result.stop_reason == "max_tokens":
            raise LLMError(f"model call {purpose!r} hit the output limit ({self.max_tokens} tokens)")
        return result


def _retry_delay(error: urllib.error.HTTPError) -> float:
    try:
        return min(max(float(error.headers.get("retry-after", 3)), 1.0), 20.0)
    except (TypeError, ValueError):
        return 3.0

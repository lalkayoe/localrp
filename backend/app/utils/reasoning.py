"""
Some local reasoning models (Qwen3, DeepSeek-R1 distills, and others with a
"thinking" toggle) emit their chain-of-thought inline in the completion,
wrapped in <think>...</think> or <thinking>...</thinking>. Left unhandled,
this causes two concrete problems in this app:

1. The hidden memory-extraction call asks for raw JSON only — a leading
   <think>...</think> block makes the response fail json.loads entirely,
   logged as "Memory extraction returned non-JSON output, skipping this
   pass".
2. In the visible chat, the reasoning text would get streamed straight to
   the user, saved into the message, and then re-sent as context on every
   future turn — burning real chunks of your max_tokens budget on
   reasoning rather than the actual reply, which is very likely why
   replies feel cut short when thinking is enabled.

Both entry points below are defensive: if a model doesn't emit these tags
at all, they're a no-op.
"""
from __future__ import annotations

import re

_OPEN_TAGS = ["<think>", "<thinking>"]
_CLOSE_TAGS = ["</think>", "</thinking>"]

# One-shot: the whole response is available at once (used by the
# non-streaming provider.complete(), i.e. memory extraction / arc rollup).
_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL)
_THINK_UNCLOSED_RE = re.compile(r"<think(?:ing)?>.*$", re.IGNORECASE | re.DOTALL)


def strip_reasoning(text: str) -> str:
    """Removes complete <think>...</think> blocks. If a <think> tag is left
    unclosed (max_tokens ran out mid-thought, before the model got to its
    actual answer), everything from that tag onward is dropped too — there's
    no real answer left to recover from a response that's 100% reasoning."""
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_UNCLOSED_RE.sub("", cleaned)
    return cleaned.strip()


def _longest_partial_suffix_match(s: str, tags: list[str]) -> int:
    """How many trailing characters of `s` could be the start of one of
    `tags`, split across a stream chunk boundary — e.g. s ending in "<th"
    might be the start of "<think>" if the next delta continues it."""
    s_lower = s.lower()
    best = 0
    for tag in tags:
        tag_lower = tag.lower()
        max_check = min(len(s_lower), len(tag_lower) - 1)
        for length in range(max_check, 0, -1):
            if s_lower[-length:] == tag_lower[:length]:
                best = max(best, length)
                break
    return best


class ThinkTagStripper:
    """Streaming counterpart to strip_reasoning(): feed it deltas as they
    arrive from provider.stream_chat(), get back only the visible text.
    Buffers internally so a tag split across two chunks (e.g. "<thi" + "nk>")
    is still caught correctly."""

    def __init__(self) -> None:
        self._buffer = ""
        self._inside_think = False

    def feed(self, delta: str) -> str:
        self._buffer += delta
        out: list[str] = []
        while True:
            if not self._inside_think:
                idx, tag_len = self._find_tag(_OPEN_TAGS)
                if idx is not None:
                    out.append(self._buffer[:idx])
                    self._buffer = self._buffer[idx + tag_len:]
                    self._inside_think = True
                    continue
                hold = _longest_partial_suffix_match(self._buffer, _OPEN_TAGS)
                emit_len = len(self._buffer) - hold
                out.append(self._buffer[:emit_len])
                self._buffer = self._buffer[emit_len:]
                break
            else:
                idx, tag_len = self._find_tag(_CLOSE_TAGS)
                if idx is not None:
                    self._buffer = self._buffer[idx + tag_len:]
                    self._inside_think = False
                    continue
                # still inside a think block with no closing tag in sight yet —
                # everything is reasoning, discard it, but keep a possible
                # partial closing-tag suffix so we don't miss it next feed()
                hold = _longest_partial_suffix_match(self._buffer, _CLOSE_TAGS)
                self._buffer = self._buffer[len(self._buffer) - hold:] if hold else ""
                break
        return "".join(out)

    def flush(self) -> str:
        """Call once the stream ends. If the model never closed its <think>
        block (cut off by max_tokens), there's nothing recoverable left —
        returns whatever plain text was still safely buffered, if any."""
        if self._inside_think:
            return ""
        remainder, self._buffer = self._buffer, ""
        return remainder

    def _find_tag(self, tags: list[str]) -> tuple[int | None, int]:
        lower = self._buffer.lower()
        best: tuple[int, int] | None = None
        for tag in tags:
            idx = lower.find(tag.lower())
            if idx != -1 and (best is None or idx < best[0]):
                best = (idx, len(tag))
        return best if best else (None, 0)

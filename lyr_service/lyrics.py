"""Unicode-safe lyric cleanup, phrase shaping, and LRC serialization."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .domain import LyricLine, TimedSegment

MAX_WORDS_PER_LINE = 12
MIN_CUE_MS = 350
DEFAULT_CUE_MS = 2_800
_DUPLICATE_GAP_MS = 1_200
_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?]")
_METADATA = re.compile(r"^\[(ar|ti|al|by|re|ve|length|offset):.*]$", re.IGNORECASE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[।!?;])\s+|(?<=[.!?;])\s+")
_SPECIAL_TOKEN = re.compile(r"<\|[^|>]+\|>")
_SPACES = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\u0980-\u09FF']+", re.UNICODE)
_NON_LYRIC_MARKERS = {
    "music",
    "instrumental",
    "applause",
    "silence",
    "background music",
    "সঙ্গীত",
    "বাদ্যযন্ত্র",
    "মিউজিক",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value or "")
    normalized = _SPECIAL_TOKEN.sub(" ", normalized)
    return _SPACES.sub(" ", normalized).strip(" \t\r\n♪♫")


def comparison_text(value: str) -> str:
    value = normalize_text(value).casefold()
    return _SPACES.sub(" ", _NON_WORD.sub(" ", value)).strip()


def contains_bengali(value: str) -> bool:
    return any("\u0980" <= character <= "\u09ff" for character in value)


def _is_marker(value: str) -> bool:
    marker = normalize_text(value).strip("[](){} ").casefold().rstrip(".!,।")
    return marker in _NON_LYRIC_MARKERS


def _split_text(text: str) -> list[str]:
    text = normalize_text(text)
    if not text or _is_marker(text):
        return []
    phrases: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(text):
        words = sentence.split()
        while words:
            phrases.append(" ".join(words[:MAX_WORDS_PER_LINE]))
            words = words[MAX_WORDS_PER_LINE:]
    return [phrase for phrase in phrases if phrase]


def segments_to_lines(
    segments: Iterable[TimedSegment], duration_seconds: float
) -> tuple[LyricLine, ...]:
    duration_ms = max(0, int(duration_seconds * 1_000))
    candidates: list[LyricLine] = []
    for segment in sorted(segments, key=lambda item: item.start_seconds):
        phrases = _split_text(segment.text)
        if not phrases:
            continue
        start_ms = max(0, int(segment.start_seconds * 1_000))
        end_ms = max(start_ms + MIN_CUE_MS, int(segment.end_seconds * 1_000))
        if duration_ms:
            start_ms = min(start_ms, max(0, duration_ms - 1))
            end_ms = min(end_ms, duration_ms)
        if end_ms <= start_ms:
            continue
        weights = [max(1, len(comparison_text(phrase))) for phrase in phrases]
        weight_total = sum(weights)
        elapsed = 0
        for index, (phrase, weight) in enumerate(zip(phrases, weights, strict=True)):
            cue_start = start_ms + (end_ms - start_ms) * elapsed // weight_total
            elapsed += weight
            cue_end = (
                end_ms
                if index == len(phrases) - 1
                else start_ms + (end_ms - start_ms) * elapsed // weight_total
            )
            cue_end = max(cue_start + MIN_CUE_MS, cue_end)
            if duration_ms:
                cue_end = min(cue_end, duration_ms)
            if cue_end > cue_start:
                candidates.append(LyricLine(cue_start, cue_end, phrase))

    merged: list[LyricLine] = []
    for cue in candidates:
        previous = merged[-1] if merged else None
        if (
            previous
            and comparison_text(previous.text) == comparison_text(cue.text)
            and cue.start_ms <= previous.end_ms + _DUPLICATE_GAP_MS
        ):
            merged[-1] = LyricLine(
                previous.start_ms, max(previous.end_ms, cue.end_ms), previous.text
            )
        else:
            merged.append(cue)

    bounded: list[LyricLine] = []
    for index, cue in enumerate(merged):
        next_start = merged[index + 1].start_ms if index + 1 < len(merged) else None
        end_ms = cue.end_ms
        if next_start is not None:
            end_ms = min(end_ms, next_start)
        if end_ms <= cue.start_ms:
            end_ms = cue.start_ms + MIN_CUE_MS
            if duration_ms:
                end_ms = min(end_ms, duration_ms)
        if end_ms > cue.start_ms:
            bounded.append(LyricLine(cue.start_ms, end_ms, cue.text))
    return tuple(bounded)


def format_timestamp(milliseconds: int) -> str:
    safe = max(0, int(milliseconds))
    minutes = safe // 60_000
    seconds = (safe % 60_000) // 1_000
    centiseconds = (safe % 1_000) // 10
    return f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"


def serialize_lrc(
    lines: Iterable[LyricLine], *, title: str = "", artist: str = ""
) -> str:
    output: list[str] = []
    if title.strip():
        output.append(f"[ti:{normalize_text(title)[:300]}]")
    if artist.strip():
        output.append(f"[ar:{normalize_text(artist)[:300]}]")
    for line in sorted(lines, key=lambda item: item.start_ms):
        output.append(f"{format_timestamp(line.start_ms)} {line.text.strip()}")
        output.append(format_timestamp(line.end_ms))
    return "\n".join(output).strip()


def parse_lrc(raw_lrc: str) -> tuple[LyricLine, ...]:
    events: list[tuple[int, str]] = []
    for original in (raw_lrc or "").splitlines():
        line = original.strip().lstrip("\ufeff")
        if not line or _METADATA.match(line):
            continue
        matches = list(_TIMESTAMP.finditer(line))
        if not matches:
            continue
        text = normalize_text(_TIMESTAMP.sub("", line))
        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or ""
            fraction_ms = int(fraction.ljust(3, "0")[:3]) if fraction else 0
            events.append((minutes * 60_000 + seconds * 1_000 + fraction_ms, text))
    events.sort(key=lambda item: item[0])
    result: list[LyricLine] = []
    for timestamp, text in events:
        if not text:
            if result and timestamp > result[-1].start_ms:
                previous = result[-1]
                result[-1] = LyricLine(previous.start_ms, timestamp, previous.text)
            continue
        next_default = timestamp + DEFAULT_CUE_MS
        if result and result[-1].end_ms > timestamp:
            previous = result[-1]
            result[-1] = LyricLine(previous.start_ms, timestamp, previous.text)
        result.append(LyricLine(timestamp, next_default, text))
    return tuple(result)


def plain_from_lrc(raw_lrc: str) -> str:
    return "\n".join(line.text for line in parse_lrc(raw_lrc))

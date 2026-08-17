"""Typed domain records for the online lyrics pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class RecognitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioData:
    samples: Any
    sample_rate: int
    duration_seconds: float
    original_name: str


@dataclass(frozen=True)
class TimedSegment:
    start_seconds: float
    end_seconds: float
    text: str

    def __post_init__(self) -> None:
        if self.start_seconds < 0:
            raise ValueError("segment start must be non-negative")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("segment end must follow start")


@dataclass(frozen=True)
class LyricLine:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("invalid lyric cue interval")
        if not self.text.strip():
            raise ValueError("lyric cue text cannot be blank")


@dataclass(frozen=True)
class LyricsDocument:
    source: str
    title: str
    artist: str
    language: str
    duration_seconds: float
    plain_lyrics: str
    synced_lyrics: str
    lines: tuple[LyricLine, ...]
    provider_id: int | None = None
    confidence: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["lines"] = [asdict(line) for line in self.lines]
        value["warnings"] = list(self.warnings)
        return value

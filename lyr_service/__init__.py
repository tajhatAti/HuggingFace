"""Lyr Online: bounded online song-to-lyrics services."""

from .domain import AudioData, LyricLine, LyricsDocument, RecognitionError, TimedSegment

__all__ = [
    "AudioData",
    "LyricLine",
    "LyricsDocument",
    "RecognitionError",
    "TimedSegment",
]

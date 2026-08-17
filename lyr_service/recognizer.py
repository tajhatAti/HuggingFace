"""Adapter around a Transformers Whisper pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from .domain import RecognitionError, TimedSegment
from .lyrics import normalize_text

LANGUAGE_CODES = {
    "Auto detect": None,
    "বাংলা": "bn",
    "English": "en",
    "Hindi": "hi",
    "Urdu": "ur",
}


class WhisperRecognizer:
    def __init__(self, pipeline: Callable[..., dict[str, Any]]) -> None:
        self.pipeline = pipeline

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        duration_seconds: float,
        language_label: str,
    ) -> tuple[str, tuple[TimedSegment, ...], str]:
        language = LANGUAGE_CODES.get(language_label)
        generate_kwargs: dict[str, str] = {"task": "transcribe"}
        if language:
            generate_kwargs["language"] = language
        try:
            result = self.pipeline(
                {"array": samples, "sampling_rate": sample_rate},
                return_timestamps=True,
                generate_kwargs=generate_kwargs,
                batch_size=8,
            )
        except Exception as exc:
            raise RecognitionError(
                f"Whisper could not process this audio: {type(exc).__name__}"
            ) from exc
        if not isinstance(result, dict):
            raise RecognitionError("Whisper returned an invalid result.")
        transcript = normalize_text(str(result.get("text") or ""))
        segments: list[TimedSegment] = []
        chunks = result.get("chunks")
        if isinstance(chunks, list):
            for item in chunks:
                if not isinstance(item, dict):
                    continue
                timestamp = item.get("timestamp")
                if not isinstance(timestamp, (tuple, list)) or len(timestamp) != 2:
                    continue
                try:
                    start = max(0.0, float(timestamp[0] or 0.0))
                    end = float(
                        timestamp[1] if timestamp[1] is not None else duration_seconds
                    )
                except (TypeError, ValueError):
                    continue
                end = min(duration_seconds, max(start + 0.1, end))
                text = normalize_text(str(item.get("text") or ""))
                if text and end > start:
                    segments.append(TimedSegment(start, end, text))
        if transcript and not segments:
            segments.append(TimedSegment(0.0, max(0.1, duration_seconds), transcript))
        if not transcript and segments:
            transcript = " ".join(segment.text for segment in segments)
        if not transcript or not segments:
            raise RecognitionError(
                "No usable sung words were recognized in this recording."
            )
        detected = language or "auto"
        return transcript, tuple(segments), detected

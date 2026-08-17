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
PREVIEW_CLIP_SECONDS = 8
PREVIEW_START_FRACTIONS = (0.16, 0.46, 0.74)


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


class CpuWhisperRecognizer:
    """CTranslate2 int8 Whisper adapter for staged quota-free CPU inference."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def preview(
        self,
        samples: np.ndarray,
        sample_rate: int,
        duration_seconds: float,
        language_label: str,
    ) -> tuple[str, str, float]:
        """Listen to three short vocal regions to infer language and identity words."""

        if sample_rate != 16_000:
            raise RecognitionError("CPU Whisper requires 16 kHz audio.")
        clip_samples = min(samples.size, PREVIEW_CLIP_SECONDS * sample_rate)
        max_start = max(0, samples.size - clip_samples)
        starts = sorted(
            {
                int(max_start * fraction)
                for fraction in PREVIEW_START_FRACTIONS
            }
        )
        clips = [samples[start : start + clip_samples] for start in starts]
        silence = np.zeros(sample_rate // 4, dtype=np.float32)
        preview_parts: list[np.ndarray] = []
        for index, clip in enumerate(clips):
            if index:
                preview_parts.append(silence)
            preview_parts.append(clip)
        preview_audio = np.concatenate(preview_parts) if preview_parts else samples
        forced_language = LANGUAGE_CODES.get(language_label)
        try:
            generated, info = self.model.transcribe(
                preview_audio,
                language=forced_language,
                task="transcribe",
                beam_size=1,
                best_of=1,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
            )
            text = normalize_text(
                " ".join(str(item.text or "") for item in generated)
            )
            language = forced_language or str(getattr(info, "language", "auto"))
            probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        except Exception as exc:
            raise RecognitionError(
                f"AI preview could not inspect this audio: {type(exc).__name__}"
            ) from exc
        return text, language, max(0.0, min(1.0, probability))

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        duration_seconds: float,
        language_label: str,
    ) -> tuple[str, tuple[TimedSegment, ...], str]:
        if sample_rate != 16_000:
            raise RecognitionError("CPU Whisper requires 16 kHz audio.")
        language = LANGUAGE_CODES.get(language_label)
        try:
            generated, info = self.model.transcribe(
                samples,
                language=language,
                task="transcribe",
                beam_size=3,
                best_of=3,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
            )
            segments: list[TimedSegment] = []
            text_parts: list[str] = []
            for item in generated:
                start = max(0.0, float(item.start))
                end = min(duration_seconds, max(start + 0.1, float(item.end)))
                text = normalize_text(str(item.text or ""))
                if text and end > start:
                    segments.append(TimedSegment(start, end, text))
                    text_parts.append(text)
        except Exception as exc:
            raise RecognitionError(
                f"CPU Whisper could not process this audio: {type(exc).__name__}"
            ) from exc
        transcript = normalize_text(" ".join(text_parts))
        if not transcript or not segments:
            raise RecognitionError(
                "No usable sung words were recognized in this recording."
            )
        detected = language or normalize_text(str(getattr(info, "language", "auto")))
        return transcript, tuple(segments), detected or "auto"

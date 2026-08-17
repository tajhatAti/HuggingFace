"""Retrieval-first online song-to-synced-lyrics orchestration."""

from __future__ import annotations

from typing import Any, Protocol

from .domain import AudioData, LyricsDocument, RecognitionError, TimedSegment
from .lyrics import (
    contains_bengali,
    parse_lrc,
    plain_from_lrc,
    segments_to_lines,
    serialize_lrc,
)
from .provider import (
    LrcLibCandidate,
    LrcLibClient,
    LyricsProviderError,
    choose_metadata_candidate,
    choose_transcript_candidate,
    transcript_phrases,
)


class Recognizer(Protocol):
    def transcribe(
        self,
        samples: Any,
        sample_rate: int,
        duration_seconds: float,
        language_label: str,
    ) -> tuple[str, tuple[TimedSegment, ...], str]: ...


class LyricsServiceError(RuntimeError):
    pass


def _provider_document(
    candidate: LrcLibCandidate,
    *,
    source: str,
    confidence: float,
    language: str,
    warnings: tuple[str, ...] = (),
) -> LyricsDocument:
    lines = parse_lrc(candidate.synced_lyrics)
    if not lines:
        raise LyricsServiceError(
            "The online match did not contain usable synchronized lyrics."
        )
    plain = candidate.plain_lyrics.strip() or plain_from_lrc(candidate.synced_lyrics)
    return LyricsDocument(
        source=source,
        title=candidate.title,
        artist=candidate.artist,
        language=language,
        duration_seconds=candidate.duration_seconds,
        plain_lyrics=plain,
        synced_lyrics=serialize_lrc(
            lines, title=candidate.title, artist=candidate.artist
        ),
        lines=lines,
        provider_id=candidate.record_id,
        confidence=round(confidence, 4),
        warnings=warnings,
    )


class LyricsService:
    def __init__(
        self,
        provider: LrcLibClient | None = None,
        recognizer: Recognizer | None = None,
    ) -> None:
        self.provider = provider or LrcLibClient()
        self.recognizer = recognizer

    def lookup(
        self,
        title: str,
        artist: str = "",
        duration_seconds: float = 0.0,
    ) -> LyricsDocument:
        if not (title or "").strip():
            raise LyricsServiceError("Enter the song title for instant lookup.")
        try:
            candidates = self.provider.search_metadata(title, artist, duration_seconds)
        except LyricsProviderError as exc:
            raise LyricsServiceError(str(exc)) from exc
        match, confidence = choose_metadata_candidate(
            candidates,
            title=title,
            artist=artist,
            duration_seconds=duration_seconds,
        )
        if match is None:
            raise LyricsServiceError(
                "No trustworthy synchronized match was found. Upload the song for AI listening."
            )
        language = "bn" if contains_bengali(match.synced_lyrics) else "unknown"
        return _provider_document(
            match, source="lrclib_metadata", confidence=confidence, language=language
        )

    def transcribe(
        self,
        audio: AudioData,
        *,
        title: str = "",
        artist: str = "",
        language_label: str = "Auto detect",
    ) -> LyricsDocument:
        warnings: list[str] = []
        if title.strip():
            try:
                candidates = self.provider.search_metadata(
                    title, artist, audio.duration_seconds
                )
                match, confidence = choose_metadata_candidate(
                    candidates,
                    title=title,
                    artist=artist,
                    duration_seconds=audio.duration_seconds,
                )
                if match is not None:
                    language = (
                        "bn" if contains_bengali(match.synced_lyrics) else "unknown"
                    )
                    return _provider_document(
                        match,
                        source="lrclib_metadata",
                        confidence=confidence,
                        language=language,
                        warnings=(
                            "Exact online synchronized lyrics were used; AI transcription was not needed.",
                        ),
                    )
            except LyricsProviderError as exc:
                warnings.append(str(exc))

        if self.recognizer is None:
            raise LyricsServiceError(
                "AI listening is temporarily unavailable; instant title lookup still works."
            )
        try:
            transcript, segments, detected_language = self.recognizer.transcribe(
                audio.samples,
                audio.sample_rate,
                audio.duration_seconds,
                language_label,
            )
        except RecognitionError as exc:
            raise LyricsServiceError(str(exc)) from exc

        bengali_expected = language_label == "বাংলা" or contains_bengali(
            f"{title} {artist} {transcript}"
        )
        provider_candidates: dict[int, LrcLibCandidate] = {}
        for phrase in transcript_phrases(transcript):
            try:
                for candidate in self.provider.search_text(phrase):
                    provider_candidates[candidate.record_id] = candidate
            except LyricsProviderError as exc:
                warnings.append(str(exc))
                break
        match, confidence = choose_transcript_candidate(
            tuple(provider_candidates.values()),
            transcript=transcript,
            duration_seconds=audio.duration_seconds,
            bengali_expected=bengali_expected,
        )
        if match is not None:
            language = (
                "bn" if contains_bengali(match.synced_lyrics) else detected_language
            )
            return _provider_document(
                match,
                source="lrclib_audio_match",
                confidence=confidence,
                language=language,
                warnings=tuple(dict.fromkeys(warnings)),
            )

        lines = segments_to_lines(segments, audio.duration_seconds)
        if not lines:
            raise LyricsServiceError(
                "AI heard text but could not create usable lyric timing."
            )
        resolved_title = title.strip() or audio.original_name.rsplit(".", 1)[0]
        resolved_artist = artist.strip() or "Unknown artist"
        synced = serialize_lrc(lines, title=resolved_title, artist=resolved_artist)
        return LyricsDocument(
            source="whisper_ai",
            title=resolved_title,
            artist=resolved_artist,
            language="bn" if bengali_expected else detected_language,
            duration_seconds=audio.duration_seconds,
            plain_lyrics="\n".join(line.text for line in lines),
            synced_lyrics=synced,
            lines=lines,
            confidence=None,
            warnings=tuple(
                dict.fromkeys(
                    warnings
                    + [
                        "No trustworthy community match was found; this is an AI transcription of the recording.",
                        "Singing, accompaniment, reverb, and pronunciation can reduce transcription accuracy.",
                    ]
                )
            ),
        )

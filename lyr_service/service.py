"""Retrieval-first online song-to-synced-lyrics orchestration."""

from __future__ import annotations

import re
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
    SongIdentity,
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


_LANGUAGE_LABEL_BY_CODE = {
    "bn": "বাংলা",
    "en": "English",
    "hi": "Hindi",
    "ur": "Urdu",
}
_FILENAME_NOISE = {
    "audio",
    "copy",
    "download",
    "file",
    "music",
    "official",
    "public",
    "domain",
    "recording",
    "track",
    "upload",
}


def _filename_title_hint(original_name: str) -> str:
    stem = (original_name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem.rsplit(".", 1)[0]
    words = re.findall(r"[^\W_]+", stem.replace("_", " ").replace("-", " "), re.UNICODE)
    useful = [
        word
        for word in words
        if word.casefold() not in _FILENAME_NOISE
        and not word.isdigit()
        and not re.fullmatch(r"[0-9a-fA-F]{8,}", word)
    ]
    return " ".join(useful[:16]) if len(useful) >= 2 else ""


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


def _search_from_ai_evidence(
    provider: Any,
    *,
    transcript: str,
    duration_seconds: float,
    bengali_expected: bool,
    warnings: list[str],
) -> tuple[LrcLibCandidate | None, float, SongIdentity | None]:
    """Identify title/artist from AI words, then require a verified synchronized match."""

    candidates: dict[int, LrcLibCandidate] = {}
    identities: dict[tuple[str, str], SongIdentity] = {}
    for phrase in transcript_phrases(transcript):
        try:
            for candidate in provider.search_text(phrase):
                candidates[candidate.record_id] = candidate
            identity_search = getattr(provider, "search_identities", None)
            if callable(identity_search):
                for identity in identity_search(phrase):
                    key = (identity.title.casefold(), identity.artist.casefold())
                    previous = identities.get(key)
                    if previous is None or identity.exact_words > previous.exact_words:
                        identities[key] = identity
        except LyricsProviderError as exc:
            warnings.append(str(exc))
            break

    ranked_identities = sorted(
        identities.values(),
        key=lambda item: (-item.exact_words, -item.matched_words),
    )
    for identity in ranked_identities[:3]:
        try:
            for candidate in provider.search_metadata(
                identity.title,
                identity.artist,
                duration_seconds,
            ):
                candidates[candidate.record_id] = candidate
        except LyricsProviderError as exc:
            warnings.append(str(exc))
            break

    match, confidence = choose_transcript_candidate(
        tuple(candidates.values()),
        transcript=transcript,
        duration_seconds=duration_seconds,
        bengali_expected=bengali_expected,
    )
    best_identity = ranked_identities[0] if ranked_identities else None
    return match, confidence, best_identity


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

        # Step 1: trust useful MediaStore metadata only after strict provider verification.
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
                            "Verified title/artist online; full AI listening was not needed.",
                        ),
                    )
            except LyricsProviderError as exc:
                warnings.append(str(exc))

        if self.recognizer is None:
            raise LyricsServiceError(
                "AI listening is temporarily unavailable; instant title lookup still works."
            )

        # Step 2: AI listens to three short regions first. This detects Bengali before full
        # transcription and supplies words for title/artist identification and online lookup.
        preview_text = ""
        detected_language = "auto"
        preview_probability = 0.0
        preview_method = getattr(self.recognizer, "preview", None)
        if callable(preview_method):
            try:
                preview_text, detected_language, preview_probability = preview_method(
                    audio.samples,
                    audio.sample_rate,
                    audio.duration_seconds,
                    language_label,
                )
            except RecognitionError as exc:
                warnings.append(str(exc))

        bengali_expected = (
            language_label == "বাংলা"
            or detected_language == "bn"
            or contains_bengali(f"{title} {artist} {preview_text}")
        )
        if detected_language and detected_language != "auto":
            probability_text = (
                f" ({preview_probability:.0%} confidence)"
                if preview_probability > 0
                else ""
            )
            warnings.append(
                f"AI preview detected {detected_language}{probability_text} before lookup."
            )

        identified: SongIdentity | None = None
        if preview_text:
            match, confidence, identified = _search_from_ai_evidence(
                self.provider,
                transcript=preview_text,
                duration_seconds=audio.duration_seconds,
                bengali_expected=bengali_expected,
                warnings=warnings,
            )
            if identified is not None:
                warnings.append(
                    f"AI identified a likely song: {identified.title} — {identified.artist}."
                )
            if match is not None:
                language = "bn" if contains_bengali(match.synced_lyrics) else detected_language
                return _provider_document(
                    match,
                    source="lrclib_audio_match",
                    confidence=confidence,
                    language=language,
                    warnings=tuple(dict.fromkeys(warnings)),
                )

        # A descriptive local filename is only a hint: verify it online after the AI
        # preview, then use the verified identity for one more synchronized search.
        filename_hint = _filename_title_hint(audio.original_name)
        title_search = getattr(self.provider, "search_title_identities", None)
        if filename_hint and callable(title_search):
            try:
                filename_identities = title_search(filename_hint)
                if not filename_identities:
                    lyric_search = getattr(self.provider, "search_identities", None)
                    if callable(lyric_search):
                        filename_identities = lyric_search(filename_hint)
                if filename_identities and (
                    identified is None
                    or filename_identities[0].exact_words >= identified.exact_words
                ):
                    identified = filename_identities[0]
                    warnings.append(
                        "AI evidence was supplemented by an online-verified filename "
                        f"identity: {identified.title} — {identified.artist}."
                    )
                    candidates = self.provider.search_metadata(
                        identified.title,
                        identified.artist,
                        audio.duration_seconds,
                    )
                    match, confidence = choose_metadata_candidate(
                        candidates,
                        title=identified.title,
                        artist=identified.artist,
                        duration_seconds=audio.duration_seconds,
                    )
                    if (
                        match is not None
                        and bengali_expected
                        and not contains_bengali(match.synced_lyrics)
                    ):
                        match = None
                    if match is not None:
                        return _provider_document(
                            match,
                            source="lrclib_audio_match",
                            confidence=confidence,
                            language=("bn" if bengali_expected else detected_language),
                            warnings=tuple(dict.fromkeys(warnings)),
                        )
            except LyricsProviderError as exc:
                warnings.append(str(exc))

        # Step 3: only a failed identity/synchronized search pays for full-song listening.
        effective_language_label = language_label
        if language_label == "Auto detect":
            effective_language_label = _LANGUAGE_LABEL_BY_CODE.get(
                detected_language,
                "Auto detect",
            )
        try:
            transcript, segments, full_detected_language = self.recognizer.transcribe(
                audio.samples,
                audio.sample_rate,
                audio.duration_seconds,
                effective_language_label,
            )
        except RecognitionError as exc:
            raise LyricsServiceError(str(exc)) from exc

        detected_language = (
            "bn" if bengali_expected else full_detected_language or detected_language
        )
        bengali_expected = bengali_expected or detected_language == "bn" or contains_bengali(
            transcript
        )

        # Step 4: richer full-song evidence gets one final identity and synced-lyrics search.
        match, confidence, full_identity = _search_from_ai_evidence(
            self.provider,
            transcript=transcript,
            duration_seconds=audio.duration_seconds,
            bengali_expected=bengali_expected,
            warnings=warnings,
        )
        if full_identity is not None:
            identified = full_identity
            warnings.append(
                f"Full-song AI identified: {identified.title} — {identified.artist}."
            )
        if match is not None:
            language = "bn" if contains_bengali(match.synced_lyrics) else detected_language
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
        resolved_title = (
            identified.title
            if identified is not None
            else title.strip() or audio.original_name.rsplit(".", 1)[0]
        )
        resolved_artist = (
            identified.artist
            if identified is not None
            else artist.strip() or "Unknown artist"
        )
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
                        "No trustworthy synchronized community match was found; full-song AI timing was used.",
                        "Singing, accompaniment, reverb, and pronunciation can reduce transcription accuracy.",
                    ]
                )
            ),
        )

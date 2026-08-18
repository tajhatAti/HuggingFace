# Lyr Online architecture

## Decision

The strong `tajhatAti/Lyr` branch already has an excellent native player, synchronized overlay, strict LRCLIB matching, local decoding, and on-device Whisper. This Space does not recreate the player. It replaces the expensive phone-side model path with a compact online service while keeping retrieval-first behavior.

## Pipeline

```text
Android app or minimal Space UI
    │
    ├── title/artist/duration ──> strict LRCLIB selection ──> synced LRC
    │
    └── bounded audio upload
            ├── stream-decode to bounded 16 kHz mono PCM, validate <= 8 minutes
            ├── verify supplied metadata online
            ├── AI preview from three short vocal regions
            ├── detect language; force bn for native বাংলা output
            ├── identify title/artist from preview evidence
            ├── bounded audio fingerprint when preview words do not identify it
            ├── strict LRCLIB synchronized search and identity verification
            ├── full-song CPU AI only after every retrieval path misses
            └── second verified search or quality-gated AI LRC + metadata + JSON
```

## Components

- `app.py` — quota-free CPU model lifecycle, minimal Gradio interface and public API callbacks.
- `lyr_service/audio.py` — bounded decode, float conversion and 16 kHz mono resampling.
- `lyr_service/provider.py` — fixed-host LRCLIB/Genius/MusicBrainz requests, candidate mapping and conservative scoring.
- `lyr_service/identifier.py` — isolated bounded Shazam fingerprint adapter.
- `lyr_service/recognizer.py` — Faster-Whisper and test-adapter output mapping.
- `lyr_service/lyrics.py` — Unicode cleanup, phrase splitting, explicit-end LRC serialization/parsing.
- `lyr_service/service.py` — retrieval-first orchestration.
- `lyr_service/domain.py` — immutable API records.

## Why quota-free Faster-Whisper large-v3-turbo

`dropbox-dash/faster-whisper-large-v3-turbo` runs through CTranslate2 int8 on the Space's free CPU. It uses more of the available 16 GB RAM and can take longer than the small model, but its stronger multilingual recognition is necessary for Bengali songs while remaining independent of daily ZeroGPU allowances. All available CPU threads are used, one transcription runs at a time, and RAM holds the model/audio safely but does not replace CPU compute. A short preview detects Bengali and attempts to identify the song before full listening; an isolated fingerprint fallback handles random filenames when words are insufficient. Native `bn` plus a Bengali-script usability gate rejects short, repetitive, Latin-heavy, or mixed-script fallback output instead of presenting it as successful lyrics.

## Lyr compatibility

The reviewed Android branch represents an explicit cue end as an empty timestamp after each lyric. `serialize_lrc()` emits that exact format, so instrumental gaps become blank in the Lyr overlay instead of leaving stale text visible.

## Failure behavior

- LRCLIB outage: audio transcription can still produce an AI LRC.
- CPU model outage: strict title lookup remains available.
- Invalid/oversized/long audio: rejected before inference.
- Weak audio-to-provider evidence: provider result is rejected and the AI transcript is returned with an accuracy warning.

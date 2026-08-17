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
            ├── metadata lookup (skip transcription when trustworthy)
            ├── multilingual int8 Faster-Whisper on the 16 GB CPU
            ├── up to two recognized-phrase LRCLIB searches
            ├── strict word/script/duration validation
            └── provider LRC or AI-timed LRC + JSON + download
```

## Components

- `app.py` — quota-free CPU model lifecycle, minimal Gradio interface and public API callbacks.
- `lyr_service/audio.py` — bounded decode, float conversion and 16 kHz mono resampling.
- `lyr_service/provider.py` — fixed-host LRCLIB requests, candidate mapping and conservative scoring.
- `lyr_service/recognizer.py` — Faster-Whisper and test-adapter output mapping.
- `lyr_service/lyrics.py` — Unicode cleanup, phrase splitting, explicit-end LRC serialization/parsing.
- `lyr_service/service.py` — retrieval-first orchestration.
- `lyr_service/domain.py` — immutable API records.

## Why quota-free Faster-Whisper small

`Systran/faster-whisper-small` runs through CTranslate2 int8 on the Space's free CPU. It trades some accuracy and speed for predictable personal availability: no daily ZeroGPU allowance can block the website or Android app. All available CPU threads are used, one transcription runs at a time, Bengali remains supported, and retrieval-first matching still avoids inference whenever trustworthy synchronized lyrics exist.

## Lyr compatibility

The reviewed Android branch represents an explicit cue end as an empty timestamp after each lyric. `serialize_lrc()` emits that exact format, so instrumental gaps become blank in the Lyr overlay instead of leaving stale text visible.

## Failure behavior

- LRCLIB outage: audio transcription can still produce an AI LRC.
- CPU model outage: strict title lookup remains available.
- Invalid/oversized/long audio: rejected before inference.
- Weak audio-to-provider evidence: provider result is rejected and the AI transcript is returned with an accuracy warning.

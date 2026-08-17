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
            ├── decode to mono PCM, validate <= 8 minutes
            ├── metadata lookup (skip GPU when trustworthy)
            ├── multilingual Whisper on ZeroGPU
            ├── up to two recognized-phrase LRCLIB searches
            ├── strict word/script/duration validation
            └── provider LRC or AI-timed LRC + JSON + download
```

## Components

- `app.py` — model lifecycle, ZeroGPU boundary, minimal Gradio interface and public API callbacks.
- `lyr_service/audio.py` — bounded decode, float conversion and 16 kHz mono resampling.
- `lyr_service/provider.py` — fixed-host LRCLIB requests, candidate mapping and conservative scoring.
- `lyr_service/recognizer.py` — Transformers Whisper output mapping.
- `lyr_service/lyrics.py` — Unicode cleanup, phrase splitting, explicit-end LRC serialization/parsing.
- `lyr_service/service.py` — retrieval-first orchestration.
- `lyr_service/domain.py` — immutable API records.

## Why Whisper large-v3-turbo

`openai/whisper-large-v3-turbo` is multilingual and keeps most large-v3 quality while using a faster decoder, which is a better fit for Bengali and sung audio than the small checkpoint. Its bfloat16 weights fit within the available 16 GB host RAM and ZeroGPU runtime. The model can be changed with `WHISPER_MODEL_ID`, but replacements must be measured before changing the 90-second declaration.

## Lyr compatibility

The reviewed Android branch represents an explicit cue end as an empty timestamp after each lyric. `serialize_lrc()` emits that exact format, so instrumental gaps become blank in the Lyr overlay instead of leaving stale text visible.

## Failure behavior

- LRCLIB outage: audio transcription can still produce an AI LRC.
- ZeroGPU/model outage: strict title lookup remains available.
- Invalid/oversized/long audio: rejected before inference.
- Weak audio-to-provider evidence: provider result is rejected and the AI transcript is returned with an accuracy warning.

# Operations

## Deploy

Push the fixed Arena branch. GitHub Actions runs unit tests and compile checks, syncs the Space, uses its free 16 GB host CPU, then uploads a public-domain WAV and requires successful synchronized LRC output.

## Verify

1. Confirm the workflow succeeds.
2. Confirm the Space runtime is `RUNNING` and the runtime SHA matches the newest Hub revision.
3. Load the page and verify the title is `Lyr Online`.
4. Call `/lookup_lyrics` with a known song and verify a strict synchronized result or a clear no-match response.
5. Upload a short public-domain speech/audio fixture and verify `whisper_ai` structured output and a valid `.lrc` download.
6. Verify 16 GB and eight-minute rejections, plus bounded 16 kHz mono decoding.
7. Verify no former RepoVault/GitHub explorer endpoint remains in `/gradio_api/info`.

## Troubleshooting

- **Model unavailable:** instant title lookup should still work; inspect the Faster-Whisper model download and CPU runtime logs.
- **LRCLIB error:** retry later; AI transcription can still finish if the model is available.
- **Audio decode error:** confirm the file is a valid MP3/M4A/WAV/FLAC/OGG/AAC and not DRM-protected.
- **Weak singing output:** provide title/artist, force the correct language, or correct the returned editable LRC in the Android app.

## Rollback

Revert the latest source commit and push the same fixed branch. Never restore the former repository explorer, Telegram bot, or leaked credentials as part of a rollback.

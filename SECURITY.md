# Security

## Product boundary

Lyr Online processes user-selected audio into lyrics. It does not execute uploads, install packages at runtime, expose a shell, accept arbitrary URLs, proxy traffic, collect third-party credentials, or publish lyrics automatically.

## Controls

- Uploads are capped at 16 GB and eight minutes, then FFmpeg decodes directly to bounded 16 kHz mono PCM so source-rate audio cannot exhaust RAM.
- Decoding produces mono PCM in memory; uploads are never executed.
- Application-controlled lookup hosts are fixed to LRCLIB plus Genius' public lyric-search API, used only for strict title/artist hints from AI-recognized words.
- HTTP redirects from the provider are rejected.
- Provider lists and lyric text lengths are bounded.
- Quota-free CPU transcription has concurrency, queue, upload, decode-time, and song-duration ceilings.
- Generated LRC files use randomized names, private file permissions, and two-hour cleanup.
- Errors do not echo audio, model prompts, tokens, or server paths.
- No secret is embedded in the Android integration contract.

## Privacy

The Space is public. Audio uploaded for transcription is handled by the Hugging Face/Gradio runtime and the Space process. Lyr Online does not create a permanent audio archive, but it must not be treated as an end-to-end encrypted or private storage service. Upload only recordings you have the right to process.

## Credential incident in the source Lyr repository

The public `main` branch of `tajhatAti/Lyr` was observed to contain Telegram bot credentials and a GitHub personal access token in source. Those values must be considered compromised even if the files are later deleted. Revoke/rotate them at Telegram BotFather and GitHub Settings; never copy them into this Space or an APK.

## Reporting

Report a vulnerability privately to the repository owner. Do not include live credentials or private audio in a public issue.

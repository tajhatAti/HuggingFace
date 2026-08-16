"""Request free ZeroGPU after GitHub Actions syncs the Gradio Space."""

from __future__ import annotations

import os
import sys

from huggingface_hub import HfApi

SPACE_ID = os.getenv("HF_SPACE_ID", "madarauchihagmailcom/My")
TOKEN = os.getenv("HF_TOKEN", "").strip()

if not TOKEN:
    raise SystemExit("HF_TOKEN is missing; cannot configure the Space.")

api = HfApi(token=TOKEN)
try:
    runtime = api.request_space_hardware(repo_id=SPACE_ID, hardware="zero-a10g")
except Exception as exc:
    print(f"Unable to request ZeroGPU for {SPACE_ID}: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise

print(
    f"Configured {SPACE_ID}: stage={runtime.stage}, "
    f"hardware={runtime.hardware}, requested={runtime.requested_hardware}"
)

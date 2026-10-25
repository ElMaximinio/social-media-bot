"""Generate one 9:16 clip per shot with Gemini Omni Flash (REST, URI delivery)."""
import time
from pathlib import Path

import requests

from . import config

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _find_video_uri(data: dict) -> str:
    # The video sits in the model_output step's content item of type "video".
    for step in data.get("steps", []):
        for item in step.get("content", []) or []:
            if item.get("type") == "video" and item.get("uri"):
                return item["uri"]
    out = data.get("output_video") or {}
    if out.get("uri"):
        return out["uri"]
    raise RuntimeError(f"No video URI in response: {str(data)[:500]}")


def generate_clip(prompt: str, dest: Path, timeout_s: int = 900) -> Path:
    key = config.require("GEMINI_API_KEY")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = {
        "model": config.OMNI_MODEL,
        "input": f"{prompt}. {config.STYLE}",
        "response_format": {
            "type": "video",
            "aspect_ratio": "9:16",
            "resolution": config.VIDEO_RESOLUTION,
            "delivery": "uri",
        },
    }
    r = requests.post(f"{BASE}/interactions", headers=headers, json=body, timeout=600)
    if not r.ok:
        # e.g. 429 "limit: 0 ... on Free Tier" means billing is not enabled on the key's project
        raise RuntimeError(f"Gemini video request failed ({r.status_code}): {r.text[:500]}")
    uri = _find_video_uri(r.json())
    file_id = uri.rstrip("/").split("/")[-1].split(":")[0]

    deadline = time.time() + timeout_s
    while True:
        info = requests.get(f"{BASE}/files/{file_id}", headers=headers, timeout=60).json()
        state = info.get("state")
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError(f"Video generation failed for: {prompt[:80]}")
        if time.time() > deadline:
            raise TimeoutError(f"Timed out waiting for {file_id}")
        time.sleep(5)

    with requests.get(f"{BASE}/files/{file_id}:download", params={"alt": "media"},
                      headers=headers, stream=True, timeout=600) as dl:
        dl.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in dl.iter_content(1 << 20):
                f.write(chunk)
    return dest

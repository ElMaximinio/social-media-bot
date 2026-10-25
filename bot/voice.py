"""Narration with ElevenLabs, plus word timings for captions."""
import base64
import json
from pathlib import Path

import requests

from . import config


def narrate(text: str, dest: Path) -> list[dict]:
    """Write an mp3 to dest and return word timings [{word, start, end}]."""
    key = config.require("ELEVENLABS_API_KEY")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}/with-timestamps"
    r = requests.post(
        url,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    dest.write_bytes(base64.b64decode(data["audio_base64"]))
    return words_from_alignment(data["alignment"])


def words_from_alignment(al: dict) -> list[dict]:
    words, cur, start, end = [], "", None, None
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"],
                        al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": start, "end": end})
            cur, start = "", None
            continue
        if start is None:
            start = s
        cur += ch
        end = e
    if cur:
        words.append({"word": cur, "start": start, "end": end})
    return words


def save_words(words: list[dict], path: Path) -> None:
    path.write_text(json.dumps(words, indent=1))

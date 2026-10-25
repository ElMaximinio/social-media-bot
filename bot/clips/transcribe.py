"""Speech to text with word timings, using ElevenLabs Scribe (same key as the narrator)."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests

from .. import config

URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = os.environ.get("BOT_STT_MODEL", "scribe_v1")


def extract_audio(video: Path, dest: Path, start: float | None = None, end: float | None = None) -> Path:
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def words_from_scribe(data: dict) -> list[dict]:
    """Scribe returns words, spacing and audio events. Keep spoken words only."""
    out = []
    for w in data.get("words", []):
        if w.get("type", "word") != "word":
            continue
        text = w.get("text", "").strip()
        if text:
            out.append({"word": text, "start": float(w["start"]), "end": float(w["end"])})
    return out


def transcribe(video: Path, start: float | None = None, end: float | None = None,
               language: str | None = None) -> list[dict]:
    key = config.require("ELEVENLABS_API_KEY")
    with tempfile.TemporaryDirectory() as tmp:
        audio = extract_audio(video, Path(tmp) / "audio.mp3", start, end)
        fields = {"model_id": MODEL, "timestamps_granularity": "word", "tag_audio_events": "true"}
        if language:
            fields["language_code"] = language
        with open(audio, "rb") as f:
            r = requests.post(URL, headers={"xi-api-key": key}, data=fields,
                              files={"file": ("audio.mp3", f, "audio/mpeg")}, timeout=900)
    if not r.ok:
        raise RuntimeError(f"ElevenLabs speech-to-text failed ({r.status_code}): {r.text[:500]}")
    return words_from_scribe(r.json())


def save(words: list[dict], path: Path) -> None:
    path.write_text(json.dumps(words, indent=1, ensure_ascii=False))

"""Offline stand-ins so the edit pipeline can be tested without API keys."""
import subprocess
from pathlib import Path

COLORS = ["0x3b2f2f", "0x2f3b4a", "0x4a3b2f", "0x2f4a3b", "0x45304a", "0x4a4530"]


def fake_clip(i: int, dest: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={COLORS[i % 6]}:s=720x1280:d=10:r=24",
                    "-f", "lavfi", "-i", "sine=f=220:d=10", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", str(dest)], capture_output=True, check=True)
    return dest


def fake_narration(text: str, dest: Path) -> list[dict]:
    words, t = [], 0.1
    for w in text.split():
        words.append({"word": w, "start": t, "end": t + 0.32})
        t += 0.38
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={t + 0.1:.2f}",
                    "-c:a", "libmp3lame", str(dest)], capture_output=True, check=True)
    return words

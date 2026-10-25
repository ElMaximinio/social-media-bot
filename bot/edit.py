"""Assemble beats into the master video and the platform cuts with FFmpeg."""
import json
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30
PAUSE = 0.35  # breath between beats, seconds


def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{res.stderr[-2000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(out.stdout.strip())


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(words: list[dict], path: Path, chunk: int = 3) -> None:
    """Big centered captions, three words at a time."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,80,80,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        nxt = words[i + chunk]["start"] if i + chunk < len(words) else group[-1]["end"] + 0.3
        text = " ".join(w["word"] for w in group).replace("{", "(").replace("}", ")").upper()
        lines.append(f"Dialogue: 0,{_ts(group[0]['start'])},{_ts(nxt)},Cap,,0,0,0,,{text}")
    path.write_text(header + "\n".join(lines) + "\n")


def build_segment(clip: Path, narration: Path, words: list[dict], dest: Path) -> Path:
    """One beat: clip fitted to 9:16, held/trimmed to the narration length, captions burned in."""
    seg_len = duration(narration) + PAUSE
    ass = dest.with_suffix(".ass")
    write_ass(words, ass)
    amb = "[0:a]" if has_audio(clip) else "[2:a]"
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration=30,trim=duration={seg_len:.3f},setpts=PTS-STARTPTS,"
          f"ass={ass}[v]")
    af = (f"{amb}volume=0.15,apad[amb];[1:a]apad[nar];"
          f"[amb][nar]amix=inputs=2:duration=longest:normalize=0,atrim=duration={seg_len:.3f}[a]")
    run(["ffmpeg", "-y", "-i", str(clip), "-i", str(narration),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(dest)])
    return dest


def concat(segments: list[Path], dest: Path) -> Path:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segments))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
         "-movflags", "+faststart", str(dest)])
    lst.unlink()
    return dest


def pick_cuts(seg_lengths: list[float], peak: int) -> dict[str, list[int]]:
    """Beat indices for each platform cut."""
    n = len(seg_lengths)
    ig, total = [], 0.0
    for i, d in enumerate(seg_lengths):
        if total + d > 45 and len(ig) >= 3:
            break
        ig.append(i)
        total += d
    peak = min(max(peak, 1), n - 1)
    return {"tiktok": list(range(n)), "instagram": ig, "x": [0, peak]}


def assemble(ep_dir: Path, n_beats: int, peak: int) -> dict[str, Path]:
    segs, lengths = [], []
    for i in range(n_beats):
        words = json.loads((ep_dir / f"beat{i}.words.json").read_text())
        seg = build_segment(ep_dir / f"clip{i}.mp4", ep_dir / f"beat{i}.mp3", words,
                            ep_dir / f"seg{i}.mp4")
        segs.append(seg)
        lengths.append(duration(seg))
    outputs = {}
    for platform, idx in pick_cuts(lengths, peak).items():
        outputs[platform] = concat([segs[i] for i in idx], ep_dir / f"{platform}.mp4")
    return outputs

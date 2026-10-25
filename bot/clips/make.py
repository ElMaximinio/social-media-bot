"""Clip workflow: find moments in a source, render one clip, post it.

A clip folder holds clip.json:
{
  "slug": "creator-moment",
  "source": "path/to/source.mp4",          # relative to the clip folder, or absolute
  "creator": "Creator Name",
  "credit": "@creator on Twitch",          # optional line under the hook
  "campaign": {"name": "...", "url": "...", "rules": "...", "required_tags": ["#tag"]},
  "start": 120.5, "end": 158.0,            # seconds in the source
  "hook": "He did NOT expect this answer",
  "caption": "TikTok caption #tags",
  "layout": "auto",                         # auto | stack | track | fit
  "tighten": true,                          # cut long quiet pauses
  "zooms": null                             # list of seconds to punch in, or null for loud moments
}
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .. import config
from ..edit import duration
from . import layout, render


def load(clip_dir: Path) -> dict:
    return json.loads((clip_dir / "clip.json").read_text())


def source_path(clip_dir: Path, spec: dict) -> Path:
    p = Path(spec["source"])
    return p if p.is_absolute() else clip_dir / p


def download(url: str, dest: Path, section: tuple[float, float] | None = None) -> Path:
    """Fetch a video with yt-dlp (needs network access to the site). Only for creators who allow clips."""
    cmd = ["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mp4",
           "-o", str(dest)]
    if section:
        cmd += ["--download-sections", f"*{section[0]:.2f}-{section[1]:.2f}", "--force-keyframes-at-cuts"]
    subprocess.run(cmd + [url], check=True)
    return dest


def find(source: str, creator: str, slug: str, rules: str = "", count: int = 3,
         min_len: float = 20, max_len: float = 60) -> Path:
    """Transcribe a whole source and save the best candidates. Writes clip.json with the top pick."""
    from . import pick, transcribe

    clip_dir = config.OUTPUT_DIR / "clips" / slug
    clip_dir.mkdir(parents=True, exist_ok=True)
    if source.startswith("http"):
        src = download(source, clip_dir / "source.mp4")
    else:
        src = Path(source).resolve()
    words_path = clip_dir / "source.words.json"
    if words_path.exists():
        words = json.loads(words_path.read_text())
    else:
        words = transcribe.transcribe(src)
        transcribe.save(words, words_path)
    (clip_dir / "transcript.txt").write_text(pick.transcript_lines(words), encoding="utf-8")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(f"Transcript saved to {clip_dir / 'transcript.txt'}. Set ANTHROPIC_API_KEY to pick "
                         "moments automatically, or write clip.json by hand (see bot/clips/make.py).")
    clips = pick.pick_clips(words, creator, rules, count, min_len, max_len)
    pick.save(clips, clip_dir / "candidates.json")
    best = clips[0]
    spec = {
        "slug": slug, "source": str(src), "creator": creator, "credit": "",
        "campaign": {"name": "", "url": "", "rules": rules, "required_tags": []},
        "start": best["start"], "end": best["end"], "hook": best["hook"], "caption": best["caption"],
        "layout": "auto", "tighten": True, "zooms": None,
    }
    (clip_dir / "clip.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    return clip_dir


def make(clip_dir: Path, dry_run: bool = False) -> dict:
    spec = load(clip_dir)
    work = clip_dir / "work"
    work.mkdir(exist_ok=True)

    cut = work / "cut.mp4"
    stamp = f"{spec['start']}-{spec['end']}"
    stamp_file = work / "cut.stamp"
    if not cut.exists() or not stamp_file.exists() or stamp_file.read_text() != stamp:
        render.cut(source_path(clip_dir, spec), spec["start"], spec["end"], cut)
        stamp_file.write_text(stamp)
        (work / "cut.words.json").unlink(missing_ok=True)

    words_path = work / "cut.words.json"
    if words_path.exists():
        words = json.loads(words_path.read_text())
    elif dry_run:
        words = []
    else:
        from . import transcribe
        words = transcribe.transcribe(cut)
        transcribe.save(words, words_path)

    total = duration(cut)
    level = render.loudness(cut)
    src = cut
    ranges = [(0.0, total)]
    if spec.get("tighten", True) and words:
        ranges = render.keep_ranges(words, total, level)
        if len(ranges) > 1:
            src = render.tighten(cut, ranges, work / "tight.mp4")
            words = render.remap_words(words, ranges)
            total = duration(src)
            level = render.loudness(src)

    faces = layout.detect_faces(src)
    kind = spec.get("layout", "auto")
    if kind == "auto":
        kind = layout.choose_layout(faces)

    zooms = spec.get("zooms")
    peaks = zooms if zooms is not None else render.loud_peaks(level)

    src_w, src_h = layout.video_size(src)
    _, caption_y = render.layout_filter(kind, src_w, src_h, faces)
    ass = render.write_ass(words, work / "captions.ass", total, caption_y,
                           hook=render.wrap_hook(spec.get("hook", "")), credit=spec.get("credit", ""))
    out = clip_dir / "tiktok.mp4"
    render.compose(src, out, kind, faces, ass, peaks)

    report = {
        "layout": kind,
        "duration": round(duration(out), 2),
        "removed_seconds": round(spec["end"] - spec["start"] - total, 2),
        "zooms_at": [round(p, 2) for p in peaks],
        "words": len(words),
    }
    (clip_dir / "render.json").write_text(json.dumps(report, indent=2))
    shutil.copy(ass, clip_dir / "captions.ass")
    return {"video": out, **report}


def caption_with_tags(spec: dict) -> str:
    caption = spec.get("caption", "")
    for tag in (spec.get("campaign") or {}).get("required_tags", []):
        if tag.lower() not in caption.lower():
            caption = f"{caption} {tag}".strip()
    return caption


def post(clip_dir: Path, scheduled_date: str | None = None, platforms=("tiktok",)) -> dict:
    from .. import post as poster

    spec = load(clip_dir)
    caption = caption_with_tags(spec)
    results = {}
    for platform in platforms:
        results[platform] = poster.publish(platform, clip_dir / "tiktok.mp4", caption, scheduled_date,
                                           user=config.CLIPS_UPLOAD_POST_USER, ai_generated=False)
    (clip_dir / "posted.json").write_text(json.dumps(results, indent=2))
    return results

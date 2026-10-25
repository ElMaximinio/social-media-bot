"""Turn a source moment into a finished 9:16 clip with FFmpeg.

Steps: cut the moment, drop dead air, reframe (stack, track or fit), punch-in zooms on loud
moments, word-by-word captions, a hook title on top and an optional credit line.
"""
import re
import subprocess
from pathlib import Path

import numpy as np

from ..edit import duration, has_audio, run
from . import layout

W, H, FPS = 1080, 1920, 30
TOP_H = 800          # facecam panel height in the stack layout
FONT = "Inter Display Black"
YELLOW = "&H0000E5FF&"  # ASS colours are BGR


# ---------- audio ----------

def loudness(path: Path, rate: int = 100) -> np.ndarray:
    """RMS level per 1/rate second, 0..1."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    pcm = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 16000 // rate
    n = len(pcm) // hop
    if n == 0:
        return np.zeros(0)
    return np.sqrt((pcm[:n * hop].reshape(n, hop) ** 2).mean(axis=1))


def loud_peaks(level: np.ndarray, rate: int = 100, max_peaks: int = 4, min_gap: float = 5.0,
               skip_start: float = 1.5) -> list[float]:
    """Times of the loudest moments (shouts, big reactions), spaced apart."""
    if len(level) == 0:
        return []
    win = max(int(0.3 * rate), 1)
    smooth = np.convolve(level, np.ones(win) / win, mode="same")
    floor = np.median(smooth) + 1.5 * smooth.std()
    order = np.argsort(-smooth)
    peaks: list[float] = []
    for i in order:
        if smooth[i] < floor or len(peaks) >= max_peaks:
            break
        t = i / rate
        if t < skip_start or any(abs(t - p) < min_gap for p in peaks):
            continue
        peaks.append(float(t))
    return sorted(peaks)


# ---------- dead air ----------

def keep_ranges(words: list[dict], total: float, level: np.ndarray | None = None, rate: int = 100,
                max_gap: float = 0.8, pad: float = 0.15) -> list[tuple[float, float]]:
    """Parts of the clip to keep. A gap between words is cut only if it is long and quiet,
    so screams, laughs and game sound with no words are kept."""
    if not words:
        return [(0.0, total)]
    speech = np.median(level) if level is not None and len(level) else 0
    ranges = [[0.0, min(words[0]["end"] + pad, total)]]
    for prev, w in zip(words, words[1:]):
        gap_start, gap_end = prev["end"] + pad, w["start"] - pad
        quiet = True
        if level is not None and len(level) and gap_end > gap_start:
            seg = level[int(gap_start * rate):int(gap_end * rate)]
            quiet = len(seg) == 0 or seg.max() < max(speech * 1.2, 0.02)
        if gap_end - gap_start > max_gap and quiet:
            ranges.append([gap_end, w["end"] + pad])
        else:
            ranges[-1][1] = w["end"] + pad
    ranges[-1][1] = total
    return [(round(a, 3), round(min(b, total), 3)) for a, b in ranges if b > a]


def subtract(ranges, cuts) -> list[tuple[float, float]]:
    """Remove the cut intervals from the keep ranges."""
    out = list(ranges)
    for ca, cb in cuts:
        nxt = []
        for a, b in out:
            if cb <= a or ca >= b:
                nxt.append((a, b))
                continue
            if ca > a:
                nxt.append((a, ca))
            if cb < b:
                nxt.append((cb, b))
        out = nxt
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > 0.05]


def remap(t: float, ranges: list[tuple[float, float]]) -> float | None:
    """Time in the tightened clip for time t in the original, or None if t was cut."""
    out = 0.0
    for a, b in ranges:
        if t < a:
            return None
        if t <= b:
            return out + t - a
        out += b - a
    return None


def remap_words(words: list[dict], ranges) -> list[dict]:
    out = []
    for w in words:
        s, e = remap(w["start"], ranges), remap(w["end"], ranges)
        if s is None or e is None:
            continue
        out.append({"word": w["word"], "start": round(s, 3), "end": round(e, 3)})
    return out


def tighten(src: Path, ranges, dest: Path) -> Path:
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)
    vf = f"select='{sel}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{sel}',asetpts=N/SR/TB"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf]
    if has_audio(src):
        cmd += ["-af", af, "-c:a", "aac", "-b:a", "192k"]
    run(cmd + ["-c:v", "libx264", "-preset", "fast", "-crf", "16", "-r", str(FPS), str(dest)])
    return dest


# ---------- captions ----------

def clean_text(s: str) -> str:
    """libass cannot draw colour emoji, so burned-in text keeps plain characters only."""
    s = re.sub(r"[\U00010000-\U0010FFFF☀-➿️]", "", s)
    return s.replace("{", "(").replace("}", ")").replace("\\", "/").strip()


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def group_words(words: list[dict], max_words: int = 3, max_chars: int = 16, max_pause: float = 0.5):
    groups, cur = [], []
    for w in words:
        text = " ".join(x["word"] for x in cur + [w])
        if cur and (len(cur) >= max_words or len(text) > max_chars or w["start"] - cur[-1]["end"] > max_pause):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def write_ass(words: list[dict], path: Path, total: float, caption_y: int, hook: str = "",
              hook_until: float | None = None, credit: str = "") -> Path:
    """Word-by-word captions (spoken word in yellow, each group pops in), hook title, credit."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,7,3,5,60,60,0,1
Style: Hook,{FONT},70,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,230,1
Style: Credit,Inter SemiBold,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,8,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    pos = f"\\pos({W // 2},{caption_y})"
    groups = group_words(words)
    for gi, g in enumerate(groups):
        g_end = g[-1]["end"] + 0.25
        if gi + 1 < len(groups):
            g_end = min(g_end, groups[gi + 1][0]["start"])
        for i, w in enumerate(g):
            start = w["start"] if i else g[0]["start"]
            end = g[i + 1]["start"] if i + 1 < len(g) else g_end
            parts = []
            for j, x in enumerate(g):
                t = clean_text(x["word"]).upper()
                parts.append(f"{{\\c{YELLOW}}}{t}{{\\c&H00FFFFFF&}}" if j == i else t)
            pop = "\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)" if i == 0 else ""
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{{pos}{pop}}}{' '.join(parts)}")
    hook = "\\N".join(x for x in (clean_text(p) for p in hook.split("\\N")) if x)
    if hook:
        end = total if hook_until is None else min(hook_until, total)
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(end)},Hook,,0,0,0,,{{\\fad(0,200)}}{hook}")
    credit = clean_text(credit)
    if credit:
        y = 230 + 86 * (hook.count("\\N") + 1) + 40 if hook else 230
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(total)},Credit,,0,0,0,,{{\\pos({W // 2},{y})}}{credit}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def wrap_hook(hook: str, max_chars: int = 22) -> str:
    """Break the hook into lines of about max_chars for the white title box."""
    words, lines, cur = clean_text(hook).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\\N".join(lines)


# ---------- zoom ----------

def zoom_expr(peaks: list[float], amount: float = 0.12, ease: float = 0.12, hold: float = 0.9,
              intro: float = 0.08) -> str:
    """Zoom factor over t: a short push-out at the start and a quick punch-in on each peak."""
    terms = [f"{intro}*max(0,1-t/0.5)"] if intro else []
    for p in peaks:
        a, b, c, d = p - ease, p, p + hold, p + hold + 0.35
        terms.append(f"{amount}*if(between(t,{a:.2f},{b:.2f}),(t-{a:.2f})/{ease},"
                     f"if(between(t,{b:.2f},{c:.2f}),1,if(between(t,{c:.2f},{d:.2f}),1-(t-{c:.2f})/0.35,0)))")
    return "1+" + "+".join(terms) if terms else "1"


# ---------- compose ----------

def layout_filter(kind: str, src_w: int, src_h: int, faces: dict | None,
                  box: list[int] | None = None) -> tuple[str, int]:
    """Filter chain from [0:v] to [base] at W x H, and the y of the caption line.
    box (x, y, w, h in source pixels) limits the fit layout to one area, e.g. to keep a prop in frame."""
    if kind == "stack":
        fx, fy, fw, fh = layout.facecam_box(faces, src_w, src_h, W / TOP_H)
        game_h = H - TOP_H
        gx = layout.gameplay_x(faces, src_w, src_h, W / game_h)
        return (f"[0:v]split=2[cam][game];"
                f"[cam]crop={fw}:{fh}:{fx}:{fy},scale={W}:{TOP_H}[top];"
                f"[game]crop={int(src_h * W / game_h) // 2 * 2}:{src_h}:{gx}:0,scale={W}:{game_h},setsar=1[bot];"
                f"[top][bot]vstack[base]"), TOP_H
    if kind == "track":
        scale_h = H
        scale_w = int(round(src_w * H / src_h / 2) * 2)
        if scale_w < W:
            scale_w, scale_h = W, int(round(src_h * W / src_w / 2) * 2)
        keys = layout.track_keyframes(faces, scale_w, W) if faces else [(0, (scale_w - W) / 2)]
        x = layout.piecewise_expr(keys)
        return (f"[0:v]scale={scale_w}:{scale_h},crop={W}:{H}:'{x}':(ih-{H})/2[base]"), int(H * 0.68)
    # fit: whole frame (or the box) over a blurred, zoomed copy
    bx, by, bw, bh = box or (0, 0, src_w, src_h)
    panel_h = min(int(round(bh * W / bw / 2) * 2), int(H * 0.62) // 2 * 2)
    panel_w = min(W, int(round(bw * panel_h / bh / 2) * 2))
    caption_y = min(H // 2 + panel_h // 2 + 110, int(H * 0.78))
    return (f"[0:v]split=2[bg][fg];"
            f"[bg]scale=-2:{H},crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12[bgb];"
            f"[fg]crop={bw}:{bh}:{bx}:{by},scale={panel_w}:{panel_h},setsar=1[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[base]"), caption_y


def compose(src: Path, dest: Path, kind: str, faces: dict | None, ass: Path, peaks: list[float],
            box: list[int] | None = None) -> Path:
    src_w, src_h = layout.video_size(src)
    chain, _ = layout_filter(kind, src_w, src_h, faces, box)
    z = zoom_expr(peaks)
    ass_path = str(ass).replace(":", "\\:").replace("'", "\\'")
    vf = (f"{chain};[base]fps={FPS},scale=w='trunc({W}*({z})/2)*2':h='trunc({H}*({z})/2)*2':eval=frame,"
          f"crop={W}:{H},setsar=1,ass='{ass_path}'[v]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if has_audio(src):
        af = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        maps = ["-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
    else:
        af, maps = None, ["-map", "[v]"]
    graph = vf + (";" + af if af else "")
    run(cmd + ["-filter_complex", graph] + maps +
        ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(dest)])
    return dest


def cut(source: Path, start: float, end: float, dest: Path) -> Path:
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
         "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", str(dest)])
    return dest

"""Find faces in the source and choose how to fit a 16:9 stream into 9:16.

Layouts:
  stack  facecam on top, gameplay below (streamers with a small webcam overlay)
  track  one 9:16 crop that follows the speaker (IRL, podcasts, just chatting)
  fit    whole frame in the middle over a blurred copy (no face found)
"""
import subprocess
from pathlib import Path

import numpy as np

MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"
SAMPLE_EVERY = 0.5  # seconds between analysed frames
ANALYSE_W = 640


def video_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def sample_frames(path: Path, every: float = SAMPLE_EVERY):
    """Yield (t, frame) at a low resolution, decoded by ffmpeg."""
    w, h = video_size(path)
    aw, ah = ANALYSE_W, int(round(ANALYSE_W * h / w / 2) * 2)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf",
                             f"fps={1 / every},scale={aw}:{ah}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE)
    i, size = 0, aw * ah * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield i * every, np.frombuffer(buf, np.uint8).reshape(ah, aw, 3)
        i += 1
    proc.wait()


def detect_faces(path: Path, every: float = SAMPLE_EVERY) -> dict:
    """Faces per sampled frame, as fractions of the frame: [(t, [(x, y, w, h, score), ...]), ...]."""
    import cv2

    det = None
    samples = []
    for t, frame in sample_frames(path, every):
        fh, fw = frame.shape[:2]
        if det is None:
            det = cv2.FaceDetectorYN.create(str(MODEL), "", (fw, fh), score_threshold=0.75)
        _, faces = det.detect(frame)
        found = []
        for f in faces if faces is not None else []:
            x, y, w, h, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
            found.append((x / fw, y / fh, w / fw, h / fh, score))
        samples.append((t, sorted(found, key=lambda b: -b[2] * b[3])))
    return {"every": every, "samples": samples}


def _main_faces(samples):
    return [(t, faces[0]) for t, faces in samples if faces]


def choose_layout(faces: dict) -> str:
    samples = faces["samples"]
    if not samples:
        return "fit"
    main = _main_faces(samples)
    if len(main) < 0.4 * len(samples):
        return "fit"
    heights = np.array([f[3] for _, f in main])
    if np.median(heights) < 0.2:
        # Small face that stays in one place: a webcam overlay on top of gameplay.
        cx = np.array([f[0] + f[2] / 2 for _, f in main])
        cy = np.array([f[1] + f[3] / 2 for _, f in main])
        if cx.std() < 0.05 and cy.std() < 0.05:
            return "stack"
        return "fit"
    return "track"


def facecam_box(faces: dict, src_w: int, src_h: int, panel_aspect: float) -> tuple[int, int, int, int]:
    """Crop box (x, y, w, h) in source pixels around the webcam, with the panel's aspect ratio."""
    main = [f for _, f in _main_faces(faces["samples"])]
    x, y, w, h = (float(np.median([f[i] for f in main])) for i in range(4))
    cx, cy = (x + w / 2) * src_w, (y + h / 2) * src_h
    bw = w * src_w * 3.2  # head plus shoulders, about what a webcam frame shows
    bh = bw / panel_aspect
    bw, bh = min(bw, src_w), min(bh, src_h)
    if bw / bh > panel_aspect:
        bw = bh * panel_aspect
    else:
        bh = bw / panel_aspect
    bx = min(max(cx - bw / 2, 0), src_w - bw)
    by = min(max(cy - bh / 2 + bh * 0.08, 0), src_h - bh)
    return int(bx) // 2 * 2, int(by) // 2 * 2, int(bw) // 2 * 2, int(bh) // 2 * 2


def gameplay_x(faces: dict, src_w: int, src_h: int, panel_aspect: float) -> int:
    """Left edge of the gameplay crop (full height), moved off the webcam when possible."""
    crop_w = int(src_h * panel_aspect)
    centre = (src_w - crop_w) / 2
    main = [f for _, f in _main_faces(faces["samples"])]
    if not main:
        return int(centre) // 2 * 2
    x, w = float(np.median([f[0] for f in main])), float(np.median([f[2] for f in main]))
    cam_l, cam_r = (x - w * 5) * src_w, (x + w * 6) * src_w  # webcam edges, generously
    left, right = centre, centre + crop_w
    if right > cam_l and left < cam_r:  # overlap: slide away, but keep the frame centre in view
        if (cam_l + cam_r) / 2 < src_w / 2:
            left = min(max(cam_r, centre), src_w / 2, src_w - crop_w)
        else:
            left = max(min(cam_l - crop_w, centre), src_w / 2 - crop_w, 0)
    return int(left) // 2 * 2


def track_keyframes(faces: dict, src_w: int, crop_w: int, dead_zone: float = 0.12,
                    move_time: float = 0.4) -> list[tuple[float, float]]:
    """Crop left edge over time [(t, x)], moving only when the speaker leaves a dead zone."""
    max_x = src_w - crop_w
    centre = lambda fx: min(max(fx * src_w - crop_w / 2, 0), max_x)
    main = _main_faces(faces["samples"])
    if not main:
        return [(0.0, max_x / 2)]
    x = centre(main[0][1][0] + main[0][1][2] / 2)
    keys = [(0.0, x)]
    for t, f in main[1:]:
        target = centre(f[0] + f[2] / 2)
        if abs(target - x) > dead_zone * crop_w and t >= keys[-1][0] + move_time:
            keys.append((t, x))
            keys.append((t + move_time, target))
            x = target
    return keys


def piecewise_expr(keys: list[tuple[float, float]]) -> str:
    """FFmpeg expression in t that holds or moves linearly between keyframes."""
    if len(keys) == 1:
        return f"{keys[0][1]:.1f}"
    expr = f"{keys[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        if x0 == x1 or t1 <= t0:
            seg = f"{x0:.1f}"
        else:
            seg = f"{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.3f})/{t1 - t0:.3f}"
        expr = f"if(lt(t,{t1:.3f}),{seg},{expr})"
    return expr

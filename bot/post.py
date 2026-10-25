"""Publish the cuts through Upload-Post, with the AI-generated label always on."""
import json
import uuid
from pathlib import Path

import requests

from . import config

URL = "https://api.upload-post.com/api/upload"


def publish(platform: str, video: Path, caption: str, scheduled_date: str | None = None,
            timezone: str = "Europe/Paris") -> dict:
    key = config.require("UPLOAD_POST_API_KEY")
    fields = {
        "user": config.UPLOAD_POST_USER,
        "platform[]": platform,
        "title": caption,
        f"{platform}_title": caption,
        "is_ai_generated": "true",
        "async_upload": "true",
    }
    if platform == "tiktok":
        fields["is_aigc"] = "true"
    if platform == "x":
        fields["made_with_ai"] = "true"
    if scheduled_date:
        fields["scheduled_date"] = scheduled_date
        fields["timezone"] = timezone
    with open(video, "rb") as f:
        r = requests.post(URL, headers={"Authorization": f"Apikey {key}",
                                        "Idempotency-Key": str(uuid.uuid4())},
                          data=fields, files={"video": (video.name, f, "video/mp4")}, timeout=600)
    r.raise_for_status()
    return r.json()


def publish_episode(ep_dir: Path, scheduled_date: str | None = None) -> dict:
    ep = json.loads((ep_dir / "episode.json").read_text())
    results = {}
    for platform in ("tiktok", "instagram", "x"):
        results[platform] = publish(platform, ep_dir / f"{platform}.mp4",
                                    ep["captions"][platform], scheduled_date)
    (ep_dir / "posted.json").write_text(json.dumps(results, indent=2))
    return results

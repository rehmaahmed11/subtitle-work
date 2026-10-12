"""Locate a working FFmpeg binary (bundled imageio-ffmpeg, then PATH)."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    override = os.environ.get("FFMPEG_BINARY")
    if override and os.path.isfile(override):
        return override
    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FFmpegError(
        "FFmpeg not found. Install ffmpeg or `pip install imageio-ffmpeg`."
    )


def run_ffmpeg(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg timed out: {' '.join(cmd[:8])}…") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2500:]
        raise FFmpegError(f"FFmpeg failed ({proc.returncode}):\n{tail}")
    return proc


def probe_duration(path: str) -> float | None:
    """Best-effort duration in seconds via ffmpeg -i parsing."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-i", path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = (proc.stderr or "") + (proc.stdout or "")
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s

"""SRT parse/compose that never mutates timestamps."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import srt

_TS = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def parse_srt(text: str) -> list[srt.Subtitle]:
    cleaned = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    subs = list(srt.parse(cleaned, ignore_errors=True))
    subs.sort(key=lambda x: x.start)
    for i, sub in enumerate(subs, 1):
        sub.index = i
        sub.content = (sub.content or "").strip()
    return [s for s in subs if s.content]


def load_srt(path: str | Path) -> list[srt.Subtitle]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    return parse_srt(raw)


def compose_srt(subs: list[srt.Subtitle], *, include_proprietary: bool = False) -> str:
    ordered = []
    for i, sub in enumerate(subs, 1):
        ordered.append(
            srt.Subtitle(
                index=i,
                start=sub.start,
                end=sub.end,
                content=(sub.content or "").strip(),
                proprietary=(getattr(sub, "proprietary", "") if include_proprietary else ""),
            )
        )
    return srt.compose(ordered)


def save_srt(subs: list[srt.Subtitle], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(compose_srt(subs), encoding="utf-8")
    return path


def timedelta_to_ass(t: dt.timedelta) -> str:
    total = t.total_seconds()
    if total < 0:
        total = 0.0
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total % 60
    # ASS uses centiseconds
    return f"{h}:{m:02d}:{s:05.2f}"


def seconds_to_td(sec: float) -> dt.timedelta:
    if sec < 0:
        sec = 0.0
    return dt.timedelta(seconds=float(sec))

"""Extract audio from a video and transcribe Turkish speech → timed SRT.

Uses faster-whisper (CTranslate2). Word-level timestamps are grouped into
readable cues without shifting the spoken start/end times.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import srt

from .ffmpeg_util import run_ffmpeg
from .srt_io import seconds_to_td


class TranscribeError(RuntimeError):
    pass


def extract_audio(video_path: str | Path, wav_path: str | Path) -> Path:
    wav_path = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]
    )
    if not wav_path.exists() or wav_path.stat().st_size < 64:
        raise TranscribeError("Audio extraction produced an empty file.")
    return wav_path


def _load_model(model_size: str, download_root: str | None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscribeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc
    kwargs = {
        "device": "cpu",
        "compute_type": "int8",
    }
    if download_root:
        kwargs["download_root"] = download_root
    try:
        return WhisperModel(model_size, **kwargs)
    except Exception as exc:
        raise TranscribeError(
            "Could not load the Whisper model "
            f"'{model_size}'. Provide a Turkish SRT instead, or allow the "
            f"model download. Detail: {exc}"
        ) from exc


def transcribe_turkish(
    audio_path: str | Path,
    *,
    model_size: str = "small",
    download_root: str | None = None,
    vad_filter: bool = True,
    progress=None,
) -> list[srt.Subtitle]:
    model = _load_model(model_size, download_root)
    try:
        segments, info = model.transcribe(
            str(audio_path),
            language="tr",
            task="transcribe",
            word_timestamps=True,
            vad_filter=vad_filter,
            beam_size=5,
            condition_on_previous_text=True,
        )
    except Exception as exc:
        raise TranscribeError(f"Whisper transcription failed: {exc}") from exc

    subs: list[srt.Subtitle] = []
    for i, seg in enumerate(segments, 1):
        text = (seg.text or "").strip()
        if not text:
            continue
        start = seconds_to_td(float(seg.start or 0.0))
        end = seconds_to_td(float(seg.end or 0.0))
        if end <= start:
            end = start + dt.timedelta(milliseconds=400)
        # Prefer word-level bounds when present (more accurate)
        words = getattr(seg, "words", None) or []
        if words:
            ws = [w for w in words if w.start is not None and w.end is not None]
            if ws:
                start = seconds_to_td(float(ws[0].start))
                end = seconds_to_td(float(ws[-1].end))
                text = " ".join((w.word or "").strip() for w in ws).strip() or text
        for cue in _pack_cue(i, start, end, text):
            subs.append(cue)
        if progress:
            progress(i, text)

    # Re-index after packing
    for i, sub in enumerate(subs, 1):
        sub.index = i
    if not subs:
        raise TranscribeError(
            "No Turkish speech was recognised. Try a larger Whisper model "
            "or supply an SRT file."
        )
    return subs


_MAX_CHARS = 42
_MAX_LINES = 2


def _pack_cue(index: int, start: dt.timedelta, end: dt.timedelta, text: str) -> list[srt.Subtitle]:
    """Split overlong segments at punctuation, keeping overall time span."""
    text = re_ws(text)
    if len(text) <= _MAX_CHARS * _MAX_LINES:
        return [srt.Subtitle(index=index, start=start, end=end, content=_wrap(text))]

    chunks = _split_text(text)
    if len(chunks) == 1:
        return [srt.Subtitle(index=index, start=start, end=end, content=_wrap(text))]

    total = (end - start).total_seconds()
    weights = [max(len(c), 1) for c in chunks]
    wsum = sum(weights) or 1
    out = []
    cursor = start.total_seconds()
    for i, chunk in enumerate(chunks):
        dur = total * (weights[i] / wsum)
        st = seconds_to_td(cursor)
        et = seconds_to_td(cursor + dur) if i < len(chunks) - 1 else end
        if et <= st:
            et = st + dt.timedelta(milliseconds=300)
        out.append(srt.Subtitle(index=index, start=st, end=et, content=_wrap(chunk)))
        cursor = et.total_seconds()
    return out


def re_ws(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text).strip()


def _wrap(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    # split near the middle on a space
    mid = len(text) // 2
    sp = text.rfind(" ", 0, _MAX_CHARS)
    if sp < 8:
        sp = text.find(" ", mid)
    if sp < 0:
        return text
    return text[:sp].strip() + "\n" + text[sp:].strip()


def _split_text(text: str) -> list[str]:
    import re

    parts = re.split(r"(?<=[.!?…;:])\s+", text)
    chunks: list[str] = []
    buf = ""
    limit = _MAX_CHARS * _MAX_LINES
    for p in parts:
        if not p:
            continue
        if not buf:
            buf = p
        elif len(buf) + 1 + len(p) <= limit:
            buf = buf + " " + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    # further split leftovers
    final: list[str] = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            words = c.split()
            buf = ""
            for w in words:
                if not buf:
                    buf = w
                elif len(buf) + 1 + len(w) <= limit:
                    buf += " " + w
                else:
                    final.append(buf)
                    buf = w
            if buf:
                final.append(buf)
    return final or [text]

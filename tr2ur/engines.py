"""Free vs paid model catalogues.

Free tier fires *every* no-key backend in parallel (Google unofficial,
MyMemory, LibreTranslate, built-in lexicon) and votes. Paid tier uses
OpenAI Whisper-1 for speech and GPT for idiom-aware Urdu.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

ARABIC = re.compile(r"[\u0600-\u06FF]")

FREE_STT = [
    {
        "id": "whisper-small",
        "label": "Whisper small (local)",
        "role": "audio → Turkish SRT",
    },
    {
        "id": "whisper-base",
        "label": "Whisper base (local fallback)",
        "role": "audio → Turkish SRT",
    },
    {
        "id": "whisper-tiny",
        "label": "Whisper tiny (local fallback)",
        "role": "audio → Turkish SRT",
    },
]

FREE_MT = [
    {
        "id": "glossary",
        "label": "Idiom / title / honorific glossary",
        "role": "lock phrases before MT",
    },
    {
        "id": "google",
        "label": "Google Translate (free)",
        "role": "Turkish → Urdu",
    },
    {
        "id": "mymemory",
        "label": "MyMemory (free)",
        "role": "Turkish → Urdu",
    },
    {
        "id": "libre",
        "label": "LibreTranslate (free)",
        "role": "Turkish → Urdu",
    },
    {
        "id": "lexicon",
        "label": "Offline lexicon",
        "role": "always-on fallback",
    },
]

PAID_STT = [
    {
        "id": "openai-whisper-1",
        "label": "OpenAI Whisper-1",
        "role": "audio → Turkish SRT",
    },
]

PAID_MT = [
    {
        "id": "gpt-4o-mini",
        "label": "GPT-4o mini",
        "role": "idiom-aware Urdu",
    },
    {
        "id": "gpt-4o",
        "label": "GPT-4o",
        "role": "highest quality Urdu",
    },
]


def looks_urdu(text: str) -> bool:
    if not text or not text.strip():
        return False
    return bool(ARABIC.search(text))


def _safe(fn: Callable[[str], str | None], text: str) -> str | None:
    try:
        out = fn(text)
    except Exception:
        return None
    if not out:
        return None
    out = out.strip()
    return out if looks_urdu(out) else None


def google_free(text: str) -> str | None:
    from deep_translator import GoogleTranslator

    return GoogleTranslator(source="tr", target="ur").translate(text)


def mymemory_free(text: str) -> str | None:
    from deep_translator import MyMemoryTranslator

    return MyMemoryTranslator(source="tr", target="ur").translate(text)


def libre_free(text: str) -> str | None:
    from deep_translator import LibreTranslator

    for url in (
        "https://libretranslate.de",
        "https://translate.argosopentech.com",
        "https://libretranslate.com",
    ):
        try:
            out = LibreTranslator(
                source="tr", target="ur", custom_url=url
            ).translate(text)
            if out and looks_urdu(out):
                return out
        except Exception:
            continue
    return None


FREE_MT_CALLS: list[tuple[str, Callable[[str], str | None]]] = [
    ("google", google_free),
    ("mymemory", mymemory_free),
    ("libre", libre_free),
]

_DEAD: set[str] = set()
_PREF = {"google": 0, "mymemory": 1, "libre": 2, "lexicon": 3}


def run_all_free_mt(
    text: str,
    *,
    offline_fn: Callable[[str], str] | None = None,
    timeout: float = 8.0,
) -> tuple[str | None, str, dict[str, str | None]]:
    """Query every free MT backend in parallel and majority-vote.

    Returns (urdu, winner_name, raw_map).
    """
    raw: dict[str, str | None] = {}
    if not text.strip() or re.fullmatch(r"⟦P\d+⟧", text.strip()):
        if offline_fn:
            off = offline_fn(text)
            raw["lexicon"] = off
            return off, "lexicon", raw
        return text, "passthrough", raw

    live = [(n, f) for n, f in FREE_MT_CALLS if n not in _DEAD]
    if live:
        with ThreadPoolExecutor(max_workers=len(live)) as pool:
            futs = {pool.submit(_safe, fn, text): name for name, fn in live}
            try:
                for fut in as_completed(futs, timeout=timeout):
                    name = futs[fut]
                    try:
                        raw[name] = fut.result()
                    except Exception:
                        raw[name] = None
                        _DEAD.add(name)
            except Exception:
                for fut, name in futs.items():
                    if name not in raw:
                        raw[name] = None

    if offline_fn is not None:
        try:
            raw["lexicon"] = offline_fn(text)
        except Exception:
            raw["lexicon"] = None

    # Majority vote on Arabic-script outputs (ignore lexicon for the vote
    # unless nobody else answered — lexicon is the safety net).
    counts: dict[str, list[str]] = {}
    for name, val in raw.items():
        if name == "lexicon" or not val:
            continue
        key = re.sub(r"\s+", " ", val).strip()
        counts.setdefault(key, []).append(name)

    if counts:
        best = max(
            counts.items(),
            key=lambda kv: (
                len(kv[1]),
                -min(_PREF.get(n, 9) for n in kv[1]),
            ),
        )
        winner = best[1][0]
        if len(best[1]) > 1:
            winner = "vote:" + "+".join(sorted(best[1], key=lambda n: _PREF.get(n, 9)))
        return best[0], winner, raw

    # Preference order if no majority
    for name in ("google", "mymemory", "libre", "lexicon"):
        if raw.get(name):
            return raw[name], name, raw
    return None, "none", raw


GPT_SYSTEM = """You are a professional Turkish → Urdu subtitle translator for film and television.

Rules:
- Return ONLY the Urdu subtitle text. No numbering, no quotes, no notes.
- Keep proper names in their original Latin/Turkish form (Ahmet, Zeynep, Istanbul).
- Honorifics: Bey → صاحب, Hanım/Hanımefendi → صاحبہ / محترمہ, Paşa → پاشا, Hoca → استاد, Efendi → افندی.
- Title cards (BÖLÜM, SEZON, ALL CAPS) become short Urdu titles (قسط, سیزن), not dialogue.
- Turkish idioms must become natural Urdu idioms, never word-for-word.
  Examples: İş işten geçti → اب دیر ہو چکی; Yerin kulağı var → دیواروں کے بھی کان ہوتے ہیں.
- Islamic formulae stay canonical: İnşallah → ان شاء اللہ, Maşallah → ما شاء اللہ, Selamün aleyküm → السلام علیکم.
- Placeholders like ⟦P1⟧ must be copied unchanged.
- Keep the same number of lines as the input cue. Do not add or drop meaning.
"""


def openai_translate(text: str, api_key: str, model: str = "gpt-4o-mini") -> str | None:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": GPT_SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    out = (resp.choices[0].message.content or "").strip()
    # strip accidental wrapping quotes
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'“”":
        out = out[1:-1].strip()
    return out or None


def openai_translate_batch(
    lines: list[str], api_key: str, model: str = "gpt-4o-mini"
) -> list[str | None]:
    """Translate many cues in one call. Returns one item per input line."""
    from openai import OpenAI

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(lines))
    prompt = (
        "Translate each numbered Turkish subtitle into Urdu. "
        "Reply with the same numbers, one cue per line, Urdu only.\n\n"
        + numbered
    )
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": GPT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    body = resp.choices[0].message.content or ""
    found: dict[int, str] = {}
    for raw in body.splitlines():
        m = re.match(r"\s*(\d+)\.\s*(.*)$", raw)
        if not m:
            continue
        found[int(m.group(1))] = m.group(2).strip()
    return [found.get(i + 1) for i in range(len(lines))]


def openai_transcribe(audio_path: str, api_key: str):
    """Whisper-1 verbose JSON with segment timestamps."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as fh:
        return client.audio.transcriptions.create(
            model="whisper-1",
            file=fh,
            language="tr",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )


def resolve_openai_key(explicit: str | None) -> str | None:
    key = (explicit or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    return key or None


def catalogue() -> dict:
    return {
        "free": {"stt": FREE_STT, "mt": FREE_MT},
        "paid": {"stt": PAID_STT, "mt": PAID_MT},
    }

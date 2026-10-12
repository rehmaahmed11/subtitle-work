"""Prepare Urdu text for on-screen rendering (shaping + bidi)."""

from __future__ import annotations

import re

import arabic_reshaper
from bidi.algorithm import get_display

_RESHAPER = arabic_reshaper.ArabicReshaper(
    configuration={
        "delete_harakat": False,
        "support_ligatures": True,
        "use_unshaped_instead_of_isolated": True,
    }
)


def contains_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" for ch in text)


def shape_urdu(text: str) -> str:
    """Logical Urdu → visual order for engines that do not run FriBidi."""
    if not text or not contains_arabic(text):
        return text
    lines = text.split("\n")
    out = []
    for line in lines:
        reshaped = _RESHAPER.reshape(line)
        out.append(get_display(reshaped))
    return "\n".join(out)


RLM = "\u200F"


def prepare_ass_text(text: str) -> str:
    """Logical Urdu for libass: Arabic punctuation + RTL paragraph mark.

    libass runs FriBidi/HarfBuzz, so we must NOT pre-shape. Starting a cue
    with a Latin name would otherwise flip the whole line to LTR.
    """
    if not text or not contains_arabic(text):
        return text
    t = (
        text.replace("?", "؟")
        .replace(";", "؛")
        .replace(",", "،")
    )
    t = re.sub(r"\.(?=\s|$)", "۔", t)
    return RLM + t

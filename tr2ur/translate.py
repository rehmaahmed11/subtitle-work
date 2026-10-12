"""Turkish subtitle text → Urdu, with title/idiom/honorific care.

Pipeline per cue:
  1. Detect title cards and SFX brackets.
  2. Protect Islamic phrases, honorifics + names, and idioms (longest match).
  3. Try Google Translate (when the network allows).
  4. Fall back to the offline phrase/lexicon matcher (Turkish is SOV like Urdu).
  5. Restore protected tokens. Timestamps are never touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .glossary import HONORIFICS, IDIOMS, ISLAMIC, PHRASES, SFX, TITLE_WORDS
from .lexicon import WORDS

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover
    GoogleTranslator = None  # type: ignore


# Longest-first combined phrase table
def _fold_map(src: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in src.items():
        out[_norm(k)] = v
    return out


def _norm(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("i̇", "i")  # composed dotted i
    t = (
        t.replace("â", "a")
        .replace("î", "i")
        .replace("û", "u")
    )
    t = re.sub(r"\s+", " ", t)
    return t


PHRASE_TABLE: dict[str, str] = {}
for table in (IDIOMS, PHRASES, ISLAMIC, TITLE_WORDS, SFX):
    PHRASE_TABLE.update(_fold_map(table))
# longer keys must win at lookup time; we sort by length at match
_PHRASE_KEYS = sorted(PHRASE_TABLE.keys(), key=lambda s: len(s.split()), reverse=True)
_MAX_PHRASE = max((len(k.split()) for k in _PHRASE_KEYS), default=1)

WORD_TABLE = _fold_map(WORDS)
HONOR_TABLE = _fold_map(HONORIFICS)

# Common Turkish inflectional tails, longest first. Conservative: stem must remain >= 3.
_SUFFIXES = sorted(
    {
        "acaklarını",
        "eceklerini",
        "acaklar",
        "ecekler",
        "acakmış",
        "ecekmiş",
        "mıyorsunuz",
        "miyorsunuz",
        "muyorsunuz",
        "müyorsunuz",
        "mıyorsun",
        "miyorsun",
        "muyorsun",
        "müyorsun",
        "ıyorsunuz",
        "iyorsunuz",
        "uyorsunuz",
        "üyorsunuz",
        "ıyorsun",
        "iyorsun",
        "uyorsun",
        "üyorsun",
        "mıyorum",
        "miyorum",
        "muyorum",
        "müyorum",
        "ıyorum",
        "iyorum",
        "uyorum",
        "üyorum",
        "ıyorlar",
        "iyorlar",
        "uyorlar",
        "üyorlar",
        "üyorlar",
        "üyor",
        "maktayız",
        "mekteyiz",
        "maktayım",
        "mekteyim",
        "malıyım",
        "meliyim",
        "malısın",
        "melisin",
        "malıdır",
        "melidir",
        "acağız",
        "eceğiz",
        "acağım",
        "eceğim",
        "acaksın",
        "eceksin",
        "acaklar",
        "ecekler",
        "acaktı",
        "ecekti",
        "mıyız",
        "miyiz",
        "muyuz",
        "müyüz",
        "mısın",
        "misin",
        "musun",
        "müsün",
        "madı",
        "medi",
        "madım",
        "medim",
        "madın",
        "medin",
        "madan",
        "meden",
        "makta",
        "mekte",
        "arken",
        "erken",
        "ınca",
        "ince",
        "unca",
        "ünce",
        "arak",
        "erek",
        "ıp",
        "ip",
        "up",
        "üp",
        "mıştı",
        "mişti",
        "muştu",
        "müştü",
        "lardı",
        "lerdi",
        "lardır",
        "lerdir",
        "larımız",
        "lerimiz",
        "larınız",
        "leriniz",
        "larının",
        "lerinin",
        "larını",
        "lerini",
        "lara",
        "lere",
        "larda",
        "lerde",
        "lardan",
        "lerden",
        "ların",
        "lerin",
        "ları",
        "leri",
        "ımız",
        "imiz",
        "umuz",
        "ümüz",
        "ınız",
        "iniz",
        "unuz",
        "ünüz",
        "sınız",
        "siniz",
        "sunuz",
        "sünüz",
        "ıyor",
        "iyor",
        "uyor",
        "üyor",
        "acak",
        "ecek",
        "mış",
        "miş",
        "muş",
        "müş",
        "dı",
        "di",
        "du",
        "dü",
        "tı",
        "ti",
        "tu",
        "tü",
        "ken",
        "lar",
        "ler",
        "dan",
        "den",
        "tan",
        "ten",
        "nın",
        "nin",
        "nun",
        "nün",
        "ın",
        "in",
        "un",
        "ün",
        "na",
        "ne",
        "ya",
        "ye",
        "yı",
        "yi",
        "yu",
        "yü",
        "sı",
        "si",
        "su",
        "sü",
        "ım",
        "im",
        "um",
        "üm",
        "ım",
        "da",
        "de",
        "ta",
        "te",
        "ça",
        "çe",
        "a",
        "e",
        "ı",
        "i",
        "u",
        "ü",
    },
    key=len,
    reverse=True,
)


_TITLE_HINT = re.compile(
    r"(?i)^\s*(önceki bölümde|önceki bölüm|bu bölümde|son bölüm|"
    r"özel bölüm|yeni bölüm|bölüm|sezon|sahne|başlık|fragman|"
    r"jenerik|yazan|yönetmen|oyuncular|senaryo)"
)
_SFX_WRAP = re.compile(r"^[\(\[\{♪🎵].*[\)\]\}♪🎵]$", re.S)


def is_title_card(text: str) -> bool:
    raw = text.strip()
    if not raw:
        return False
    if _TITLE_HINT.match(raw):
        return True
    letters = [c for c in raw if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = 0
    for c in letters:
        if c.isupper() or c in "İIŞĞÜÖÇ":
            # Capital I in Turkish all-caps is I/İ
            upper += 1
        elif c in "ıi":
            pass
    ratio = upper / len(letters)
    # ALL-CAPS title cards, not shouted dialogue (those usually have ! and are longer)
    if ratio >= 0.82 and len(letters) <= 48:
        return True
    return False


def is_sfx(text: str) -> bool:
    t = text.strip()
    return bool(_SFX_WRAP.match(t))


def _split_punct(token: str) -> tuple[str, str, str]:
    m = re.match(r"^(\W*)(.*?[A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû].*?)(\W*)$", token, re.S)
    if not m:
        return "", token, ""
    return m.group(1), m.group(2), m.group(3)


def _stem_lookup(word: str) -> str | None:
    n = _norm(word)
    if n in WORD_TABLE:
        return WORD_TABLE[n]
    if n in HONOR_TABLE:
        return HONOR_TABLE[n]
    if n in PHRASE_TABLE:
        return PHRASE_TABLE[n]
    body = n
    # Ali'nin / Ankara'da
    if "'" in body:
        base, _, _suf = body.partition("'")
        if base in WORD_TABLE:
            return WORD_TABLE[base]
        if len(base) >= 2 and base[0].isalpha() and base not in WORD_TABLE:
            return word.split("'")[0]  # keep proper name
    for suf in _SUFFIXES:
        if body.endswith(suf) and len(body) - len(suf) >= 3:
            stem = body[: -len(suf)]
            if stem in WORD_TABLE:
                return WORD_TABLE[stem]
            if stem in HONOR_TABLE:
                return HONOR_TABLE[stem]
    return None


def _is_probable_name(token: str) -> bool:
    if not token:
        return False
    core = token.strip(".,!?;:\"'“”«»")
    if len(core) < 2:
        return False
    if core[0].isupper() and not core.isupper():
        low = _norm(core)
        if low in WORD_TABLE or low in PHRASE_TABLE or low in HONOR_TABLE:
            return False
        return True
    return False


@dataclass
class TranslateResult:
    urdu: str
    method: str
    is_title: bool = False
    notes: list[str] = field(default_factory=list)


class Translator:
    def __init__(self, prefer_online: bool = True) -> None:
        self.prefer_online = prefer_online
        self._gt = None
        self._gt_failed = False
        self.stats = {"online": 0, "offline": 0, "titles": 0, "idioms": 0}

    def _google(self, text: str) -> str | None:
        if not self.prefer_online or self._gt_failed or GoogleTranslator is None:
            return None
        try:
            if self._gt is None:
                self._gt = GoogleTranslator(source="tr", target="ur")
            out = self._gt.translate(text)
            if out and out.strip():
                self.stats["online"] += 1
                return out.strip()
        except Exception:
            self._gt_failed = True
        return None

    def translate_text(self, text: str, *, title: bool | None = None) -> TranslateResult:
        original = text
        stripped = text.strip()
        if not stripped:
            return TranslateResult(urdu=text, method="empty")

        title_flag = is_title_card(stripped) if title is None else title
        sfx_flag = is_sfx(stripped)

        protected: dict[str, str] = {}
        working, idiom_hits = self._protect(stripped, protected)

        online = None
        if not sfx_flag:
            online = self._google(working)

        if online:
            rendered = self._restore(online, protected)
            method = "google"
        else:
            rendered = self._restore(self._offline(working), protected)
            method = "offline"
            self.stats["offline"] += 1

        if title_flag:
            self.stats["titles"] += 1
        if idiom_hits:
            self.stats["idioms"] += idiom_hits

        # Preserve surrounding whitespace / original line breaks count
        if original.endswith("\n"):
            rendered += "\n"
        return TranslateResult(
            urdu=rendered.strip() if not original.startswith(" ") else rendered,
            method=method,
            is_title=title_flag,
            notes=["sfx"] if sfx_flag else [],
        )

    def _protect(self, text: str, bucket: dict[str, str]) -> tuple[str, int]:
        """Replace idioms / islamic / honorifics with placeholders."""
        hits = 0
        n = 0

        def stash(ur: str) -> str:
            nonlocal n
            n += 1
            key = f"⟦P{n}⟧"
            bucket[key] = ur
            return key

        # SFX inner text
        def sfx_sub(m: re.Match) -> str:
            inner = m.group(2).strip()
            ur = PHRASE_TABLE.get(_norm(inner))
            if ur is None:
                ur = self._offline(inner)
            return m.group(1) + stash(ur) + m.group(3)

        text = re.sub(r"([\[\(\{])([^\]\)\}]+)([\]\)\}])", sfx_sub, text)

        words = _tokenize_keep(text)
        out: list[str] = []
        i = 0
        while i < len(words):
            kind, tok = words[i]
            if kind != "word":
                out.append(tok)
                i += 1
                continue

            # honorific: Name Honorific  OR Honorific
            nxt_words = _lookahead_words(words, i, _MAX_PHRASE)
            # try longest phrase
            matched = False
            for L in range(min(_MAX_PHRASE, len(nxt_words)), 0, -1):
                phrase = " ".join(_norm(w) for w in nxt_words[:L])
                if phrase in PHRASE_TABLE:
                    out.append(stash(PHRASE_TABLE[phrase]))
                    i += _skip_n_words(words, i, L)
                    hits += 1
                    matched = True
                    break
            if matched:
                continue

            # "Ahmet Bey" / "Zeynep Hanım"
            if i + 2 < len(words):
                # word, space, word
                pass
            name_hon = _match_name_honorific(words, i)
            if name_hon is not None:
                consumed, urdu = name_hon
                out.append(stash(urdu))
                i += consumed
                continue

            out.append(tok)
            i += 1
        return "".join(out), hits

    def _offline(self, text: str) -> str:
        if not text.strip():
            return text
        # If the whole remaining string is a placeholder, leave it
        if re.fullmatch(r"⟦P\d+⟧", text.strip()):
            return text

        words = _tokenize_keep(text)
        out: list[str] = []
        i = 0
        while i < len(words):
            kind, tok = words[i]
            if kind != "word":
                out.append(tok)
                i += 1
                continue
            if re.fullmatch(r"⟦P\d+⟧", tok):
                out.append(tok)
                i += 1
                continue

            nxt = _lookahead_words(words, i, _MAX_PHRASE)
            matched = False
            for L in range(min(_MAX_PHRASE, len(nxt)), 0, -1):
                phrase = " ".join(_norm(w) for w in nxt[:L])
                if phrase in PHRASE_TABLE:
                    out.append(PHRASE_TABLE[phrase])
                    i += _skip_n_words(words, i, L)
                    matched = True
                    break
            if matched:
                continue

            hon = _match_name_honorific(words, i)
            if hon is not None:
                consumed, urdu = hon
                out.append(urdu)
                i += consumed
                continue

            pre, core, post = _split_punct(tok)
            ur = _stem_lookup(core)
            if ur is None and _is_probable_name(core):
                ur = core  # keep Latin/Turkish proper name
            if ur is None:
                ur = core
            out.append(pre + ur + post)
            i += 1
        return "".join(out)

    def _restore(self, text: str, bucket: dict[str, str]) -> str:
        for k, v in bucket.items():
            text = text.replace(k, v)
        return text

    def translate_subs(self, subs, progress=None) -> list:
        import srt as srtmod

        out = []
        n = len(subs)
        for i, sub in enumerate(subs):
            res = self.translate_text(sub.content)
            out.append(
                srtmod.Subtitle(
                    index=sub.index,
                    start=sub.start,
                    end=sub.end,
                    content=res.urdu,
                    proprietary=("TITLE" if res.is_title else getattr(sub, "proprietary", "")),
                )
            )
            if progress and (i % 5 == 0 or i == n - 1):
                progress(i + 1, n, res.method)
        return out


def _tokenize_keep(text: str) -> list[tuple[str, str]]:
    """Split into ('word', token) | ('other', token) keeping whitespace/punct."""
    parts: list[tuple[str, str]] = []
    buf = []
    mode = None

    def flush(m, b):
        if b:
            parts.append((m, "".join(b)))

    for ch in text:
        is_w = ch.isalpha() or ch in "'’⟦⟧0123456789" or ("\u0600" <= ch <= "\u06FF")
        # digits attached to words (Bölüm 12 handled separately as other)
        if ch.isdigit():
            is_w = False
        if ch in "⟦⟧P" or (mode == "word" and ch.isdigit() and buf and buf[0] == "⟦"):
            is_w = True
        cur = "word" if (ch.isalpha() or ch in "'’") else "other"
        # placeholders
        if ch in "⟦⟧" or (mode == "word" and ch.isdigit() and any(x == "⟦" for x in buf)):
            cur = "word"
        if mode is None:
            mode = cur
            buf = [ch]
        elif cur == mode or (mode == "word" and ch in "'’"):
            buf.append(ch)
        else:
            flush(mode, buf)
            mode = cur
            buf = [ch]
    flush(mode, buf)
    # merge placeholder pieces if split
    return parts


def _lookahead_words(tokens: list[tuple[str, str]], i: int, n: int) -> list[str]:
    found = []
    for kind, tok in tokens[i:]:
        if kind == "word":
            found.append(tok)
            if len(found) >= n:
                break
        elif tok.strip() == "":
            continue
        else:
            # punctuation breaks phrases except apostrophes already in word
            if tok.strip() in {",", ".", "!", "?", ";", ":"}:
                break
    return found


def _skip_n_words(tokens: list[tuple[str, str]], i: int, n: int) -> int:
    seen = 0
    j = i
    while j < len(tokens) and seen < n:
        kind, tok = tokens[j]
        j += 1
        if kind == "word":
            seen += 1
    return j - i


def _match_name_honorific(tokens: list[tuple[str, str]], i: int) -> tuple[int, str] | None:
    """Match 'Name Honorific' or 'Honorific Name'."""
    nxt = _lookahead_words(tokens, i, 3)
    if len(nxt) < 2:
        # single honorific
        if nxt and _norm(nxt[0]) in HONOR_TABLE:
            return _skip_n_words(tokens, i, 1), HONOR_TABLE[_norm(nxt[0])]
        return None
    a, b = _norm(nxt[0]), _norm(nxt[1])
    if b in HONOR_TABLE and (_is_probable_name(nxt[0]) or nxt[0][0].isupper()):
        return _skip_n_words(tokens, i, 2), f"{nxt[0]} {HONOR_TABLE[b]}"
    if a in HONOR_TABLE and (_is_probable_name(nxt[1]) or nxt[1][0].isupper()):
        return _skip_n_words(tokens, i, 2), f"{HONOR_TABLE[a]} {nxt[1]}"
    return None

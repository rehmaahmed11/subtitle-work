from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tr2ur.srt_io import load_srt, compose_srt
from tr2ur.translate import Translator, is_title_card


def test_title_card_detection():
    assert is_title_card("BİRİNCİ BÖLÜM")
    assert is_title_card("Önceki bölümde")
    assert not is_title_card("Ahmet, nasılsın?")


def test_idiom_not_literal():
    t = Translator(prefer_online=False)
    r = t.translate_text("İş işten geçti.")
    assert "دیر" in r.urdu
    r2 = t.translate_text("Sütten ağzı yanan yoğurdu üfleyerek yer.")
    assert "دودھ" in r2.urdu


def test_honorific_keeps_name():
    t = Translator(prefer_online=False)
    r = t.translate_text("Ahmet Bey, nasılsınız?")
    assert "Ahmet" in r.urdu
    assert "صاحب" in r.urdu


def test_islamic_phrase():
    t = Translator(prefer_online=False)
    r = t.translate_text("İnşallah yarın görüşürüz.")
    assert "ان شاء اللہ" in r.urdu


def test_timestamps_preserved():
    path = ROOT / "examples" / "sample_tr.srt"
    subs = load_srt(path)
    t = Translator(prefer_online=False)
    out = t.translate_subs(subs)
    assert len(out) == len(subs)
    for a, b in zip(subs, out):
        assert a.start == b.start
        assert a.end == b.end
        assert b.content.strip()


def test_sample_roundtrip_srt_text():
    path = ROOT / "examples" / "sample_tr.srt"
    subs = load_srt(path)
    t = Translator(prefer_online=False)
    out = t.translate_subs(subs)
    text = compose_srt(out)
    assert "-->" in text
    assert "قسط" in text or "صاحب" in text

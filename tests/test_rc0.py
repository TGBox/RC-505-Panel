import shutil

import pytest

from rc_505_panel.storage.rc0 import Rc0Document, read_count
from rc_505_panel.storage.rc0_schema import (
    AssignSlot, guess_memory_tempo, read_assign, source_index_for_cc, track_info, write_assign,
)


def test_roundtrip_fixtures_byte_identical(fixtures):
    for name in ("MEMORY001A.RC0", "MEMORY001B.RC0"):
        raw = (fixtures / name).read_bytes()
        assert Rc0Document(raw).to_bytes() == raw


def test_roundtrip_all_memories_byte_identical(full_backup):
    """AC1: alle 198 Memory-Dateien des echten Backups."""
    files = sorted((full_backup / "DATA").glob("MEMORY*.RC0"))
    assert len(files) == 198
    for f in files:
        raw = f.read_bytes()
        assert Rc0Document(raw, f).to_bytes() == raw, f.name


def test_load_picks_higher_hex_count(fixtures, tmp_path):
    for n in ("MEMORY001A.RC0", "MEMORY001B.RC0"):
        shutil.copy(fixtures / n, tmp_path / n)
    doc = Rc0Document.load(tmp_path, 1)
    assert doc.source.name == "MEMORY001B.RC0" and doc.count == 8
    # count ist hexadezimal: 0x10 > 0x09
    a = tmp_path / "MEMORY001A.RC0"
    a.write_bytes(a.read_bytes().replace(b"<count>0007</count>", b"<count>0010</count>"))
    assert Rc0Document.load(tmp_path, 1).source.name == "MEMORY001A.RC0"


def test_known_values(fixtures):
    doc = Rc0Document.from_file(fixtures / "MEMORY001B.RC0")
    assert doc.get("mem/TRACK1/X") == 1336560
    assert doc.name() == "Memory01"
    info = track_info(doc, 1)
    assert info.has_data and info.frames == 1336560
    assert "ifx/SETUP/A" in doc and "tfx/SETUP/A" in doc  # gleiche Sektionsnamen, verschiedene Pfade


def test_set_changes_only_that_value(fixtures):
    raw = (fixtures / "MEMORY001B.RC0").read_bytes()
    doc = Rc0Document(raw)
    doc.set("mem/TRACK3/X", 12345)
    out = doc.to_bytes()
    assert Rc0Document(out).get("mem/TRACK3/X") == 12345
    old = b"<X>" + str(doc.get_original("mem/TRACK3/X")).encode() + b"</X>"
    i = raw.index(old, raw.index(b"<TRACK3>"))
    assert out[:i] == raw[:i]
    assert out[i + len(b"<X>12345</X>"):] == raw[i + len(old):]


def test_unknown_path_raises(fixtures):
    doc = Rc0Document.from_file(fixtures / "MEMORY001A.RC0")
    with pytest.raises(KeyError):
        doc.set("mem/TRACK9/X", 1)


def test_save_writes_older_slot_with_next_hex_count(fixtures, tmp_path):
    for n in ("MEMORY001A.RC0", "MEMORY001B.RC0"):
        shutil.copy(fixtures / n, tmp_path / n)
    b_before = (tmp_path / "MEMORY001B.RC0").read_bytes()
    doc = Rc0Document.load(tmp_path, 1)          # B (count 8) ist aktuell
    doc.set_name("Drop Test")
    written = doc.save()
    assert written.name == "MEMORY001A.RC0"      # älterer Slot (count 7)
    assert read_count(written) == 9
    assert written.read_bytes().endswith(b"<count>0009</count>")
    assert (tmp_path / "MEMORY001B.RC0").read_bytes() == b_before
    again = Rc0Document.load(tmp_path, 1)
    assert again.source.name == "MEMORY001A.RC0" and again.name() == "Drop Test"


def test_assign_roundtrip(fixtures):
    doc = Rc0Document.from_file(fixtures / "MEMORY001B.RC0")
    slot = AssignSlot(1, True, source_index_for_cc(21), 0)
    write_assign(doc, slot)
    again = Rc0Document(doc.to_bytes())
    assert read_assign(again, 1) == slot
    assert source_index_for_cc(26) == 64
    with pytest.raises(ValueError):
        source_index_for_cc(70)  # CC#64–95 noch nicht bestätigt


def test_guess_tempo(fixtures):
    doc = Rc0Document.from_file(fixtures / "MEMORY001B.RC0")
    assert guess_memory_tempo(doc) == track_info(doc, 1).tempo

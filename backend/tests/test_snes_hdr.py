# -*- coding: utf-8 -*-
"""snes_hdr.read_header() — which coprocessor a SNES cart declares in its header.

Pins the three things that make the answer trustworthy: the checksum test (a random
stretch of ROM must not read as a header), the 'unknown' vs 'none' distinction (a
failure to read must never be recorded as "plain cart"), and the map-mode SA-1 path
(some SA-1 carts leave the rom-type byte looking ordinary and only declare themselves
at 0x15). Also pins that the .smc copier header is skipped, and that reading is
seek-based — the startup backfill walks the whole snes library.
"""
import pytest

from app.services import snes_hdr


def _cart(tmp_path, *, offset=0x7FC0, map_mode=0x20, rom_type=0x00,
          copier=False, valid_checksum=True, name=b"TEST CART"):
    """Build a minimal cart whose header sits at `offset`, checksum consistent by
    default. Real carts are megabytes; only the header window has to be right."""
    hdr = bytearray(0x30)
    hdr[0x00:0x15] = name.ljust(0x15, b" ")[:0x15]
    hdr[0x15] = map_mode
    hdr[0x16] = rom_type
    hdr[0x17] = 0x0A                                   # rom size, unused by the chip read
    complement, checksum = 0x1234, (0x1234 ^ 0xFFFF) if valid_checksum else 0x0000
    hdr[0x1C:0x1E] = complement.to_bytes(2, "little")
    hdr[0x1E:0x20] = checksum.to_bytes(2, "little")

    # Real carts are power-of-two sized, which is what makes the copier header
    # detectable at all (size % 1024 == 512). Pad to a bank boundary so the fixture
    # has that property too.
    span = offset + 0x30
    body = bytearray(span + (-span % 1024))
    body[offset:offset + 0x30] = hdr
    blob = (b"\x00" * 512 + bytes(body)) if copier else bytes(body)

    p = tmp_path / "game.smc"
    p.write_bytes(blob)
    return p


# --- no coprocessor -----------------------------------------------------

def test_plain_lorom_reads_as_none(tmp_path):
    assert snes_hdr.read_header(_cart(tmp_path))["chip"] == "none"


def test_plain_hirom_at_its_own_offset(tmp_path):
    assert snes_hdr.read_header(_cart(tmp_path, offset=0xFFC0, map_mode=0x21))["chip"] == "none"


# --- coprocessors -------------------------------------------------------

@pytest.mark.parametrize("high_nibble,expected", [
    (0x0, "DSP"), (0x1, "SuperFX"), (0x2, "OBC1"), (0x3, "SA-1"),
    (0x4, "S-DD1"), (0x5, "S-RTC"), (0xE, "Other"), (0xF, "Custom"),
])
def test_rom_type_high_nibble_names_the_chip(tmp_path, high_nibble, expected):
    # Low nibble 0x3 = "ROM + coprocessor"; only then is the high nibble a chip id.
    cart = _cart(tmp_path, rom_type=(high_nibble << 4) | 0x3)
    assert snes_hdr.read_header(cart)["chip"] == expected


def test_low_nibble_without_coprocessor_is_not_a_chip(tmp_path):
    """0x02 is ROM+RAM+battery. Its high nibble is 0, which would read as 'DSP' if the
    low nibble were ignored — the commonest way to get this wrong."""
    assert snes_hdr.read_header(_cart(tmp_path, rom_type=0x02))["chip"] == "none"


@pytest.mark.parametrize("map_mode", [0x23, 0x33])
def test_sa1_declared_only_in_map_mode(tmp_path, map_mode):
    """Some SA-1 carts carry an ordinary-looking rom type and say SA-1 at 0x15 alone.
    Missing this silently files a second 65816 as a plain cart."""
    assert snes_hdr.read_header(_cart(tmp_path, map_mode=map_mode, rom_type=0x00))["chip"] == "SA-1"


@pytest.mark.parametrize("map_mode", [0x22, 0x32])
def test_sdd1_map_mode_is_not_sa1(tmp_path, map_mode):
    """0x32 is S-DD1's FastROM spelling and sits one below SA-1's 0x33. Reading it as
    SA-1 filed Star Ocean — an S-DD1 cart — as carrying a second 65816, which is how
    this was caught: against the real library, not the fixtures."""
    assert snes_hdr.read_header(_cart(tmp_path, map_mode=map_mode, rom_type=0x00))["chip"] == "S-DD1"


def test_rom_type_beats_map_mode(tmp_path):
    """Map mode only fills in for carts that leave the rom-type byte blank. A cart that
    names its chip properly must never be overridden by the coarser signal."""
    cart = _cart(tmp_path, map_mode=0x23, rom_type=0x13)   # map says SA-1, type says GSU
    assert snes_hdr.read_header(cart)["chip"] == "SuperFX"


# --- unknown is not 'none' ----------------------------------------------

def test_bad_checksum_is_unknown_not_none(tmp_path):
    """The whole point of the distinction: a dump we could not read must not be
    recorded as a cart we read and found empty."""
    assert snes_hdr.read_header(_cart(tmp_path, valid_checksum=False))["chip"] == "unknown"


def test_garbage_file_is_unknown(tmp_path):
    p = tmp_path / "garbage.sfc"
    p.write_bytes(b"\xAA" * 0x20000)
    assert snes_hdr.read_header(p)["chip"] == "unknown"


def test_file_too_small_for_any_header_is_unknown(tmp_path):
    p = tmp_path / "tiny.sfc"
    p.write_bytes(b"\x00" * 64)
    assert snes_hdr.read_header(p)["chip"] == "unknown"


def test_missing_file_is_unknown(tmp_path):
    assert snes_hdr.read_header(tmp_path / "nope.sfc")["chip"] == "unknown"


# --- copier header ------------------------------------------------------

def test_copier_header_is_skipped(tmp_path):
    """A .smc from a copier puts 512 bytes of its own in front. Not skipping them
    shifts every candidate offset and the header is never found."""
    cart = _cart(tmp_path, rom_type=0x13, copier=True)   # 0x1_ = SuperFX
    assert snes_hdr.read_header(cart)["chip"] == "SuperFX"


# --- reading is header-only ---------------------------------------------

def test_does_not_read_the_whole_cart(tmp_path, monkeypatch):
    """The startup backfill walks every snes rom; a read_bytes() per cart would be
    gigabytes of I/O. Guard the seek-based access so it cannot regress."""
    cart = _cart(tmp_path, rom_type=0x33)                # SA-1
    reads: list[int] = []
    real_open = type(cart).open

    def spy_open(self, *a, **kw):
        fh = real_open(self, *a, **kw)
        real_read = fh.read

        def counting_read(n=-1):
            reads.append(n)
            return real_read(n)

        fh.read = counting_read
        return fh

    monkeypatch.setattr(type(cart), "open", spy_open)
    assert snes_hdr.read_header(cart)["chip"] == "SA-1"
    assert reads, "expected the header to be read"
    assert all(n == 0x30 for n in reads), f"non-header-sized read: {reads}"


# --- HEAVY set ----------------------------------------------------------

def test_upload_stamps_the_chip_and_the_library_returns_it(client, session_id, tmp_path):
    """End-to-end, because the insert in routers/roms.py binds twenty-two POSITIONAL
    values: a column added in the wrong place there lands the chip in someone else's
    field and nothing else would notice. Also pins that the library endpoint carries
    it — the card in the grid reads `snes_chip` off exactly this payload."""
    cart = _cart(tmp_path, rom_type=0x13)                # SuperFX
    resp = client.post(
        f"/api/sessions/{session_id}/roms",
        data={"system": "snes"},
        files=[("files", ("Star Fox.sfc", cart.read_bytes(), "application/octet-stream"))],
    )
    assert resp.status_code == 200, resp.text

    lib = client.get(f"/api/sessions/{session_id}/library").json()
    rom = next(r for r in lib["roms"] if r["system_key"] == "snes")
    assert rom["snes_chip"] == "SuperFX"


def test_upload_of_a_non_snes_rom_leaves_the_column_null(client, session_id):
    """The header read is snes-only: a .nes file has no SNES header and must not be
    probed for one, nor recorded as 'unknown' for failing a test it never took."""
    resp = client.post(
        f"/api/sessions/{session_id}/roms",
        data={"system": "nes"},
        files=[("files", ("Game.nes", b"NES\x1a" + b"\x00" * 2048, "application/octet-stream"))],
    )
    assert resp.status_code == 200, resp.text

    lib = client.get(f"/api/sessions/{session_id}/library").json()
    rom = next(r for r in lib["roms"] if r["system_key"] == "nes")
    assert rom["snes_chip"] is None


def test_heavy_names_match_what_the_reader_returns(tmp_path):
    """HEAVY is matched against read_header()'s output by the UI, so a rename in one
    place and not the other would quietly stop flagging the heaviest carts."""
    produced = {snes_hdr.read_header(_cart(tmp_path, rom_type=(n << 4) | 0x3))["chip"]
                for n in (0x1, 0x3)}
    assert produced == set(snes_hdr.HEAVY)


# --- mapper and declared size -------------------------------------------

@pytest.mark.parametrize("map_mode,expected", [
    (0x20, "LoROM"), (0x21, "HiROM"), (0x25, "ExHiROM"),
    (0x30, "LoROM · FastROM"), (0x31, "HiROM · FastROM"),
    (0x22, "LoROM"),                      # S-DD1 carts reuse the LoROM shape
    (0x23, "LoROM"),                      # so do SA-1 carts
])
def test_map_mode_names_the_layout_and_flags_fastrom(tmp_path, map_mode, expected):
    """FastROM is bit 4 of the same byte, so every layout has two spellings. The panel
    prints this verbatim; getting the bit wrong would label half the library wrong."""
    assert snes_hdr.read_header(_cart(tmp_path, map_mode=map_mode))["map"] == expected


def test_declared_rom_size_is_read(tmp_path):
    """Byte 0x17 is log2 of the size in KB — 0x0A is 1024 KB, the commonest cart here."""
    assert snes_hdr.read_header(_cart(tmp_path))["rom_kb"] == 1024


def test_absurd_declared_size_is_dropped(tmp_path):
    """A header can say anything. Quoting "33554432 KB" at the user because a byte was
    garbage is worse than saying nothing, so out-of-range exponents become None."""
    cart = _cart(tmp_path)
    raw = bytearray(cart.read_bytes())
    raw[0x7FC0 + 0x17] = 0x19             # 2^25 KB — not a cartridge
    cart.write_bytes(bytes(raw))
    assert snes_hdr.read_header(cart)["rom_kb"] is None


def test_unreadable_header_reports_nothing_else(tmp_path):
    """map and rom_kb come off the same bytes the checksum just rejected. Returning
    them anyway would be quoting a source we have declared untrustworthy."""
    h = snes_hdr.read_header(_cart(tmp_path, valid_checksum=False))
    assert h == {"chip": "unknown", "map": None, "rom_kb": None, "title": None}


# --- internal cart title (the cover search's last resort) ----------------

def test_internal_title_is_read(tmp_path):
    """The only Latin name a Korean-titled rom carries. Without it the cover search has
    literally nothing to ask a provider for."""
    assert snes_hdr.read_header(_cart(tmp_path, name=b"CONTRA SPIRITS"))["title"] == "CONTRA SPIRITS"


def test_title_padding_is_trimmed(tmp_path):
    """The field is 21 bytes, space- or NUL-padded. Searching for 'R-TYPE 3\\x00\\x00' is
    searching for nothing."""
    cart = _cart(tmp_path, name=b"R-TYPE 3\x00\x00\x00")
    assert snes_hdr.read_header(cart)["title"] == "R-TYPE 3"


def test_shift_jis_title_is_dropped(tmp_path):
    """Japanese carts often fill this field with Shift-JIS. Those bytes are not a search
    term in any useful sense, and feeding them to a provider is noise."""
    assert snes_hdr.read_header(_cart(tmp_path, name=b"\x83\x8d\x83b\x83N\x83}\x83\x93"))["title"] is None


def test_title_too_short_to_be_a_name_is_dropped(tmp_path):
    """Padding and stubs would search as confidently as they are useless."""
    assert snes_hdr.read_header(_cart(tmp_path, name=b"A1"))["title"] is None


def test_unreadable_header_has_no_title_either(tmp_path):
    assert snes_hdr.read_header(_cart(tmp_path, valid_checksum=False))["title"] is None

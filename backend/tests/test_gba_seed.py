"""The startup seed: hand every GBA rom the measurements the shipped table already holds,
without stepping on a local live measurement the table has never seen."""
from app import db
from app.services import gba_seed


def _gba_header(code: str, *, magic: int = 0x96) -> bytes:
    """A file body with a valid GBA cart header carrying `code` at 0xAC."""
    header = bytearray(0xC0)
    header[0xAC:0xB0] = code.encode()
    header[0xB2] = magic
    return bytes(header) + b"\x00" * 64


def test_seed_fills_an_unmeasured_rom_from_the_table(session_id, make_rom):
    # BPEK — Pokémon Emerald (Korean), a game the shipped table has measured.
    rom = make_rom("gba", "emerald.gba", content=_gba_header("BPEK"))
    assert rom["exec_cycles"] is None

    with db.connect() as conn:
        assert gba_seed.apply_table(conn) == 1
        got = conn.execute(
            "SELECT exec_cycles, idle_pc, probe_status FROM roms WHERE id = ?",
            (rom["id"],)).fetchone()
    assert got["probe_status"] == "ok"
    assert got["idle_pc"] == "0x80008ce"
    assert 0 < got["exec_cycles"] < 280896


def test_seed_is_idempotent(session_id, make_rom):
    make_rom("gba", "emerald.gba", content=_gba_header("BPEK"))
    with db.connect() as conn:
        assert gba_seed.apply_table(conn) == 1     # first run measures it
        assert gba_seed.apply_table(conn) == 0     # second run changes nothing


def test_seed_leaves_a_rom_the_table_never_saw_alone(session_id, make_rom):
    # A rom this deployment measured live but that is not yet in the shipped table is the
    # LOCAL truth — the seed must not blank it back to unknown.
    rom = make_rom("gba", "unknown.gba", content=_gba_header("ZZZZ"),
                   exec_cycles=12345, probe_status="ok", idle_hunted=1)
    with db.connect() as conn:
        assert gba_seed.apply_table(conn) == 0
        got = conn.execute(
            "SELECT exec_cycles, probe_status FROM roms WHERE id = ?", (rom["id"],)).fetchone()
    assert got["exec_cycles"] == 12345
    assert got["probe_status"] == "ok"


def test_seed_carries_the_sound_driver(session_id, make_rom):
    # A game whose M4A mixer the firmware replaces natively — the audio columns are the
    # whole point of shipping this data, and only the table has them.
    code = _driver_code()
    rom = make_rom("gba", "musical.gba", content=_gba_header(code))
    with db.connect() as conn:
        gba_seed.apply_table(conn)
        got = conn.execute(
            "SELECT audio_cycles, audio_name FROM roms WHERE id = ?", (rom["id"],)).fetchone()
    assert got["audio_cycles"] and got["audio_cycles"] > 0
    assert got["audio_name"]


def _driver_code() -> str:
    """A game code the table measured WITH a named sound driver (mixer HLE'd)."""
    for code, row in gba_seed.gba_probe._table.load().items():
        if row.get("audio_cycles") and row.get("audio_name") and code.isascii() and code.strip("\x00"):
            return code
    raise AssertionError("no audio-named entry in the shipped table")

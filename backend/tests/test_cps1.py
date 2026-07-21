"""CPS-1 romset identification and folder composition.

The failure this guards against does not raise, log, or look wrong until you
see the screen: a MAME romset's ROM_LOAD order is not its filename order, so
assigning chips by name loads every file, checks out every size, and cross-wires
two bitplane pairs. The firmware measured it at 85% of the graphics region
corrupted. Everything here keys on CRC32 for that reason.

Fixtures are synthetic: 512 KB blobs whose CRC32 is made to match a real MAME
entry. No ROM content is in this repository.
"""
from __future__ import annotations

import io
import zipfile
import zlib

import pytest

from app.services import cps1


CHIP = 0x80000

# Real wofj / wofr1 entries, from app/assets/cps1_romsets.json.
WOFJ_PRG = ["9b215a68", "b74b09ac"]
WOFJ_GFX = ["0d9cb9bf", "45227027", "c5ca2460", "e349551c",
            "e4a44d53", "58066ba8", "d706568e", "d4a19a02"]
# The four wofj shares with its parent — the ones a clone archive omits.
SHARED_GFX = WOFJ_GFX[:4]


def blob_with_crc(target_hex: str, size: int = CHIP) -> bytes:
    """A `size`-byte blob whose CRC32 is exactly `target_hex`.

    Lets a fixture name the real MAME hash it stands for, so these tests
    exercise the shipped table rather than invented numbers.

    CRC32 is affine over GF(2): crc(body + tail) = crc(body + 0) XOR L(tail)
    for a linear L. Probe L's 32 basis vectors by flipping one tail bit at a
    time, reduce to row echelon, and read off the tail that lands on `target`.
    """
    target = int(target_hex, 16)
    body = bytes(size - 4)
    base = zlib.crc32(body + bytes(4)) & 0xFFFFFFFF

    pivots: dict[int, tuple[int, int]] = {}   # high bit -> (vector, tail mask)
    for bit in range(32):
        vec = (zlib.crc32(body + (1 << bit).to_bytes(4, "little")) & 0xFFFFFFFF) ^ base
        mask = 1 << bit
        while vec:
            col = vec.bit_length() - 1
            if col not in pivots:
                pivots[col] = (vec, mask)
                break
            pvec, pmask = pivots[col]
            vec ^= pvec
            mask ^= pmask

    want, tail = target ^ base, 0
    while want:
        col = want.bit_length() - 1
        assert col in pivots, "CRC32 basis is not full rank — cannot forge"
        pvec, pmask = pivots[col]
        want ^= pvec
        tail ^= pmask

    out = body + tail.to_bytes(4, "little")
    assert zlib.crc32(out) & 0xFFFFFFFF == target, "forced CRC did not take"
    return out


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture(scope="module")
def clone_zip() -> bytes:
    """wofj as MAME actually distributes it: its own chips only."""
    own = [c for c in WOFJ_GFX if c not in SHARED_GFX]
    entries = {f"tk2j{i}.bin": blob_with_crc(c) for i, c in enumerate(WOFJ_PRG)}
    entries.update({f"tk20{i + 5}.bin": blob_with_crc(c) for i, c in enumerate(own)})
    # A PAL dump, which must be ignored rather than mistaken for a chip.
    entries["tk263b.1a"] = b"\x00" * 279
    return make_zip(entries)


@pytest.fixture(scope="module")
def parent_zip() -> bytes:
    """The parent archive, holding the four shared graphics chips.

    Named in FILENAME order that deliberately disagrees with slot order --
    tk2_gfx2 is slot 2 and tk2_gfx3 is slot 1 in the real set — so a filename-
    ordered implementation passes nothing here.
    """
    by_slot = dict(zip(SHARED_GFX, ["tk2_gfx1.rom", "tk2_gfx3.rom",
                                    "tk2_gfx2.rom", "tk2_gfx4.rom"]))
    return make_zip({name: blob_with_crc(crc) for crc, name in by_slot.items()})


def test_table_loads_and_matches_the_firmware_source():
    sets = cps1.romsets()
    assert {s["name"] for s in sets} >= {"wof", "wofj", "wofr1"}
    wofj = cps1.romset("wofj")
    assert wofj["parent"] == "wof"
    assert [c["crc32"] for c in wofj["gfx"]] == WOFJ_GFX


def test_clone_alone_is_reported_incomplete_with_its_parent_named(clone_zip):
    result = cps1.identify([("wofj.zip", clone_zip)])
    assert result.setname == "wofj"
    assert not result.complete
    # Four shared graphics chips, and the user is told which set has them.
    assert len(result.missing_crcs) == 4
    assert set(result.missing_crcs) == set(SHARED_GFX)
    assert result.parent == "wof"


def test_clone_plus_parent_is_complete(clone_zip, parent_zip):
    result = cps1.identify([("wofj.zip", clone_zip), ("wof.zip", parent_zip)])
    assert result.setname == "wofj"
    assert result.complete
    assert result.missing_crcs == []


def test_pal_dumps_and_junk_are_ignored(clone_zip):
    junk = make_zip({"readme.txt": b"hello", "tk263b.1a": b"\x00" * 279})
    result = cps1.identify([("wofj.zip", clone_zip), ("junk.zip", junk)])
    assert result.setname == "wofj"
    assert len(result.missing_crcs) == 4


def test_unknown_archive_names_no_set(clone_zip):
    stranger = make_zip({"whatever.rom": blob_with_crc("deadbeef")})
    result = cps1.identify([("x.zip", stranger)])
    assert result.setname is None
    assert not result.complete


def test_compose_writes_every_chip_under_its_own_name(tmp_path, clone_zip, parent_zip):
    dest = tmp_path / "천지를 먹다 2 (Warriors of Fate)"
    written = cps1.compose_folder(
        dest, [("wofj.zip", clone_zip), ("wof.zip", parent_zip)])

    assert len(written) == 10
    on_disk = sorted(p.name for p in dest.iterdir())
    assert len(on_disk) == 10
    # Original MAME filenames survive; nothing is renamed to a hash.
    assert "tk2_gfx3.rom" in on_disk
    # And no PAL dump or stray file rode along.
    assert "tk263b.1a" not in on_disk
    assert all((dest / n).stat().st_size == CHIP for n in on_disk)


def test_compose_refuses_an_incomplete_set(tmp_path, clone_zip):
    dest = tmp_path / "wofj"
    with pytest.raises(cps1.IncompleteRomset) as e:
        cps1.compose_folder(dest, [("wofj.zip", clone_zip)])
    # The message has to name the parent -- "4 chips missing" alone does not
    # tell a user what to go and find.
    assert "wof" in str(e.value)
    assert not dest.exists()


def test_composed_folder_is_what_the_device_matches(tmp_path, clone_zip, parent_zip):
    """The whole point: the device re-derives the same set from the folder.

    Mirrors the firmware's loader -- hash every 512 KB file found, match the
    table -- so a composition that satisfies this test satisfies the device.
    """
    dest = tmp_path / "game"
    cps1.compose_folder(dest, [("wofj.zip", clone_zip), ("wof.zip", parent_zip)])

    found = []
    for p in sorted(dest.iterdir()):
        if p.stat().st_size != CHIP:
            continue
        found.append("%08x" % (zlib.crc32(p.read_bytes()) & 0xFFFFFFFF))

    matched = cps1.match_crcs(found)
    assert matched is not None
    setname, prg_idx, gfx_idx = matched
    assert setname == "wofj"
    assert [found[i] for i in prg_idx] == WOFJ_PRG
    assert [found[i] for i in gfx_idx] == WOFJ_GFX


# --- the SD packaging view: a game folder of zips -> chips on the card -------

def test_game_folder_of_zips_expands_to_the_full_set(tmp_path, clone_zip, parent_zip):
    game = tmp_path / "천지를 먹다 2 (Warriors of Fate)"
    game.mkdir()
    (game / "wofj.zip").write_bytes(clone_zip)
    (game / "wof.zip").write_bytes(parent_zip)

    entries = cps1.sd_chip_entries(game)
    assert len(entries) == 10
    assert all(e.size == CHIP for e in entries)
    # Original MAME names on the card; the parent's chips came from its own zip.
    assert "tk2_gfx3.rom" in {e.name for e in entries}
    assert {e.archive.name for e in entries} == {"wofj.zip", "wof.zip"}


def test_incomplete_game_folder_ships_nothing_rather_than_half(tmp_path, clone_zip):
    game = tmp_path / "wofj only"
    game.mkdir()
    (game / "wofj.zip").write_bytes(clone_zip)
    # Half a romset on the card is a game that reaches the device and dies there.
    assert cps1.sd_chip_entries(game) == []


def test_adding_the_parent_later_completes_it_with_nothing_to_invalidate(
        tmp_path, clone_zip, parent_zip):
    """Re-uploading has to be safe: this is why nothing is pre-extracted."""
    game = tmp_path / "game"
    game.mkdir()
    (game / "wofj.zip").write_bytes(clone_zip)
    assert cps1.sd_chip_entries(game) == []

    (game / "wof.zip").write_bytes(parent_zip)
    assert len(cps1.sd_chip_entries(game)) == 10

    # And uploading the same archive again changes nothing.
    (game / "wofj.zip").write_bytes(clone_zip)
    assert len(cps1.sd_chip_entries(game)) == 10


def test_empty_or_missing_folder_is_not_an_error(tmp_path):
    assert cps1.sd_chip_entries(tmp_path / "nope") == []
    (tmp_path / "empty").mkdir()
    assert cps1.sd_chip_entries(tmp_path / "empty") == []


# --- end to end: what actually lands on the card ----------------------------

def _sd_names(root, **kw):
    """Arcnames the SD builder would write, for a fake session root."""
    from app.services import packaging
    return {arc for _src, arc, _member in packaging._cps1_entries(root, kw.get("systems"),
                                                                  kw.get("excluded_roms"))}


def test_romset_zips_never_reach_the_card(tmp_path):
    from app import config
    from app.services.packaging import _excluded
    z = tmp_path / config.ROMS_DIR_NAME / "cps1" / "game" / "wof.zip"
    z.parent.mkdir(parents=True)
    z.write_bytes(b"x")
    # The firmware cannot read a zip: raw chip bytes or nothing.
    assert _excluded(tmp_path, z, include_video=False) is True
    # Its cover still ships.
    cover = tmp_path / "covers" / "cps1" / "game.img"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"x")
    assert _excluded(tmp_path, cover, include_video=False) is False


def test_card_gets_chips_under_the_game_name_folder(tmp_path, clone_zip, parent_zip):
    from app import config
    game = tmp_path / config.ROMS_DIR_NAME / "cps1" / "천지를 먹다 2 (Warriors of Fate)"
    game.mkdir(parents=True)
    (game / "wofj.zip").write_bytes(clone_zip)
    (game / "wof.zip").write_bytes(parent_zip)

    names = _sd_names(tmp_path)
    assert len(names) == 10
    prefix = f"{config.ROMS_DIR_NAME}/cps1/천지를 먹다 2 (Warriors of Fate)/"
    assert all(n.startswith(prefix) for n in names)
    assert prefix + "tk2_gfx3.rom" in names
    # No zip, no PAL dump.
    assert not any(n.endswith(".zip") or n.endswith("tk263b.1a") for n in names)


def test_incomplete_game_contributes_nothing_to_the_card(tmp_path, clone_zip):
    from app import config
    game = tmp_path / config.ROMS_DIR_NAME / "cps1" / "wofj only"
    game.mkdir(parents=True)
    (game / "wofj.zip").write_bytes(clone_zip)
    assert _sd_names(tmp_path) == set()


def test_card_size_counts_chips_not_zips(tmp_path, clone_zip, parent_zip):
    from app import config
    from app.services import packaging
    game = tmp_path / config.ROMS_DIR_NAME / "cps1" / "game"
    game.mkdir(parents=True)
    (game / "wofj.zip").write_bytes(clone_zip)
    (game / "wof.zip").write_bytes(parent_zip)

    total = sum(packaging._entry_size(src, m)
                for src, _arc, m in packaging._cps1_entries(tmp_path, None, None))
    # Ten chips, not the ~5 MB of compressed archives.
    assert total == 10 * CHIP


# --- two clones, one shared parent: each folder must stand alone -------------

WOFR1_PRG = ["11fb2ed1", "479b3f24"]
WOFR1_OWN_GFX = ["291f0f0b", "3edeb949", "1abd14d6", "b27948e3"]


@pytest.fixture(scope="module")
def sibling_zip() -> bytes:
    """wofr1's own chips — a second clone that needs the SAME four shared
    graphics chips wofj does."""
    entries = {f"tk2e_2{i}b.rom": blob_with_crc(c) for i, c in enumerate(WOFR1_PRG)}
    entries.update({f"tk2-{i + 5}m.rom": blob_with_crc(c)
                    for i, c in enumerate(WOFR1_OWN_GFX)})
    return make_zip(entries)


def test_two_clones_sharing_a_parent_each_get_a_complete_folder(
        tmp_path, clone_zip, sibling_zip, parent_zip):
    """Neither folder may depend on the other's existence.

    A game folder is self-contained by design: the device scans that one
    directory and nothing else. So when two releases share a parent's chips,
    BOTH folders carry a copy — the duplication is the point, not an oversight.
    """
    pool = [("wofj.zip", clone_zip), ("wofr1.zip", sibling_zip), ("wof.zip", parent_zip)]

    jp = tmp_path / "천지를 먹다 2 (Japan)"
    world = tmp_path / "Warriors of Fate (World)"
    assert len(cps1.compose_folder(jp, pool)) == 10
    # compose picks the best match first; ask for the sibling explicitly.
    assert len(cps1.compose_folder(world, [("wofr1.zip", sibling_zip),
                                           ("wof.zip", parent_zip)])) == 10

    def crcs_of(d):
        return {"%08x" % (zlib.crc32(p.read_bytes()) & 0xFFFFFFFF)
                for p in d.iterdir() if p.stat().st_size == CHIP}

    jp_crcs, world_crcs = crcs_of(jp), crcs_of(world)
    # Each folder is a complete set on its own...
    assert cps1.match_crcs(sorted(jp_crcs)) is not None
    assert cps1.match_crcs(sorted(world_crcs)) is not None
    # ...and the four shared chips are physically present in BOTH.
    assert set(SHARED_GFX) <= jp_crcs
    assert set(SHARED_GFX) <= world_crcs
    # They are different games, not two copies of one.
    assert jp_crcs != world_crcs


# --- what becomes a game, decided without asking -----------------------------
#
# Rule: a set that could not complete on its own BORROWED chips, so it is the
# release the user is adding — the archive it borrowed from was only a donor.
# Show the children; if nothing borrowed, the base release is the game.

def test_child_wins_and_the_donor_gets_no_entry(clone_zip, parent_zip):
    """The live case: wofj.zip needs wof.zip, so only wofj is a game."""
    games = cps1.plan_games([("wofj.zip", clone_zip), ("wof.zip", parent_zip)])
    assert [g.setname for g in games] == ["wofj"]
    assert games[0].borrowed_from == ("wof.zip",)
    # Both archives belong to that one game's folder.
    assert set(games[0].archives) == {"wofj.zip", "wof.zip"}


def test_a_base_release_on_its_own_is_the_game(sibling_zip, parent_zip):
    """Nothing borrowed → the complete set IS the entry."""
    games = cps1.plan_games([("wofr1.zip", sibling_zip), ("wof.zip", parent_zip)])
    assert [g.setname for g in games] == ["wofr1"]


def test_two_children_one_donor_yields_two_games_not_three(
        clone_zip, sibling_zip, parent_zip):
    games = cps1.plan_games([("wofj.zip", clone_zip), ("wofr1.zip", sibling_zip),
                             ("wof.zip", parent_zip)])
    assert sorted(g.setname for g in games) == ["wofj", "wofr1"]
    # Each carries the donor along, because each folder must stand alone.
    for g in games:
        assert "wof.zip" in g.archives


def test_a_lone_complete_archive_is_the_game(sibling_zip, parent_zip):
    combined = cps1.plan_games([("wof.zip", parent_zip)])
    assert combined == []          # four gfx chips are not a romset
    solo = cps1.plan_games([("wofr1.zip", sibling_zip), ("wof.zip", parent_zip)])
    assert [g.setname for g in solo] == ["wofr1"]


def test_a_clone_with_nothing_to_borrow_from_is_reported_not_silently_dropped(clone_zip):
    games = cps1.plan_games([("wofj.zip", clone_zip)])
    assert games == []
    ident = cps1.identify([("wofj.zip", clone_zip)])
    assert not ident.complete and ident.parent == "wof"


# --- the endpoint: drop zips in, get games out ------------------------------

def _post(client, session_id, uploads):
    return client.post(f"/api/sessions/{session_id}/roms/cps1",
                       files=[("files", (n, b, "application/zip")) for n, b in uploads])


def test_endpoint_makes_one_game_from_a_clone_and_its_donor(
        client, session_id, data_dir, clone_zip, parent_zip):
    r = _post(client, session_id, [("wofj.zip", clone_zip), ("wof.zip", parent_zip)])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] == 1, body
    game = body["results"][0]
    assert game["ok"] and game["romset"] == "wofj"
    assert game["donors"] == ["wof.zip"]

    # Both archives live in the ONE game folder; the donor is not its own entry.
    base = data_dir / "library" / session_id / "roms" / "cps1"
    dirs = [p for p in base.iterdir() if p.is_dir()]
    assert len(dirs) == 1
    assert {p.name for p in dirs[0].iterdir()} == {"wofj.zip", "wof.zip"}


def test_endpoint_reports_a_clone_uploaded_alone_instead_of_storing_half(
        client, session_id, data_dir, clone_zip):
    r = _post(client, session_id, [("wofj.zip", clone_zip)])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] == 0
    res = body["results"][0]
    assert res["error"] == "incomplete"
    # The message has to name the parent, or the user cannot act on it.
    assert "wof" in res["detail"]
    base = data_dir / "library" / session_id / "roms" / "cps1"
    assert not base.exists() or not any(p.is_dir() for p in base.iterdir())


def test_endpoint_yields_two_games_when_two_clones_share_a_donor(
        client, session_id, data_dir, clone_zip, sibling_zip, parent_zip):
    r = _post(client, session_id, [("wofj.zip", clone_zip), ("wofr1.zip", sibling_zip),
                                   ("wof.zip", parent_zip)])
    body = r.json()
    assert body["stored"] == 2, body
    base = data_dir / "library" / session_id / "roms" / "cps1"
    dirs = sorted(p for p in base.iterdir() if p.is_dir())
    assert len(dirs) == 2
    # Each folder stands alone: the donor archive is physically in both.
    for d in dirs:
        assert "wof.zip" in {p.name for p in d.iterdir()}


def test_endpoint_rejects_a_non_zip(client, session_id):
    r = _post(client, session_id, [("readme.txt", b"hello")])
    body = r.json()
    assert body["stored"] == 0
    assert body["results"][0]["error"] == "not a .zip"

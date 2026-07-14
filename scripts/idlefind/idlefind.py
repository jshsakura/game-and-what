"""Drive idlefind over a ROM directory and convert its answers to gpSP addresses.

mGBA reports the loop's START (the branch target). gpSP's gba_over.h keys on the
backward BRANCH itself — `cpu.cc` compares the PC against idle_loop_target_pc, and
that PC is the branch. So for each detected loop we disassemble forward from the
start until we find the branch that jumps back to it; that is gpSP's address.

Usage:
    idlefind.py <idlefind-binary> <rom-dir> [frames]
"""
import glob
import json
import os
import subprocess
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
BRANCHES = {"b", "beq", "bne", "bcs", "bcc", "bmi", "bpl", "bhi", "bls", "bge", "blt", "bgt", "ble"}
MAX_LOOP = 64   # a spin loop is short; if we walk further than this we've lost the thread


def game_code(path):
    with open(path, "rb") as f:
        h = f.read(0xC0)
    if len(h) < 0xC0 or h[0xB2] != 0x96:
        return None
    return h[0xAC:0xB0].decode("ascii", "replace")


def branch_pc(path, loop_start):
    """Walk forward from the loop's start to the branch that closes it."""
    off = loop_start - 0x8000000
    with open(path, "rb") as f:
        f.seek(off)
        window = f.read(MAX_LOOP)
    for ins in md.disasm(window, loop_start):
        if ins.mnemonic in BRANCHES:
            try:
                target = int(ins.op_str.lstrip("#"), 16)
            except ValueError:
                continue
            if target == loop_start:
                return ins.address
    return None


def main():
    binary, rom_dir = sys.argv[1], sys.argv[2]
    frames = sys.argv[3] if len(sys.argv) > 3 else "900"

    out = {}
    roms = sorted(glob.glob(os.path.join(rom_dir, "*.gba")))
    for i, path in enumerate(roms, 1):
        code = game_code(path)
        if not code:
            continue
        try:
            res = subprocess.run([binary, path, frames], capture_output=True, timeout=300)
            data = json.loads(res.stdout.decode().strip().splitlines()[-1])
        except Exception as exc:
            out[code] = {"name": os.path.basename(path), "error": str(exc)[:60]}
            continue

        start = data.get("loop_start")
        rec = {"name": os.path.basename(path), "loop_start": start, "frame": data.get("frame"),
               "exec_median": data.get("exec_median"), "exec_p90": data.get("exec_p90")}
        if start:
            pc = branch_pc(path, int(start, 16))
            rec["gpsp_pc"] = hex(pc) if pc else None
        out[code] = rec
        print(f"  [{i}/{len(roms)}] {code} {rec.get('gpsp_pc') or '-':>12} "
              f"{rec.get('exec_median') or 0:>7}cy  {rec['name'][:36]}", file=sys.stderr)

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

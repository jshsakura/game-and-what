"""A/B every idle-loop address: does the game actually do LESS work with it?

"exec dropped below a full frame" is not proof. A game that already waits via the BIOS
sits well under a full frame no matter what address you hand gpSP — so a bogus address
would sail through that check and ship. The only honest test is the difference:

    run with the skip DISABLED   ->  exec_off
    run with the address         ->  exec_on

If exec_on is not meaningfully lower than exec_off, the address is doing nothing and
must not be shipped. gpSP would be jumping out of the frame somewhere that is not the
wait loop.
"""
import concurrent.futures as cf
import json, os, subprocess, sys

BIN, ROOT, DB, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
FRAMES = "1200"
NO_SKIP = "0x8FFFFFE"      # a rom address the game never executes -> nothing is skipped
MIN_DROP = 0.15            # the address must cut at least 15% of the work to earn its place

BR = {"b","beq","bne","bcs","bcc","bmi","bpl","bhi","bls","bge","blt","bgt","ble"}
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

def loop_start(path, branch):
    b = int(branch, 16)
    with open(path, "rb") as f:
        f.seek(b - 0x8000000)
        ins = next(md.disasm(f.read(4), b), None)
    if ins and ins.mnemonic in BR:
        try:
            return int(ins.op_str.lstrip("#"), 16)
        except ValueError:
            return None
    return None

def run(path, forced):
    try:
        r = subprocess.run([BIN, path, FRAMES] + ([forced] if forced else []),
                           capture_output=True, timeout=300)
        return json.loads(r.stdout.decode().strip().splitlines()[-1]).get("exec_median")
    except Exception:
        return None

# Find each rom by its CART HEADER, never by filename. The library renames files, so a
# name lookup can quietly hand you a different game — it tested Mario vs. Donkey Kong's
# address against the Japanese release, which is a different rom.
import glob
BY_CODE = {}
for p in sorted(glob.glob(os.path.join(ROOT, "*.gba"))):
    with open(p, "rb") as f:
        h = f.read(0xC0)
    if len(h) < 0xC0 or h[0xB2] != 0x96:
        continue
    BY_CODE.setdefault(h[0xAC:0xB0].decode("ascii", "replace"), p)

rows = {r["game_code"]: r for r in json.load(open(DB, encoding="utf-8"))}
todo = [(c, r) for c, r in rows.items() if r.get("idle_verified")]

def check(item):
    code, r = item
    path = BY_CODE.get(code)
    if not path:
        return code, None, None, "rom not here"
    start = loop_start(path, r["idle_verified"])
    if start is None:
        return code, None, None, "not a branch"
    off = run(path, NO_SKIP)
    on = run(path, hex(start))
    return code, off, on, None

out = {}
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    for code, off, on, err in ex.map(check, todo):
        if err or not off or not on:
            out[code] = {"ok": False, "why": err or "no reading"}
            print(f"  ?  {code}  {err or 'no reading'}", flush=True)
            continue
        drop = (off - on) / off
        ok = drop >= MIN_DROP
        out[code] = {"ok": ok, "exec_off": off, "exec_on": on, "drop": round(drop, 3)}
        print(f"  {'OK' if ok else 'XX'} {code}  off={off:>7} on={on:>7}  drop={drop*100:5.1f}%", flush=True)

json.dump(out, open(OUT, "w"), indent=1)
good = sum(1 for v in out.values() if v["ok"])
print(f"\n{len(out)} 검증 / 진짜 {good} / 가짜·불명 {len(out)-good}")

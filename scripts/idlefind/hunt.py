"""Stop guessing the loop's shape. Try every address the frame is burning, and let the
A/B decide.

The disassembly-led hunts kept missing real loops because they assumed a loop is a body
with a backward branch at the end. Super Mario Advance is not:

    0x8001cde  body: poll the flag the VBlank IRQ sets
    0x8001cf2  beq  #0x8001cfc      <- what libretro and ReGBA both ship
    0x8001cfc  b    #0x8001cbc
    0x8001cbc  b    #0x8001cde      <- three hops, back to the body

It hops three times. mGBA's detector cannot see it either — the detector wants the same
jump target twice in a row (memory.c:263) and this loop lands somewhere different each
hop, which is exactly why games like this ended up "unmeasured" and looking heavy.

So: no shape assumptions. Take the addresses the frame's cycles actually went to and
force each one in turn. If it is a landing point of the wait, mGBA halts there and the
work collapses; if it is not, mGBA never halts and nothing happens. Either way the A/B
answers, and the answer is what we keep:

    exec drops >= 15%   — the address is where the frame was going
    seq is IDENTICAL    — and skipping it changed nothing the game drew

gpSP compares reg[REG_PC] after every instruction (cpu.cc:3063), so any address the loop
executes on every iteration works — the landing point included. We ship the backward
branch when the loop has one we can read (that is upstream's convention and the other 89
addresses' too), and the proven landing point when it does not.
"""
import concurrent.futures as cf
import glob, json, os, subprocess, sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM

BIN, ROOT, TODO, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
FRAMES = "1500"
NO_SKIP = "0x8FFFFFE"
MIN_DROP = 0.15
GOOD_ENOUGH = 0.40       # a wait loop gives up far more than the bar; take it and move on
MAX_TRIES = 20           # the hottest 20 addresses; a wait loop is never colder than that
NEAR = 96                # how far around the hot region we look for the closing branch

# What "the skip changed nothing" has to mean.
#
# Frame-for-frame equality was too strict and threw away a real loop. Final Fight One
# keeps 99.8% of its frames and every one of its screens when its wait is skipped — the
# two runs differ on a couple of frames out of 1200, because the halt lands on the event
# boundary a touch differently. That game is fine.
#
# What is NOT fine is a game that goes somewhere else. Bomberman Max 2's hot loop drops
# 60% of the frame and the run still renders — but only HALF its screens are screens the
# unskipped run ever drew. It did not shift; it diverged. And a broken skip is starker
# still: Gunstar freezes on one single frame forever.
#
# So the test is the set of screens the game reached. Shared ~100% -> the skip removed
# waiting. Shared half -> it removed work, and we do not ship it.
SAME_SCREENS = 0.97

BRANCHES = {"b", "beq", "bne", "bcs", "bcc", "bmi", "bpl", "bhi", "bls", "bge", "blt", "bgt", "ble"}
md_thumb = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md_arm = Cs(CS_ARCH_ARM, CS_MODE_ARM)


ENV = dict(os.environ, IDLEFIND_HASHES="1")


def run(path, forced):
    try:
        r = subprocess.run([BIN, path, FRAMES] + ([forced] if forced else []),
                           capture_output=True, timeout=600, env=ENV)
        return json.loads(r.stdout.decode(errors="replace").strip().splitlines()[-1])
    except Exception:
        return None


def screens_shared(off_frames, on_frames):
    """How much of what the game drew is the same, as a set. Frozen -> ~0. Waiting -> ~1."""
    a, b = set(off_frames or []), set(on_frames or [])
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def bytemap(mem):
    out = {}
    for pc_hex, blob in (mem or {}).items():
        base = int(pc_hex, 16)
        for i, b in enumerate(bytes.fromhex(blob)):
            out[base + i] = b
    return out


def slab(bmap, lo, hi):
    out = bytearray()
    for a in range(lo, hi):
        if a not in bmap:
            break
        out.append(bmap[a])
    return bytes(out)


def closing_branch(bmap, start, hot_pcs):
    """The branch that jumps back into the loop — gpSP's conventional key.

    Read forward from the loop's landing point and take the first branch that lands back
    on an address the loop is executing. None is not a failure: the landing point is a
    valid key too, because gpSP checks the PC after every instruction.
    """
    for anchor in sorted(p for p in hot_pcs if abs(p - start) <= NEAR):
        code = slab(bmap, anchor, anchor + NEAR)
        if not code:
            continue
        for md in (md_thumb, md_arm):
            for ins in md.disasm(code, anchor):
                if ins.mnemonic not in BRANCHES:
                    continue
                try:
                    target = int(ins.op_str.lstrip("#"), 16)
                except ValueError:
                    continue
                if target <= ins.address and target in hot_pcs:
                    return ins.address
    return None


BY_CODE = {}
for p in sorted(glob.glob(os.path.join(ROOT, "*.gba"))):
    with open(p, "rb") as f:
        h = f.read(0xC0)
    if len(h) < 0xC0 or h[0xB2] != 0x96:
        continue
    BY_CODE.setdefault(h[0xAC:0xB0].decode("ascii", "replace"), p)


def hunt(code):
    path = BY_CODE.get(code)
    if not path:
        return code, {"ok": False, "why": "rom not here"}

    off = run(path, NO_SKIP)
    if not off or not off.get("exec_median"):
        return code, {"ok": False, "why": "no reading"}
    off_exec, off_seq, off_frames = off["exec_median"], off["seq"], off.get("frames")
    hot = [(int(pc, 16), cy) for pc, cy in (off.get("hot") or [])]
    bmap = bytemap(off.get("mem"))
    hot_pcs = {pc for pc, _ in hot}

    tried, best, broke = [], None, False
    for pc, _cy in hot[:MAX_TRIES]:
        on = run(path, hex(pc))
        if not on or not on.get("exec_median"):
            continue
        drop = (off_exec - on["exec_median"]) / off_exec
        exact = on["seq"] == off_seq
        shared = screens_shared(off_frames, on.get("frames"))
        safe = exact or shared >= SAME_SCREENS
        tried.append({"pc": hex(pc), "drop": round(drop, 3), "exact": exact,
                      "shared": round(shared, 3), "distinct": on.get("distinct")})
        if drop >= MIN_DROP and not safe:
            broke = True            # hot, and the game went somewhere else: real work
        if drop >= MIN_DROP and safe and (best is None or drop > best["drop"]):
            best = {"start": hex(pc), "exec_on": on["exec_median"], "drop": round(drop, 3),
                    "exact": exact, "shared": round(shared, 3)}
            if drop >= GOOD_ENOUGH:
                break

    if best:
        start = int(best["start"], 16)
        br = closing_branch(bmap, start, hot_pcs)
        return code, {"ok": True, "start": best["start"],
                      "gpsp_pc": hex(br) if br else best["start"],
                      "gpsp_pc_is_branch": br is not None,
                      "exec_off": off_exec, "exec_on": best["exec_on"], "drop": best["drop"],
                      # exact: every frame identical. shared: the screens it reached.
                      "exact": best["exact"], "shared": best["shared"],
                      "tried": tried, "name": os.path.basename(path)}

    why = ("hot loop is real work (skipping it sent the game elsewhere)" if broke
           else "nothing to skip — the frame is spread over real code")
    return code, {"ok": False, "why": why, "exec_off": off_exec, "tried": tried,
                  "name": os.path.basename(path)}


todo = json.load(open(TODO, encoding="utf-8"))
out = {}
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    for code, v in ex.map(hunt, [r["code"] for r in todo]):
        out[code] = v
        if v["ok"]:
            tier = "exact" if v["exact"] else f"screens {v['shared']*100:.1f}%"
            print(f"  OK {code}  {v['gpsp_pc']:>10}  {v['exec_off']:>7} -> {v['exec_on']:>7} "
                  f"({v['drop']*100:4.1f}%)  [{tier}]  {(v.get('name') or '')[:28]}", flush=True)
        else:
            print(f"  -- {code}  {v['why']}  {(v.get('name') or '')[:30]}", flush=True)

json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
good = [c for c, v in out.items() if v["ok"]]
print(f"\n{len(out)} 추적 / 루프 찾음 {len(good)} / 스킵할 것 없음 {len(out) - len(good)}")

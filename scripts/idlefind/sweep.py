"""Run idlefind over the whole GBA set, 4 at a time.

Pass 1 only: let mGBA detect. A rom that comes back with no loop AND a full frame of
work (280,896 cycles) is not a heavy game — it is a rom whose loop we failed to find,
and it goes on a second list to chase separately.
"""
import concurrent.futures as cf
import glob, json, os, subprocess, sys

BIN, ROOT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
FRAMES = "1500"
FRAME = 280896

def code_of(p):
    with open(p, "rb") as f:
        h = f.read(0xC0)
    if len(h) < 0xC0 or h[0xB2] != 0x96:
        return None
    return h[0xAC:0xB0].decode("ascii", "replace")

def probe(path):
    code = code_of(path)
    if not code:
        return None
    try:
        r = subprocess.run([BIN, path, FRAMES], capture_output=True, timeout=300)
        d = json.loads(r.stdout.decode().strip().splitlines()[-1])
    except Exception as e:
        return {"code": code, "name": os.path.basename(path), "error": str(e)[:40]}
    return {"code": code, "name": os.path.basename(path),
            "loop_start": d.get("loop_start"),
            "exec_median": d.get("exec_median"), "exec_p90": d.get("exec_p90")}

roms = sorted(glob.glob(os.path.join(ROOT, "*.gba")))
out, done = {}, 0
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    for r in ex.map(probe, roms):
        done += 1
        if not r:
            continue
        out[r["code"]] = r
        if done % 25 == 0:
            print(f"  {done}/{len(roms)}", flush=True)
json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)

found = [r for r in out.values() if r.get("loop_start")]
stuck = [r for r in out.values() if not r.get("loop_start") and (r.get("exec_median") or 0) > 0.9 * FRAME]
light = [r for r in out.values() if not r.get("loop_start") and (r.get("exec_median") or 0) <= 0.9 * FRAME]
print(f"\n{len(out)} roms")
print(f"  루프 탐지        : {len(found)}")
print(f"  루프 없음 + 가벼움: {len(light)}   (BIOS halt로 이미 쉬는 게임)")
print(f"  루프 못 찾음      : {len(stuck)}   <- 따로 추적 필요")

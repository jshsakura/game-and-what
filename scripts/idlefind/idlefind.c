// Answer two questions about a GBA ROM by RUNNING it:
//
//   1. Where is its VBlank idle loop?  gpSP can only skip a loop it has in its
//      table, and a game it doesn't have spins through the whole frame.
//   2. How much work does it ACTUALLY do per frame?  That is what decides whether
//      the skip is enough to hit full speed on the Game & Watch's M7 — and the
//      idle-loop flag alone never told us.
//
// (1) cannot be done statically: a spin loop and an ordinary polling loop are the
// same shape in a disassembly, and a 1MB ROM offers ~95 candidates. Behaviour is
// what separates them, and mGBA's IDLE_LOOP_DETECT already watches for it — it
// re-walks a backward branch's body tracking provably-unchanged registers, and if
// the body has no side effects and cannot exit on its own, records the loop
// (src/gba/memory.c). mGBA records the loop's START; gpSP's gba_over.h keys on the
// backward BRANCH, so idlefind.py converts.
//
// (2) uses gIdleFindExecCycles, patched into ARMRunLoop (src/arm/arm.c). It counts
// only cycles spent EXECUTING instructions: idle-skip and HALT jump the clock
// forward outside that loop, so they never land in the count. What's left per frame
// is the game's real work, against a 280896-cycle frame.
//
// Init order follows mGBA's own headless harness (src/platform/test/fuzz-main.c);
// skipping mCoreInitConfig segfaults on reset.
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mgba-util/common.h>
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/gba/core.h>
#include <mgba/internal/gba/gba.h>
#include <mgba-util/vfs.h>

extern uint64_t gIdleFindExecCycles;   // patched into src/arm/arm.c

#define DEFAULT_FRAMES 1800    // ~30 s of play
#define WARMUP_FRAMES 240      // skip the BIOS + logo: not representative of the game
#define GBA_FRAME_CYCLES 280896

static int cmp_u32(const void* a, const void* b) {
	uint32_t x = *(const uint32_t*) a, y = *(const uint32_t*) b;
	return (x > y) - (x < y);
}

int main(int argc, char** argv) {
	if (argc < 2) {
		fprintf(stderr, "usage: idlefind <rom.gba> [frames]\n");
		return 2;
	}
	int frames = argc > 2 ? atoi(argv[2]) : DEFAULT_FRAMES;
	// Optional 3rd arg: a loop START address we already know. When detection fails,
	// the spin keeps executing and the cycle count comes back pinned at a full frame
	// (280896) — which reads as "heavy game" when it actually means "loop not found".
	// Feeding the known address makes the measurement mean what it claims.
	uint32_t forced_loop = argc > 3 ? (uint32_t) strtoul(argv[3], NULL, 0) : 0;

	// GBACoreCreate, not mCoreFind: the latter came back with a null init vtable in
	// this minimal build and jumped straight to 0x0.
	struct mCore* core = GBACoreCreate();
	if (!core || !core->init(core)) {
		fprintf(stderr, "core init failed\n");
		return 1;
	}
	mCoreInitConfig(core, "idlefind");
	mCoreConfigSetDefaultValue(&core->config, "idleOptimization", "detect");

	void* buf = malloc(256 * 256 * 4);
	core->setVideoBuffer(core, buf, 256);

	if (!mCoreLoadFile(core, argv[1])) {
		fprintf(stderr, "load failed: %s\n", argv[1]);
		return 1;
	}
	core->reset(core);

	struct GBA* gba = (struct GBA*) core->board;
	gba->hardCrash = false;
	// AFTER reset, not before: reset applies mGBA's own override database, which for
	// a game it already knows fills in idleLoop and flips idleOptimization to REMOVE
	// — detection then never runs and we learn nothing. Force DETECT so the answer
	// comes from the ROM's behaviour, not from mGBA's existing table.
	if (forced_loop) {
		gba->idleLoop = forced_loop;
		gba->idleOptimization = IDLE_LOOP_REMOVE;
	} else {
		gba->idleLoop = GBA_IDLE_LOOP_NONE;
		gba->idleOptimization = IDLE_LOOP_DETECT;
	}

	// Mash START / A. Left alone, most games sit on a title screen and never reach
	// the wait we're after — that alone accounted for every ROM the first pass failed
	// to detect. Alternate the two, with gaps, so menus advance instead of a held
	// button being swallowed as a single press.
	const uint32_t KEY_A = 1 << 0;
	const uint32_t KEY_START = 1 << 3;

	uint32_t* samples = calloc(frames, sizeof(uint32_t));
	int nsamples = 0;
	int found_at = forced_loop ? 0 : -1;
	// GBA_IDLE_LOOP_NONE is 0xFFFFFFFF, not 0 — seeding this with a bare `forced_loop`
	// (i.e. 0 when nothing was forced) made an UNDETECTED rom report a loop at
	// 0x00000000, which then read as an IWRAM loop downstream.
	uint32_t idle_loop = forced_loop ? forced_loop : GBA_IDLE_LOOP_NONE;

	for (int i = 0; i < frames; ++i) {
		int phase = i % 40;
		core->setKeys(core, phase < 6 ? KEY_START : (phase >= 20 && phase < 26 ? KEY_A : 0));

		gIdleFindExecCycles = 0;
		core->runFrame(core);

		if (found_at < 0 && gba->idleLoop != GBA_IDLE_LOOP_NONE) {
			found_at = i;
			idle_loop = gba->idleLoop;
			// mGBA flips to REMOVE the moment it detects, so from here on the spin is
			// skipped and the cycle count reflects real work — which is what we sample.
		}
		if (i >= WARMUP_FRAMES) {
			samples[nsamples++] = (uint32_t) gIdleFindExecCycles;
		}
	}

	uint32_t median = 0, p90 = 0;
	if (nsamples) {
		qsort(samples, nsamples, sizeof(uint32_t), cmp_u32);
		median = samples[nsamples / 2];
		p90 = samples[(nsamples * 9) / 10];
	}

	printf("{");
	if (idle_loop != GBA_IDLE_LOOP_NONE) {
		printf("\"loop_start\": \"0x%08x\", \"frame\": %d, ", idle_loop, found_at);
	} else {
		printf("\"loop_start\": null, ");
	}
	printf("\"exec_median\": %u, \"exec_p90\": %u, \"frame_cycles\": %d, \"samples\": %d}\n",
	       median, p90, GBA_FRAME_CYCLES, nsamples);

	free(samples);
	free(buf);
	core->deinit(core);
	return 0;
}

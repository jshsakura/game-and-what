// idlefind — run a GBA game and answer two questions the cart header cannot.
//
//   1. WHERE IS ITS VBLANK WAIT LOOP?  gpSP can only skip a loop it has been given, and a
//      game it has not been given busy-waits through the whole 280,896-cycle frame.
//   2. HOW MUCH WORK DOES IT ACTUALLY DO?  Knowing the loop only says the skip is
//      available. gIdleFindExecCycles (patched into ARMRunLoop) counts only the cycles
//      spent EXECUTING — idle-skip and HALT move the clock forward outside that loop — so
//      what is left, per frame, is the game's real work.
//
// Neither can be read off the rom: a spin loop and an ordinary polling loop are the same
// shape in a disassembly. So we run it. Usage:
//
//     idlefind rom.gba [frames] [forced_loop_start]
//       (no address)  -> let mGBA's detector look
//       0x8FFFFFE     -> a pc the game never executes: nothing is skipped (the A/B's "off")
//       <address>     -> halt there (the A/B's "on")
//     IDLEFIND_HASHES=1 also dumps every frame's hash, which is what tells a game that
//     merely waits less from one that has been strangled.
//
// The detector only records a loop it can PROVE is idle: it re-walks the body and
// gives up if anything in there has a side effect. Plenty of real wait loops do have
// one (they poke a register, bump a counter, feed the sound driver), and gpSP happily
// skips those anyway — its check is a bare PC compare. For those games the detector is
// silent and we have to find the loop ourselves.
//
// So: ask the frame where its cycles went. A game that is waiting spends the frame in
// the wait — that is what waiting IS — so the loop is at the top of a per-PC cycle
// histogram (gIdleFindPcHist, patched into src/arm/arm.c). Ranking is all this does;
// the ranking is a HYPOTHESIS, and ab3.py is what turns it into evidence.
//
// It also prints `seq`, a rolling digest of every rendered frame. That is the check the
// forced-address path could not do without: an idle skip must not change what the game
// draws, because all it removes is waiting. Same input, same rom, same frames — mGBA is
// deterministic — so if `seq` with the address differs from `seq` without it, the
// address is not a wait loop, whatever it did to the cycle count.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mgba-util/common.h>
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/gba/core.h>
#include <mgba/internal/gba/gba.h>

extern uint64_t gIdleFindExecCycles;
extern uint32_t* gIdleFindPcHist;
extern uint32_t gIdleFindPcHistLen;
extern uint32_t* gIdleFindEwramHist;
extern uint32_t* gIdleFindIwramHist;

#define DEFAULT_FRAMES 3000
#define WARMUP_FRAMES 300
#define GBA_FRAME_CYCLES 280896
#define ROM_BASE 0x08000000
#define EWRAM_BASE 0x02000000
#define EWRAM_LEN (256 * 1024)
#define IWRAM_BASE 0x03000000
#define IWRAM_LEN (32 * 1024)
#define TOP_PCS 64
#define MEM_WINDOW 64          // bytes dumped around each hot pc, for the disassembler
#define MAX_BLOCK 4096         // the biggest code block we will look for at run time
#define HASH_STRIDE 7
#define MAX_DISTINCT 4096

enum { KEY_A = 1 << 0, KEY_B = 1 << 1, KEY_SELECT = 1 << 2, KEY_START = 1 << 3,
       KEY_RIGHT = 1 << 4, KEY_LEFT = 1 << 5, KEY_UP = 1 << 6, KEY_DOWN = 1 << 7,
       KEY_R = 1 << 8, KEY_L = 1 << 9 };

// Same script as idlefind2, and it must STAY the same: an A/B is only a comparison if
// both runs saw the same buttons.
static uint32_t keys_for(int frame) {
	int p = frame % 240;
	if (p < 6) return KEY_START;
	if (p >= 20 && p < 26) return KEY_A;
	if (p >= 40 && p < 46) return KEY_B;
	if (p >= 60 && p < 66) return KEY_DOWN;
	if (p >= 76 && p < 82) return KEY_A;
	if (p >= 96 && p < 102) return KEY_RIGHT;
	if (p >= 116 && p < 122) return KEY_START;
	if (p >= 136 && p < 142) return KEY_UP;
	if (p >= 156 && p < 162) return KEY_A;
	if (p >= 176 && p < 182) return KEY_LEFT;
	if (p >= 196 && p < 202) return KEY_L;
	if (p >= 210 && p < 216) return KEY_R;
	return 0;
}

static int cmp_u32(const void* a, const void* b) {
	uint32_t x = *(const uint32_t*) a, y = *(const uint32_t*) b;
	return (x > y) - (x < y);
}

static uint32_t frame_hash(const mColor* buf) {
	uint32_t h = 2166136261u;
	for (int y = 0; y < 160; y += 2) {
		for (int x = 0; x < 240; x += HASH_STRIDE) {
			h = (h ^ buf[y * 256 + x]) * 16777619u;
		}
	}
	return h;
}

int main(int argc, char** argv) {
	if (argc < 2) {
		fprintf(stderr, "usage: idlefind <rom.gba> [frames] [forced_loop_start]\n");
		return 2;
	}
	int frames = argc > 2 ? atoi(argv[2]) : DEFAULT_FRAMES;
	uint32_t forced_loop = argc > 3 ? (uint32_t) strtoul(argv[3], NULL, 0) : 0;

	FILE* f = fopen(argv[1], "rb");
	if (!f) {
		fprintf(stderr, "open failed: %s\n", argv[1]);
		return 1;
	}
	fseek(f, 0, SEEK_END);
	long rom_size = ftell(f);
	fclose(f);

	struct mCore* core = GBACoreCreate();
	if (!core || !core->init(core)) {
		fprintf(stderr, "core init failed\n");
		return 1;
	}
	mCoreInitConfig(core, "idlefind");
	mCoreConfigSetDefaultValue(&core->config, "idleOptimization", "detect");

	mColor* buf = malloc(256 * 256 * sizeof(mColor));
	core->setVideoBuffer(core, buf, 256);

	if (!mCoreLoadFile(core, argv[1])) {
		fprintf(stderr, "load failed: %s\n", argv[1]);
		return 1;
	}
	core->reset(core);

	struct GBA* gba = (struct GBA*) core->board;
	gba->hardCrash = false;
	if (forced_loop) {
		gba->idleLoop = forced_loop;
		gba->idleOptimization = IDLE_LOOP_REMOVE;
	} else {
		// Detection stays ON even while we histogram: if mGBA can answer, take its
		// answer — it is the one that comes with a proof attached.
		gba->idleLoop = GBA_IDLE_LOOP_NONE;
		gba->idleOptimization = IDLE_LOOP_DETECT;
	}

	gIdleFindPcHistLen = (uint32_t) (rom_size / 2);
	gIdleFindPcHist = calloc(gIdleFindPcHistLen, sizeof(uint32_t));
	gIdleFindEwramHist = calloc(EWRAM_LEN / 2, sizeof(uint32_t));
	gIdleFindIwramHist = calloc(IWRAM_LEN / 2, sizeof(uint32_t));
	if (!gIdleFindPcHist || !gIdleFindEwramHist || !gIdleFindIwramHist) {
		fprintf(stderr, "histogram alloc failed\n");
		return 1;
	}

	uint32_t* samples = calloc(frames, sizeof(uint32_t));
	uint32_t* seen = calloc(MAX_DISTINCT, sizeof(uint32_t));
	// Every frame's hash, in order. `seq` says "the run differed"; this says HOW — a
	// game that broke and a game whose animation merely shifted a frame both fail seq,
	// and they are not remotely the same answer.
	uint32_t* fhash = calloc(frames, sizeof(uint32_t));
	int nfh = 0;
	const int dump_hashes = getenv("IDLEFIND_HASHES") != NULL;
	int nsamples = 0, ndistinct = 0;
	int found_at = forced_loop ? 0 : -1;
	uint32_t idle_loop = forced_loop ? forced_loop : GBA_IDLE_LOOP_NONE;
	uint32_t seq = 2166136261u;

	// IDLEFIND_BLOCK=<hex>: a block of code, cut out of the rom, that we want the cost of.
	//
	// A GBA game's sound driver (M4A/Sappy, GAX) is a library it links in and COPIES INTO
	// IWRAM at boot, then runs there every frame. The firmware replaces that driver with a
	// native one, so the guest never executes it — which means the work is real here and
	// gone on the device, and a CPU figure that includes it is wrong by however much the
	// game's music costs. On Zelda that is 60% of the frame.
	//
	// We do not model it. The block's bytes are in the rom, so: find where they landed in
	// RAM, then add up the cycles the histogram already charged to that range. Measured,
	// per game, in the same run as everything else.
	uint8_t block[MAX_BLOCK];
	int block_len = 0;
	const char* block_hex = getenv("IDLEFIND_BLOCK");
	if (block_hex) {
		int n = (int) strlen(block_hex) / 2;
		if (n > MAX_BLOCK) {
			n = MAX_BLOCK;
		}
		for (int i = 0; i < n; ++i) {
			unsigned byte = 0;
			if (sscanf(block_hex + i * 2, "%2x", &byte) != 1) {
				break;
			}
			block[block_len++] = (uint8_t) byte;
		}
	}

	for (int i = 0; i < frames; ++i) {
		core->setKeys(core, keys_for(i));
		if (i == WARMUP_FRAMES) {
			// Throw the boot away: logos, BIOS, decompression. None of it is the game
			// waiting, and all of it would outrank the wait in the histogram.
			memset(gIdleFindPcHist, 0, (size_t) gIdleFindPcHistLen * sizeof(uint32_t));
			memset(gIdleFindEwramHist, 0, (EWRAM_LEN / 2) * sizeof(uint32_t));
			memset(gIdleFindIwramHist, 0, (IWRAM_LEN / 2) * sizeof(uint32_t));
		}

		gIdleFindExecCycles = 0;
		core->runFrame(core);

		if (found_at < 0 && gba->idleLoop != GBA_IDLE_LOOP_NONE) {
			found_at = i;
			idle_loop = gba->idleLoop;
		}
		if (i >= WARMUP_FRAMES) {
			samples[nsamples++] = (uint32_t) gIdleFindExecCycles;
			uint32_t h = frame_hash(buf);
			fhash[nfh++] = h;
			seq = (seq ^ h) * 16777619u;
			int dup = 0;
			for (int j = 0; j < ndistinct; ++j) {
				if (seen[j] == h) { dup = 1; break; }
			}
			if (!dup && ndistinct < MAX_DISTINCT) {
				seen[ndistinct++] = h;
			}
		}
	}

	uint32_t median = 0, p90 = 0;
	if (nsamples) {
		qsort(samples, nsamples, sizeof(uint32_t), cmp_u32);
		median = samples[nsamples / 2];
		p90 = samples[(nsamples * 9) / 10];
	}

	// Top PCs by cycles charged, across all three regions a game can run from. A tight
	// spin shows up as a run of neighbouring hot halfwords; the python side clusters
	// them and picks out the branch that closes the loop.
	uint32_t top_pc[TOP_PCS] = {0};
	uint32_t top_cy[TOP_PCS] = {0};
	struct { const uint32_t* hist; uint32_t len; uint32_t base; } regions[] = {
		{ gIdleFindPcHist, gIdleFindPcHistLen, ROM_BASE },
		{ gIdleFindEwramHist, EWRAM_LEN / 2, EWRAM_BASE },
		{ gIdleFindIwramHist, IWRAM_LEN / 2, IWRAM_BASE },
	};
	for (int r = 0; r < 3; ++r) {
		for (uint32_t i = 0; i < regions[r].len; ++i) {
			uint32_t cy = regions[r].hist[i];
			if (cy <= top_cy[TOP_PCS - 1]) {
				continue;
			}
			int j = TOP_PCS - 1;
			while (j > 0 && top_cy[j - 1] < cy) {
				top_cy[j] = top_cy[j - 1];
				top_pc[j] = top_pc[j - 1];
				--j;
			}
			top_cy[j] = cy;
			top_pc[j] = regions[r].base + (i << 1);
		}
	}

	printf("{");
	if (idle_loop != GBA_IDLE_LOOP_NONE) {
		printf("\"loop_start\": \"0x%08x\", \"frame\": %d, ", idle_loop, found_at);
	} else {
		printf("\"loop_start\": null, ");
	}
	printf("\"exec_median\": %u, \"exec_p90\": %u, \"distinct\": %d, \"seq\": \"0x%08x\", "
	       "\"frame_cycles\": %d, \"samples\": %d, \"hot\": [",
	       median, p90, ndistinct, seq, GBA_FRAME_CYCLES, nsamples);
	for (int i = 0; i < TOP_PCS && top_cy[i]; ++i) {
		printf("%s[\"0x%08x\", %u]", i ? ", " : "", top_pc[i], top_cy[i]);
	}
	// The code at a hot RAM pc is not in the rom file — it was copied there at boot —
	// so the disassembler cannot read it off disk. Hand it the bytes.
	printf("], \"mem\": {");
	for (int i = 0; i < TOP_PCS && top_cy[i]; ++i) {
		printf("%s\"0x%08x\": \"", i ? ", " : "", top_pc[i]);
		for (int b = 0; b < MEM_WINDOW; ++b) {
			printf("%02x", core->busRead8(core, top_pc[i] + b) & 0xFF);
		}
		printf("\"");
	}
	printf("}");    // closes "mem"
	// Where did the block land, and what did it cost? Search the regions a driver is
	// copied into (IWRAM first — that is where a sound driver goes, for the speed), then
	// sum the cycles the histogram charged to it.
	if (block_len > 0) {
		uint32_t base = 0, cycles = 0;
		struct { uint32_t addr; uint32_t len; const uint32_t* hist; } regions[] = {
			{ IWRAM_BASE, IWRAM_LEN, gIdleFindIwramHist },
			{ EWRAM_BASE, EWRAM_LEN, gIdleFindEwramHist },
		};
		for (int r = 0; r < 2 && !base; ++r) {
			for (uint32_t off = 0; off + (uint32_t) block_len <= regions[r].len; off += 2) {
				int same = 1;
				for (int b = 0; b < block_len; ++b) {
					if ((core->busRead8(core, regions[r].addr + off + b) & 0xFF) != block[b]) {
						same = 0;
						break;
					}
				}
				if (!same) {
					continue;
				}
				base = regions[r].addr + off;
				for (int b = 0; b < block_len; b += 2) {
					cycles += regions[r].hist[(off + b) >> 1];
				}
				break;
			}
		}
		printf(", \"block_base\": \"0x%08x\", \"block_cycles\": %u",
		       base, nsamples ? cycles / (uint32_t) nsamples : 0);
	}

	if (dump_hashes) {
		printf(", \"frames\": [");
		for (int i = 0; i < nfh; ++i) {
			printf("%s%u", i ? "," : "", fhash[i]);
		}
		printf("]");
	}
	printf("}\n");

	free(gIdleFindPcHist);
	free(gIdleFindEwramHist);
	free(gIdleFindIwramHist);
	free(samples);
	free(seen);
	free(fhash);
	free(buf);
	core->deinit(core);
	return 0;
}

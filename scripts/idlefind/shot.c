// Render a GBA ROM headless and dump a frame as PNG — the only way to tell a Korean
// fan-patch from the original: the patch keeps the cart header, so nothing outside
// the picture gives it away.
#include <stdio.h>
#include <stdlib.h>
#include <mgba-util/common.h>
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/gba/core.h>
#include <mgba/internal/gba/gba.h>
#include <mgba-util/vfs.h>
#include <mgba-util/image/png-io.h>

int main(int argc, char** argv) {
	if (argc < 4) { fprintf(stderr, "usage: shot <rom> <frames> <out.png>\n"); return 2; }
	int frames = atoi(argv[2]);
	struct mCore* core = GBACoreCreate();
	core->init(core);
	mCoreInitConfig(core, "shot");
	void* buf = malloc(256 * 256 * 4);
	core->setVideoBuffer(core, buf, 256);
	if (!mCoreLoadFile(core, argv[1])) { fprintf(stderr, "load failed\n"); return 1; }
	core->reset(core);
	((struct GBA*) core->board)->hardCrash = false;
	for (int i = 0; i < frames; ++i) {
		int phase = i % 40;
		core->setKeys(core, phase < 6 ? (1 << 3) : (phase >= 20 && phase < 26 ? (1 << 0) : 0));
		core->runFrame(core);
	}
	unsigned w, h;
	core->currentVideoSize(core, &w, &h);
	struct VFile* out = VFileOpen(argv[3], O_WRONLY | O_CREAT | O_TRUNC);
	png_structp png = PNGWriteOpen(out);
	png_infop info = PNGWriteHeader(png, w, h, mCOLOR_XBGR8);
	PNGWritePixels(png, w, h, 256, buf, mCOLOR_XBGR8);
	PNGWriteClose(png, info);
	out->close(out);
	printf("%ux%u -> %s\n", w, h, argv[3]);
	return 0;
}

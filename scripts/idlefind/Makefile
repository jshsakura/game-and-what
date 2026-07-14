# Build the `idlefind` binary: mGBA, patched, driven headless.
#
#     make            -> ./idlefind
#     make check      -> build it and prove it runs
#     make clean      -> drop the build, keep the mGBA clone
#     make distclean  -> drop everything
#
# The binary is mGBA with two instruments patched in (mgba-cycle-counter.patch):
#   * a per-frame counter of cycles actually EXECUTING instructions — idle-skip and HALT
#     move the clock forward outside that loop, so what is left is the game's real work;
#   * a per-PC cycle histogram, which is how we find a wait loop the detector cannot see.
#
# THE BUILD FLAGS ARE NOT OPTIONAL. `struct mCore`'s layout depends on mGBA's own cmake
# flags (ENABLE_DEBUGGERS alone changes its size by 4 KB), so a tool compiled against a
# different set gets a null vtable and segfaults on the first call — silently, at run time.
# That is why the recipe below reads mGBA's flags back out of its own build and compiles
# with those, rather than guessing them.

MGBA_REPO   ?= https://github.com/mgba-emu/mgba.git
MGBA_COMMIT ?= 5157ce208a5965e8a47bf5b48b5aae5198c22a5e
JOBS        ?= $(shell nproc 2>/dev/null || echo 4)

MGBA  := mgba
BUILD := $(MGBA)/build
LIB   := $(BUILD)/libmgba.a

.PHONY: all check clean distclean

all: idlefind

$(MGBA):
	git clone $(MGBA_REPO) $(MGBA)
	cd $(MGBA) && git checkout $(MGBA_COMMIT) && git apply ../mgba-cycle-counter.patch

$(LIB): | $(MGBA)
	mkdir -p $(BUILD)
	cd $(BUILD) && cmake .. -DCMAKE_BUILD_TYPE=Release \
	    -DBUILD_QT=OFF -DBUILD_SDL=OFF -DBUILD_GL=OFF -DBUILD_GLES2=OFF -DBUILD_GLES3=OFF \
	    -DUSE_FFMPEG=OFF -DUSE_DISCORD_RPC=OFF -DUSE_LIBZIP=OFF -DUSE_SQLITE3=OFF \
	    -DUSE_ELF=OFF -DUSE_EDITLINE=OFF -DBUILD_SHARED=OFF -DBUILD_STATIC=ON \
	    -DENABLE_SCRIPTING=OFF
	$(MAKE) -C $(BUILD) -j$(JOBS) mgba

# Compile with mGBA's OWN flags — read back out of its build, never guessed. See above.
idlefind: idlefind.c $(LIB)
	grep '^C_DEFINES'  $(BUILD)/CMakeFiles/mgba.dir/flags.make | sed 's/^C_DEFINES *= *//'  > .defs.rsp
	grep '^C_INCLUDES' $(BUILD)/CMakeFiles/mgba.dir/flags.make | sed 's/^C_INCLUDES *= *//' > .incs.rsp
	gcc -O2 @.defs.rsp @.incs.rsp -o $@ idlefind.c $(LIB) -lz -lpng -lm -lpthread -ldl

# shot: render one frame to a png. The ONLY way to tell a Korean patch from the original —
# nothing in the header, the filename or the region code says so. Only the screen does.
shot: shot.c $(LIB)
	grep '^C_DEFINES'  $(BUILD)/CMakeFiles/mgba.dir/flags.make | sed 's/^C_DEFINES *= *//'  > .defs.rsp
	grep '^C_INCLUDES' $(BUILD)/CMakeFiles/mgba.dir/flags.make | sed 's/^C_INCLUDES *= *//' > .incs.rsp
	gcc -O2 @.defs.rsp @.incs.rsp -o $@ shot.c $(LIB) -lz -lpng -lm -lpthread -ldl

check: idlefind
	./idlefind 2>&1 | grep -q usage && echo "idlefind: builds, links and starts"
	python3 -m pytest tests -q

clean:
	rm -rf $(BUILD) idlefind shot .defs.rsp .incs.rsp

distclean: clean
	rm -rf $(MGBA)

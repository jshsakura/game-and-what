// In-browser game runner. Clicking ▶ on a ROM launches it via Nostalgist.js,
// which loads the matching libretro core (compiled to WASM) from its default CDN
// and runs the raw ROM bytes our backend serves.
//
// Display modes (so trying games one-by-one from the list isn't disruptive):
//   window → centered popup, the library stays visible/dimmed behind it (default on PC)
//   max    → fills the browser viewport (default on phones)
//   plus a true OS-fullscreen button (Fullscreen API).
//
// Coverage is bounded by which cores libretro builds for emscripten: MSX
// (bluemsx/fmsx), Watara (potator) and Pokémon Mini (pokemini) have NO wasm build
// anywhere, so they can't run in a browser — canPlay() returns false and the UI
// hides the ▶ button for them.
import React, { useEffect, useRef, useState } from "react";
import { X, Maximize2, Minimize2, Monitor, Copy, Check } from "lucide-react";
import { romFileUrl, extraDownloadUrl } from "./api.js";
import { useT } from "./i18n.jsx";

// system_key → libretro core. We SELF-HOST every core in /public/cores/ (see
// resolveCoreJs/Wasm in launch) so we never depend on an external CDN staying up.
// genesis_plus_gx is the one-stop Sega core: Game Gear, Master System, SG-1000
// and Genesis/Mega Drive all load through it.
const CORE_MAP = {
  nes: "fceumm",
  gb: "gambatte",
  gbc: "gambatte",
  gg: "genesis_plus_gx",
  sms: "genesis_plus_gx",
  sg: "genesis_plus_gx",
  md: "genesis_plus_gx",
  pce: "mednafen_pce_fast",
  col: "gearcoleco",
  gw: "gw",
  tama: "tamalibretro",
  pico8: "retro8",
  // Watara Supervision — potator core compiled from source for emscripten (MODULARIZE,
  // Nostalgist-compatible). No prebuilt existed anywhere; built via emsdk + RetroArch.
  wsv: "potator",
  // Neo Geo Pocket (mono+Color) and WonderSwan (mono+Color) via Mednafen cores,
  // self-hosted from arianrhodsandlot/retroarch-emscripten-build (Nostalgist format).
  ngp: "mednafen_ngp",
  ws: "mednafen_wswan",
  // Atari Lynx via the handy core, self-hosted from the same
  // arianrhodsandlot/retroarch-emscripten-build (Nostalgist format, v1.22.2 —
  // the version nostalgist@0.21 pins). .lnx files carry a header, so handy boots
  // them HLE: no lynxboot.img BIOS required.
  lynx: "handy",
  // NOTE: Atari 2600/7800, Amstrad CPC, MSX, Pokémon Mini have no Nostalgist-compatible
  // core, so they run via a self-hosted JS engine in an iframe instead (see JS_ENGINE —
  // Amstrad uses CPCEC, MSX uses WebMSX, Poké Mini uses the webRcade PokeMini core).
  // Watara (wsv→potator) had no prebuilt wasm anywhere, so its core was compiled from
  // source (emsdk + RetroArch) into the Nostalgist format above. Every system now plays.
};

// Every core listed above is mirrored under /public/cores/<core>_libretro.{js,wasm}.
const CORE_BASE = "/cores";

// Systems with NO libretro WASM core, but a standalone JS emulator we self-host
// and run in an isolated iframe. `pad` = how the on-screen pad reaches it:
// 'jt' → postMessage to Javatari's control socket; null → engine's own input only.
const JS_ENGINE = {
  a2600: { html: "javatari.html", pad: "jt" },   // Javatari (pure JS)
  a7800: { html: "js7800.html", pad: "js7800" },  // js7800 (ProSystem WASM)
  // Amstrad CPC via self-hosted CPCEC (CNGSoft, WASM). Inserts + autoruns the .dsk;
  // pad bridged to CPC keys as synthetic KeyboardEvents. See amstrad.html. (cap32 via
  // EmulatorJS was abandoned — it aborted on every disk mount.)
  amstrad: { html: "amstrad.html", pad: "ejs" },
  // MSX via self-hosted WebMSX (Paulo Peccin, WASM). Auto-detects cart/disk and boots
  // via a cold power-cycle; pad → MSX keys as synthetic KeyboardEvents. See msx.html.
  msx: { html: "msx.html", pad: "ejs" },
  // Pokémon Mini via self-hosted webRcade PokeMini core (RetroArch/WASM, FreeBIOS).
  // Pumps _emscripten_mainloop per frame; pad → _wrc_set_input. See pokemini.html.
  mini: { html: "pokemini.html", pad: "ejs" },
};
export function jsEngineFor(systemKey) { return JS_ENGINE[systemKey] || null; }

// Cores that exist but whose ROM format may differ from retro-go's packaging —
// best-effort, may fail to boot. The overlay warns before launching.
const EXPERIMENTAL = new Set(["gw", "pico8"]);

const MOBILE_QUERY = "(max-width: 640px)";

// Per-system DISPLAY aspect ratio (par-corrected) so the screen is drawn at its
// real shape, not the squarish raw framebuffer. Handhelds keep their native ratio;
// the rest are 4:3. Atari runs in an iframe and is intentionally left alone.
const SCREEN_ASPECT = {
  nes: "4 / 3", sms: "4 / 3", sg: "4 / 3", md: "4 / 3", pce: "4 / 3",
  col: "4 / 3", gw: "4 / 3", gg: "4 / 3",
  gb: "10 / 9", gbc: "10 / 9",
  pico8: "1 / 1", tama: "1 / 1", wsv: "1 / 1",
  amstrad: "4 / 3",
  msx: "4 / 3",
  mini: "4 / 3",
  // Handhelds at their native framebuffer ratio (else the 4/3 fallback stretches
  // them): Neo Geo Pocket 160×152, WonderSwan 224×144 (landscape default),
  // Atari Lynx 160×102 (square pixels).
  ngp: "20 / 19", ws: "14 / 9", lynx: "80 / 51",
};

// Square-pixel handhelds: PAR is 1:1, so the screen's true shape IS the live
// framebuffer ratio. We track it at runtime (WonderSwan rotates vertical games →
// 144×224) and draw object-fit:contain so it fills the LCD without stretching,
// capped to the stage (never blown up out of shape). SCREEN_ASPECT above is the
// pre-boot fallback.
const SQUARE_PIXEL = new Set(["ngp", "ws"]);

// Numeric display aspect (w/h) for a system — drives the popup's natural width so
// the window opens shaped to the game (4:3 wide, square handhelds narrower) instead
// of one fixed box. Clamped to a golden min/max in CSS so it never gets silly.
function aspectNumber(systemKey) {
  const [w, h] = (SCREEN_ASPECT[systemKey] || "4 / 3").split("/").map((x) => parseFloat(x));
  return w > 0 && h > 0 ? w / h : 4 / 3;
}

// Per-system keyboard cheatsheet. The keys are libretro's DEFAULT keyboard map
// (RetroPad → keyboard) that Nostalgist drives the core with; the labels are each
// system's real button names so it reads like retro-go's per-console control hint.
const DPAD = { keys: ["↑", "↓", "←", "→"], b: "D-pad" };
const AB = [{ k: "Z", b: "B" }, { k: "X", b: "A" }];
const KEY_HINTS = {
  nes:   [DPAD, ...AB, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "START" }],
  gb:    [DPAD, ...AB, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "START" }],
  gbc:   [DPAD, ...AB, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "START" }],
  gg:    [DPAD, { k: "Z", b: "1" }, { k: "X", b: "2" }, { k: "Enter", b: "START" }],
  sms:   [DPAD, { k: "Z", b: "1" }, { k: "X", b: "2" }, { k: "Enter", b: "PAUSE" }],
  sg:    [DPAD, { k: "Z", b: "1" }, { k: "X", b: "2" }],
  md:    [DPAD, { k: "A", b: "A" }, { k: "Z", b: "B" }, { k: "X", b: "C" }, { k: "Shift", b: "MODE" }, { k: "Enter", b: "START" }],
  pce:   [DPAD, { k: "Z", b: "II" }, { k: "X", b: "I" }, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "RUN" }],
  col:   [DPAD, { k: "Z", b: "Left fire" }, { k: "X", b: "Right fire" }, { k: "1~9 0 * #", b: "Keypad" }],
  gw:    [DPAD, { k: "X", b: "A" }, { k: "Z", b: "B" }, { k: "Enter", b: "START" }],
  tama:  [{ k: "Z", b: "A" }, { k: "X", b: "B" }, { k: "A", b: "C" }],
  pico8: [DPAD, { k: "Z", b: "O (○)" }, { k: "X", b: "X (✕)" }],
  wsv:   [DPAD, ...AB, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "START" }],
  // Atari Lynx: A/B + the two Option buttons (→ RetroPad L/R) and Pause (→ Start).
  lynx:  [DPAD, ...AB, { k: "Q", b: "OPTION 1" }, { k: "W", b: "OPTION 2" }, { k: "Enter", b: "PAUSE" }],
  amstrad: [DPAD, { k: "Space", b: "Fire" }, { k: "Shift", b: "Fire 2" }, { k: "Enter", b: "RETURN" }],
  msx:    [DPAD, { k: "Space", b: "Fire (Space)" }, { k: "Ctrl", b: "Fire 2" }, { k: "Enter", b: "RETURN" }],
  mini:   [DPAD, { k: "X", b: "A" }, { k: "Z", b: "B" }, { k: "C", b: "C" }, { k: "Enter", b: "START" }],
};
const DEFAULT_HINTS = [DPAD, ...AB, { k: "Shift", b: "SELECT" }, { k: "Enter", b: "START" }];

// Cores that need a BIOS in the RetroArch system dir to boot. `path` is where
// the file lives in the Extra folder (named for the SD firmware); `fileName` is
// what the libretro CORE looks for — they differ! gearcoleco wants
// "colecovision.rom", not the SD's "coleco.bin" (same bytes).
const BIOS = {
  col: [{ fileName: "colecovision.rom", path: "bios/coleco/coleco.bin" }],
};
const FDS_BIOS = { fileName: "disksys.rom", path: "bios/nes/disksys.rom" };

// Fetch the BIOS file(s) this ROM needs from the Extra folder. Missing BIOS is
// non-fatal — we just launch without it (the core reports its own error).
async function loadBios(rom) {
  const needed = [...(BIOS[rom.system_key] || [])];
  if (rom.system_key === "nes" && /\.fds$/i.test(rom.stored_name)) needed.push(FDS_BIOS);
  const out = [];
  for (const b of needed) {
    try {
      const r = await fetch(extraDownloadUrl(b.path));
      if (r.ok) out.push({ fileName: b.fileName, fileContent: await r.blob() });
    } catch (_) { /* BIOS absent → launch anyway */ }
  }
  return out;
}

export function coreFor(systemKey) {
  return CORE_MAP[systemKey] || null;
}
export function canPlay(systemKey) {
  return Boolean(CORE_MAP[systemKey] || JS_ENGINE[systemKey]);
}
export function isExperimental(systemKey) {
  return EXPERIMENTAL.has(systemKey);
}

// Emulator window. Windowed popup by default on PC (list stays behind), or full
// viewport on phones. Closes on X / Escape only — never on backdrop click, so a
// misclick can't kill a running game.
export function EmulatorOverlay({ rom, onClose }) {
  const t = useT();
  const canvasRef = useRef(null);
  const windowRef = useRef(null);
  const nostRef = useRef(null);
  const iframeRef = useRef(null);
  const [status, setStatus] = useState("loading"); // loading | running | error
  const [err, setErr] = useState("");
  const [mode, setMode] = useState(
    () => (window.matchMedia(MOBILE_QUERY).matches ? "max" : "window")
  );
  // Drag-to-move (window mode only) — offset from the centered rest position.
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const dragRef = useRef(null);

  // Switching out of window mode snaps back to centered.
  useEffect(() => { if (mode !== "window") setPos({ x: 0, y: 0 }); }, [mode]);

  function onBarPointerDown(e) {
    // Drag the popup only with a MOUSE in window mode — touch uses max mode and
    // dragging there just hijacks taps (and a missed pointerup left it stuck).
    if (mode !== "window" || e.target.closest(".emu-bar-right")) return;
    if (e.pointerType && e.pointerType !== "mouse") return;
    e.preventDefault();
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y };
    const onMove = (ev) => {
      const d = dragRef.current;
      if (d) setPos({ x: d.ox + ev.clientX - d.sx, y: d.oy + ev.clientY - d.sy });
    };
    const end = () => {
      dragRef.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);   // touch/interrupt → don't get stuck
  }

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lock page scroll/drag while the emulator is open — on mobile the page would
  // otherwise drag/overscroll under the game and pad while you play.
  useEffect(() => {
    const body = document.body;
    const prev = { o: body.style.overflow, t: body.style.touchAction, b: body.style.overscrollBehavior };
    body.style.overflow = "hidden";
    body.style.touchAction = "none";
    body.style.overscrollBehavior = "none";
    return () => {
      body.style.overflow = prev.o;
      body.style.touchAction = prev.t;
      body.style.overscrollBehavior = prev.b;
    };
  }, []);

  useEffect(() => {
    // JS-engine systems (a2600 → Javatari) run inside a self-hosted iframe below,
    // not via Nostalgist — nothing to launch here, the iframe handles loading.
    if (jsEngineFor(rom.system_key)) { setStatus("running"); return undefined; }
    let cancelled = false;
    (async () => {
      try {
        const core = coreFor(rom.system_key);
        if (!core) throw new Error(t("This platform can't run in the browser."));

        const res = await fetch(romFileUrl(rom.id));
        if (!res.ok) throw new Error(t("Failed to load the ROM file."));
        const fileContent = await res.blob();
        const bios = await loadBios(rom);
        if (cancelled) return;

        const { Nostalgist } = await import("nostalgist");
        const nost = await Nostalgist.launch({
          core,
          // Load every core from OUR server (/public/cores), not an external CDN —
          // if jsdelivr/libretro goes down, the emulator still works.
          resolveCoreJs: (c) => `${CORE_BASE}/${c}_libretro.js`,
          resolveCoreWasm: (c) => `${CORE_BASE}/${c}_libretro.wasm`,
          rom: { fileName: rom.stored_name, fileContent },
          ...(bios.length ? { bios } : {}),
          element: canvasRef.current,
          respondToGlobalEvents: true,
        });
        if (cancelled) { try { nost.exit(); } catch (_) {} return; }
        nostRef.current = nost;
        setStatus("running");
      } catch (e) {
        if (!cancelled) { setErr(e?.message || String(e)); setStatus("error"); }
      }
    })();
    return () => {
      cancelled = true;
      try { nostRef.current?.exit?.(); } catch (_) {}
      nostRef.current = null;
    };
  }, [rom.id, rom.system_key, rom.stored_name]);

  function goFullscreen() {
    const el = windowRef.current;
    if (!el) return;
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (fsEl) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      try { exit?.call(document); } catch (_) {}
      return;
    }
    // standard + webkit (Safari/iOS); ignore the promise rejection some browsers throw
    const req = el.requestFullscreen || el.webkitRequestFullscreen || el.webkitRequestFullScreen;
    if (req) {
      try { const p = req.call(el); if (p && p.catch) p.catch(() => {}); } catch (_) {}
    }
  }

  // Virtual gamepad → drive the core via Nostalgist's keyboard bridge.
  // a2600 runs in the Javatari iframe → drive it via postMessage (the iframe
  // forwards to Javatari's console-controls socket). Other systems → Nostalgist.
  const sendPad = (btn, down) => {
    const js = jsEngineFor(rom.system_key);
    if (js?.pad === "jt") {
      try { iframeRef.current?.contentWindow?.postMessage({ type: "jt-input", btn, down }, "*"); } catch (_) {}
    } else if (js?.pad === "js7800") {
      try { iframeRef.current?.contentWindow?.postMessage({ type: "js7800-input", btn, down }, "*"); } catch (_) {}
    } else if (js?.pad === "ejs") {
      try { iframeRef.current?.contentWindow?.postMessage({ type: "ejs-input", btn, down }, "*"); } catch (_) {}
    } else if (!js) {
      try { down ? nostRef.current?.pressDown(btn) : nostRef.current?.pressUp(btn); } catch (_) {}
    }
  };
  const hold = (btn) => sendPad(btn, true);
  const release = (btn) => sendPad(btn, false);

  const title = rom.korean_name || rom.stored_name;

  // Copy the on-device filename to the clipboard — handy for matching the cart on
  // the SD card. Icon flips to a check for a moment so the click feels confirmed.
  const [copied, setCopied] = useState(false);
  async function copyName() {
    try {
      await navigator.clipboard.writeText(rom.stored_name || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (_) {}
  }

  return (
    <div className={`emu-overlay mode-${mode}`} role="dialog" aria-modal="true" aria-label={t("Run {title}", { title })}>
      <div className="emu-window" ref={windowRef}
        style={mode === "window"
          ? { transform: `translate(${pos.x}px, ${pos.y}px)`, "--emu-asp": aspectNumber(rom.system_key) }
          : { "--emu-asp": aspectNumber(rom.system_key) }}>
        <div className={`emu-bar ${mode === "window" ? "draggable" : ""}`} onPointerDown={onBarPointerDown}>
          <span className="emu-led" aria-hidden />
          <span className="emu-title">{title}</span>
          <span className="emu-bar-right">
            <button className="icon-btn" onClick={copyName}
              title={copied ? t("Filename copied") : t("Copy filename")}>
              {copied ? <Check size={15} strokeWidth={2.5} /> : <Copy size={15} strokeWidth={2.5} />}
            </button>
            {mode === "window" ? (
              <button className="icon-btn" onClick={() => setMode("max")} title={t("Fill browser")}>
                <Maximize2 size={15} strokeWidth={2.5} />
              </button>
            ) : (
              <button className="icon-btn" onClick={() => setMode("window")} title={t("Window mode")}>
                <Minimize2 size={15} strokeWidth={2.5} />
              </button>
            )}
            <button className="icon-btn" onClick={goFullscreen} title={t("Fullscreen")}>
              <Monitor size={15} strokeWidth={2.5} />
            </button>
            <button className="icon-btn" onClick={onClose} title={t("Close (ESC)")}>
              <X size={17} strokeWidth={2.5} />
            </button>
          </span>
        </div>

        <div className="emu-stage">
          {jsEngineFor(rom.system_key) ? (
            <iframe
              ref={iframeRef}
              className="emu-canvas"
              title={t("Run {title}", { title })}
              src={`/${jsEngineFor(rom.system_key).html}?rom=${encodeURIComponent(rom.id)}&ext=${encodeURIComponent((rom.stored_name || "").split(".").pop().toLowerCase())}`}
              allow="autoplay; fullscreen; gamepad"
              onLoad={() => { try { iframeRef.current?.contentWindow?.focus(); } catch (_) {} }}
              style={{ border: 0, width: "100%", height: "100%", background: "#000" }}
            />
          ) : (
            <canvas ref={canvasRef} className="emu-canvas"
              style={
                SQUARE_PIXEL.has(rom.system_key)
                  ? { aspectRatio: SCREEN_ASPECT[rom.system_key], objectFit: "contain" }
                  : { aspectRatio: SCREEN_ASPECT[rom.system_key] || "4 / 3" }
              } />
          )}
          {status === "loading" && (
            <div className="emu-status">
              <div className="emu-spinner" aria-hidden />
              {t("Loading core…")}
              {isExperimental(rom.system_key) && (
                <div className="emu-note">{t("This platform has experimental support and may not run correctly.")}</div>
              )}
            </div>
          )}
          {status === "error" && (
            <div className="emu-status emu-error">
              <div>{t("Can't run.")}</div>
              <div className="emu-note">{err}</div>
            </div>
          )}
        </div>

        {status === "running" && <VirtualPad onDown={hold} onUp={release} />}

        {/* Control legend — detached panel pinned just below the device shell.
            Hidden for JS-engine (Javatari) systems: their keyboard map differs and
            the on-screen pad is the control, so the libretro key hints would mislead. */}
        {status === "running" && !jsEngineFor(rom.system_key) && (
          <div className="emu-keys" aria-label={t("Keyboard controls")}>
            {(KEY_HINTS[rom.system_key] || DEFAULT_HINTS).map((h, i) => (
              <span className="emu-key-grp" key={i}>
                {(h.keys || [h.k]).map((kk, j) => <kbd key={j}>{kk}</kbd>)}
                <em>{t(h.b)}</em>
              </span>
            ))}
            <span className="emu-key-grp"><kbd>Esc</kbd><em>{t("Close")}</em></span>
          </div>
        )}
      </div>
    </div>
  );
}

// One pad button. Pointer events (touch + mouse) hold the key while pressed and
// release on lift/cancel; pointer capture keeps the press alive if the finger
// slides off the button. Visual "on" state is toggled directly to avoid renders.
function PadButton({ btn, className, label, glyph, onDown, onUp }) {
  const down = (e) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.currentTarget.classList.add("on");
    onDown(btn);
  };
  const up = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove("on");
    onUp(btn);
  };
  return (
    <button
      type="button"
      className={`pad-btn ${className || ""}`}
      aria-label={label}
      onContextMenu={(e) => e.preventDefault()}
      onPointerDown={down}
      onPointerUp={up}
      onPointerCancel={up}
    >
      {glyph ?? label}
    </button>
  );
}

// Game & Watch control deck, mirroring the real Zelda/Mario layout: D-pad on the
// left, and a right cluster with the grouped SELECT/START frame stacked ABOVE the
// red A/B buttons.
function VirtualPad({ onDown, onUp }) {
  const t = useT();
  const p = { onDown, onUp };
  return (
    <div className="emu-pad">
      <div className="pad-dpad">
        {/* trailing U+FE0E forces text (not colour-emoji) presentation — ◀ ▶ render
            as emoji on many platforms otherwise */}
        <PadButton btn="up" glyph="▲︎" label={t("Up")} className="dp dp-up" {...p} />
        <PadButton btn="left" glyph="◀︎" label={t("Left")} className="dp dp-left" {...p} />
        <span className="dp-hub" aria-hidden />
        <PadButton btn="right" glyph="▶︎" label={t("Right")} className="dp dp-right" {...p} />
        <PadButton btn="down" glyph="▼︎" label={t("Down")} className="dp dp-down" {...p} />
      </div>
      <div className="pad-right">
        <div className="pad-ss">
          <div className="pad-ss-labels"><em>SELECT</em><em>START</em></div>
          <div className="pad-mid">
            <PadButton btn="select" label="SELECT" glyph="" className="pad-pill" {...p} />
            <PadButton btn="start" label="START" glyph="" className="pad-pill" {...p} />
          </div>
        </div>
        <div className="pad-face">
          <span className="pad-cap cap-bottom">
            <PadButton btn="b" label="B" glyph="" className="pad-round b" {...p} />
            <em>B</em>
          </span>
          <span className="pad-cap cap-bottom">
            <PadButton btn="a" label="A" glyph="" className="pad-round a" {...p} />
            <em>A</em>
          </span>
        </div>
      </div>
    </div>
  );
}

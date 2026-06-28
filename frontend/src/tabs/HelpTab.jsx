import React from "react";
import { Gamepad2, Keyboard, Power, Info, ListOrdered, HardDrive, Rocket } from "lucide-react";
import { useT } from "../i18n.jsx";

// Steps to prepare the SD with this tool
const STEPS = [
  "In the UPLOAD tab (or an empty library), pick a platform and drag in your ROMs.",
  "Korean (English) names and covers are added automatically. Videos are converted to .avi in the VIDEO tab and placed in /media.",
  "If needed, rename, search/upload covers, and adjust the crop position from the card details.",
  "Download via 'SD ZIP' at the top right (or 'Current Platform ZIP' in the library). The estimated size is shown on the label.",
  "Just extract the downloaded ZIP to the root of your SD card and you're done — the /roms, /covers, /cores structure is already set up.",
];

// SD card / folder structure
const SDCARD = [
  ["Format", "exFAT recommended (or FAT32)"],
  ["/roms/<platform>/", "ROM files per platform (uncompressed)"],
  ["/covers/<platform>/", "Cover .img (186×100, filename matches the ROM) — auto-generated"],
  ["/cores/", "PICO-8 cores (pico8.bin, etc.) — automatically included in the SD ZIP"],
  ["/media/", "Entertainment videos .avi (excluded from the SD ZIP by default, included with ?video)"],
];

// Device button shortcuts (source: github.com/sylverb/game-and-watch-retro-go-sd)
const SECTIONS = [
  {
    icon: Gamepad2,
    title: "Basic Buttons",
    rows: [
      ["GAME", "Start"],
      ["TIME", "Select"],
      ["PAUSE/SET", "Open the emulator menu"],
    ],
  },
  {
    icon: Keyboard,
    title: "In-Game Shortcuts  ·  while holding PAUSE/SET",
    rows: [
      ["PAUSE/SET + GAME", "Capture screenshot"],
      ["PAUSE/SET + TIME", "Toggle speed (1x / 1.5x)"],
      ["PAUSE/SET + ▲", "Increase brightness"],
      ["PAUSE/SET + ▼", "Decrease brightness"],
      ["PAUSE/SET + ▶", "Increase volume"],
      ["PAUSE/SET + ◀", "Decrease volume"],
      ["PAUSE/SET + A", "Save state"],
      ["PAUSE/SET + B", "Load state"],
      ["PAUSE/SET + POWER", "Power off (does not save state)"],
    ],
  },
  {
    icon: Power,
    title: "On Boot (hold while powering on)",
    rows: [
      ["PAUSE/SET", "Bootloader diagnostics menu"],
      ["TIME", "Force boot to the game list (bypass a problematic save)"],
    ],
  },
];

// GitHub mark (Octocat) — lucide-react dropped brand icons, so inline the mark.
function GithubMark({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.65 7.65 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function Combo({ combo }) {
  const keys = combo.split("+").map((k) => k.trim());
  return (
    <span className="help-combo">
      {keys.map((k, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span className="help-plus">+</span>}
          <kbd className="keycap">{k}</kbd>
        </React.Fragment>
      ))}
    </span>
  );
}

export default function HelpTab() {
  const t = useT();
  return (
    <div className="stack help-tab">
      <div className="muted">
        <Info size={13} aria-hidden /> {t("Upload ROMs & videos — Korean names and covers are added automatically and packed into a ZIP in the retro-go SD card layout.")}
      </div>

      {/* 사용법 */}
      <div className="help-section">
        <div className="help-head"><ListOrdered size={14} strokeWidth={2.5} aria-hidden /> {t("Basic Usage")}</div>
        <ol className="help-steps">
          {STEPS.map((s, i) => <li key={i}>{t(s)}</li>)}
        </ol>
      </div>

      {/* SD 카드 구조 */}
      <div className="help-section">
        <div className="help-head"><HardDrive size={14} strokeWidth={2.5} aria-hidden /> {t("SD Card / Folder Structure")}</div>
        <div className="help-list">
          {SDCARD.map(([k, v]) => (
            <div className="help-row" key={k}>
              <span className="help-combo"><kbd className="keycap">{t(k)}</kbd></span>
              <span className="help-action">{t(v)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 단축키 */}
      {SECTIONS.map((s) => (
        <div className="help-section" key={s.title}>
          <div className="help-head"><s.icon size={14} strokeWidth={2.5} aria-hidden /> {t(s.title)}</div>
          <div className="help-list">
            {s.rows.map(([combo, action]) => (
              <div className="help-row" key={combo + action}>
                <Combo combo={combo} />
                <span className="help-action">{t(action)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="muted help-note">
        {t("MSX and Amstrad support virtual keyboard input from the PAUSE/SET menu, and Zelda 3 / Super Mario World have different button mappings depending on the Mario/Zelda device version. · Source:")}
      </div>
      <div className="help-projects">
        {/* Upstream firmware project (sylverb) */}
        <a className="help-project" href="https://github.com/sylverb/game-and-watch-retro-go-sd" target="_blank" rel="noreferrer">
          <GithubMark size={18} />
          <span className="help-project-name">game-and-watch-retro-go-sd</span>
        </a>
        {/* My experimental firmware fork — release/download page */}
        <a className="help-project help-project-alt" href="https://github.com/jshsakura/game-and-watch-retro-go-sd/releases" target="_blank" rel="noreferrer">
          <Rocket size={16} strokeWidth={2.5} aria-hidden />
          <span className="help-project-name">{t("Releases (experimental)")}</span>
        </a>
      </div>
    </div>
  );
}

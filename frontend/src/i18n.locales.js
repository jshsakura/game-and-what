// Single source of truth for UI languages. The set mirrors the retro-go-sd
// firmware locales (sd_content/lang/*.bin) so the web manager and the device
// menu speak the same languages. English is the SOURCE language: in-code strings
// are English and used directly as lookup keys, so `en` carries no dictionary.
// Korean and all remaining locales lazily load their dictionaries on first use.
//
// `flag` is the basename under /public/flags/<flag>.png. Some flags are not yet
// bundled (tw, pt, ru, no) — the switcher falls back to a text code badge, so a
// missing asset never breaks rendering.
export const LOCALES = [
  { code: "ko", label: "한국어", flag: "kr" }, // source language (no dictionary)
  { code: "en", label: "English", flag: "us" },
  { code: "ja", label: "日本語", flag: "jp" },
  { code: "zh-CN", label: "简体中文", flag: "cn" },
  { code: "zh-TW", label: "繁體中文", flag: "tw" },
  { code: "de", label: "Deutsch", flag: "de" },
  { code: "es", label: "Español", flag: "es" },
  { code: "fr", label: "Français", flag: "fr" },
  { code: "it", label: "Italiano", flag: "it" },
  { code: "pt", label: "Português", flag: "pt" },
  { code: "ru", label: "Русский", flag: "ru" },
  { code: "no", label: "Norsk", flag: "no" },
];

export const DEFAULT_LOCALE = "en";
export const SOURCE_LOCALE = "en";

const CODES = LOCALES.map((l) => l.code);

export function isLocale(code) {
  return CODES.includes(code);
}

// Resolve the browser's preferred language to a supported locale. Tries an exact
// match (e.g. "zh-CN"), then a language-prefix match (e.g. "zh" → "zh-CN", "pt-BR"
// → "pt"), then falls back to English.
export function resolveBrowserLocale(navLang) {
  const raw = (navLang || "").trim();
  if (!raw) return DEFAULT_LOCALE;
  const lower = raw.toLowerCase();

  const exact = CODES.find((c) => c.toLowerCase() === lower);
  if (exact) return exact;

  const prefix = lower.split("-")[0];
  const byPrefix = CODES.find((c) => c.toLowerCase().split("-")[0] === prefix);
  return byPrefix || DEFAULT_LOCALE;
}

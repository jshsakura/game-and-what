import React, { createContext, useContext, useEffect, useState } from "react";
import EN from "./locales/en.js";
import {
  SOURCE_LOCALE,
  DEFAULT_LOCALE,
  isLocale,
  resolveBrowserLocale,
} from "./i18n.locales.js";

// UI language. English is the SOURCE language: in-code strings are English and used
// directly as the lookup key. A missing key falls back to the English key itself.
// Korean and all other locales lazily import their translation dicts on first use.
const LANG_KEY = "gnw_lang";

// Loaded dictionaries by locale. English is the source: by default a key resolves
// to itself, but en.js may carry a few disambiguation overrides (e.g. two distinct
// keys that should render the same English word). Other locales populate on first use.
const dictCache = { [SOURCE_LOCALE]: EN };

function loadDict(code) {
  if (dictCache[code] !== undefined) return Promise.resolve(dictCache[code]);
  // Vite bundles each ./locales/*.js as its own chunk for this dynamic import.
  return import(`./locales/${code}.js`)
    .then((m) => (dictCache[code] = m.default || {}))
    .catch(() => (dictCache[code] = {})); // missing/broken dict → full English fallback
}

// CJK / Cyrillic web font lazy loader. Only runs for locales that need extra
// glyphs not covered by the bundled Noto Sans KR. Each import() becomes its own
// Vite asset chunk so the initial bundle stays small on mobile.
const fontLoaded = new Set();
function loadFont(code) {
  if (fontLoaded.has(code)) return;
  fontLoaded.add(code);
  const imports = {
    ja:    () => import("@fontsource/noto-sans-jp/japanese-400.css"),
    "zh-CN": () => import("@fontsource/noto-sans-sc/chinese-simplified-400.css"),
    "zh-TW": () => import("@fontsource/noto-sans-tc/chinese-traditional-400.css"),
    ru:    () => import("@fontsource/noto-sans/cyrillic-400.css"),
  };
  if (imports[code]) imports[code]().catch(() => {}); // font failure must not break the app
}

function initialLang() {
  const saved = localStorage.getItem(LANG_KEY);
  if (saved && isLocale(saved)) return saved;
  return resolveBrowserLocale(navigator.language || navigator.userLanguage);
}

const I18nContext = createContext({
  lang: DEFAULT_LOCALE,
  setLang: () => {},
  t: (s) => s,
});

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(initialLang);
  // Active locale's dictionary; English has no dict (it IS the source).
  const [dict, setDict] = useState(() => dictCache[lang] || null);

  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang);
    document.documentElement.setAttribute("lang", lang);
    loadFont(lang); // lazy-load CJK/Cyrillic web font for this locale (no-op for others)
    let cancelled = false;
    loadDict(lang).then((d) => {
      if (!cancelled) setDict(d);
    });
    return () => {
      cancelled = true;
    };
  }, [lang]);

  const setLang = (code) => {
    if (isLocale(code)) setLangState(code);
  };

  // t(en[, vars]): the English source string is the key. Resolution order for a
  // non-English locale: that locale's translation → English source (key itself).
  // Supports {name}-style placeholders: t("Total {n} items", {n: 5}).
  const t = (en, vars) => {
    let s = (dict && dict[en]) || en; // locale translation (or en.js override) → English key
    if (vars) for (const k in vars) s = s.replaceAll(`{${k}}`, vars[k]);
    return s;
  };

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

// Convenience hook: const t = useT();  →  t("string")
export function useT() {
  return useContext(I18nContext).t;
}

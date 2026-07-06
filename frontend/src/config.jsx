import React, { createContext, useContext, useEffect, useState } from "react";
import { getConfig } from "./api.js";

// Runtime feature flags from GET /api/config. korean_mode gates the
// Korea-specific UI (한글패치 toggle, Korean-name resolve/gamelist, 한글명 누락
// 필터). Defaults to false until loaded so non-Korean is the safe default.
// libretro is keyless → always available; the keyed providers default off until
// /api/config confirms a key is configured (so their buttons start disabled).
const DEFAULT_COVER_SOURCES = { libretro: true, igdb: false, tgdb: false, sgdb: false };
const ConfigContext = createContext({ korean_mode: false, experimental_mode: false, cover_sources: DEFAULT_COVER_SOURCES });

export function ConfigProvider({ children }) {
  const [config, setConfig] = useState({ korean_mode: false, experimental_mode: false, cover_sources: DEFAULT_COVER_SOURCES });
  useEffect(() => {
    let alive = true;
    getConfig().then((c) => { if (alive) setConfig(c); });
    return () => { alive = false; };
  }, []);
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}

// Convenience: the Korea-specific feature flag.
export function useKoreanMode() {
  return !!useContext(ConfigContext).korean_mode;
}

// "Personal lab" flag: fork-firmware extras (experimental systems, MEDIA tab,
// the experimental-releases link). Off → upstream-official feature set only.
export function useExperimentalMode() {
  return !!useContext(ConfigContext).experimental_mode;
}

// Which cover-search providers are configured (have an API key). libretro is
// keyless so it's always true; the rest depend on server env.
export function useCoverSources() {
  return useContext(ConfigContext).cover_sources || DEFAULT_COVER_SOURCES;
}

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Library, Inbox, ChevronLeft, ChevronRight, ImageOff, Languages, Search, Upload, Check, HardDriveDownload, StarOff } from "lucide-react";
import { getLibrary, getSystems, coverUrl, uploadRoms, uploadCdFolder, FOLDER_SYSTEMS } from "../api.js";
import { RomCard, SystemIcon, systemColor, Dropzone, Pico8CompatFilter, SortSelect } from "../components.jsx";
import { useToast } from "../toast.jsx";
import { useKoreanMode } from "../config.jsx";
import { useI18n } from "../i18n.jsx";

// Desktop: 30 fills whole rows (5/6-wide grid). Mobile: 21 (3-wide grid) so the
// page isn't a giant scroll.
const PAGE_SIZE_DESKTOP = 20;
const PAGE_SIZE_MOBILE = 20;
const MOBILE_QUERY = "(max-width: 640px)";

// Sort roms by display name (Korean title if present, else filename), Korean-aware.
const byName = (a, b) =>
  (a.korean_name || a.stored_name || "").localeCompare(
    b.korean_name || b.stored_name || "", "ko", { numeric: true }
  );

// Favorites (★) bubble to the front; ties broken by display name.
// Favorites are always pinned to the top; the chosen sort orders the rest.
const favFirst = (a, b) => (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0);
const byDateDesc = (a, b) => (b.created_at || "").localeCompare(a.created_at || "");
const byDateAsc = (a, b) => (a.created_at || "").localeCompare(b.created_at || "");
// IGDB score: 0-100 = rating, -1 = checked/none, NULL = not fetched. Only a real
// >0 score counts as "rated"; unrated roms ALWAYS sink to the bottom in BOTH
// directions (use the 무평점 filter to isolate them), so the rating sorts only
// reorder games that actually carry a score.
const hasScore = (r) => typeof r.igdb_score === "number" && r.igdb_score > 0;
const byScore = (a, b, dir) => {
  const sa = hasScore(a), sb = hasScore(b);
  if (sa !== sb) return sa ? -1 : 1;   // rated always before unrated, both directions
  if (!sa) return 0;                   // both unrated → let name break the tie
  return dir * (a.igdb_score - b.igdb_score);
};
const byScoreDesc = (a, b) => byScore(a, b, -1);
const byScoreAsc = (a, b) => byScore(a, b, 1);
// Available sort modes (the segmented control in the toolbar). Default = recent
// so a freshly-uploaded batch floats to the top, easy to find and organize.
const SORTS = {
  recent: (a, b) => favFirst(a, b) || byDateDesc(a, b) || byName(a, b),
  name:   (a, b) => favFirst(a, b) || byName(a, b),
  oldest: (a, b) => favFirst(a, b) || byDateAsc(a, b) || byName(a, b),
  rating: (a, b) => favFirst(a, b) || byScoreDesc(a, b) || byName(a, b),
  rating_asc: (a, b) => favFirst(a, b) || byScoreAsc(a, b) || byName(a, b),
};
const SORT_ORDER = ["recent", "name", "oldest", "rating", "rating_asc"];
const SORT_LABELS = { recent: "Newest", name: "Name", oldest: "Oldest", rating: "Rating", rating_asc: "Rating (low)" };

// Does this ROM actually ship to the SD card? Mirrors backend _excluded_roms():
// a ROM is dropped when the user opted it out (sd_exclude) OR it's a PICO-8 cart
// that doesn't run on the real G&W (구동불가/broken). Excluded ROMs stay visible
// in the library but are left out of per-system counts and the SD download.
const shipsToSd = (rom) => !rom.sd_exclude && rom.pico8_compat !== "broken";

const HANGUL_RE = /[가-힣]/;
// Homebrew / Pico-8 are indie carts with no Korean release → never "missing".
// Atari Lynx is a US/EU handheld with no Korean releases either; PC Engine CD is
// a JP/US format with no official Korean releases.
const NO_KOREAN_SYSTEMS = new Set(["homebrew", "pico8", "lynx", "pcecd"]);
// "Needs a Korean title" = no Hangul AND has a real translatable word: a run of
// 2+ consecutive letters containing a lowercase one. This excludes titles that
// are only digits/symbols ("1942"), all-caps acronyms ("NBA", "WWF"), and dotted
// initialisms ("Z.O.E" → just z/o/e single letters) — none of which get a Korean
// name. "Antarctic Adventure", "R-Type", "Bonk's" all still count.
const needsKorean = (rom) => {
  if (NO_KOREAN_SYSTEMS.has(rom.system_key)) return false;
  const stem = (rom.stored_name || "").replace(/\.[^.]+$/, "");
  if (HANGUL_RE.test(stem)) return false;
  const words = stem.match(/[A-Za-z]+/g) || [];
  return words.some((w) => w.length >= 2 && /[a-z]/.test(w));
};

function usePageSize() {
  const [size, setSize] = useState(
    () => (window.matchMedia(MOBILE_QUERY).matches ? PAGE_SIZE_MOBILE : PAGE_SIZE_DESKTOP)
  );
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = (e) => setSize(e.matches ? PAGE_SIZE_MOBILE : PAGE_SIZE_DESKTOP);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return size;
}

export default function LibraryTab({ reloadKey, onChanged, selected, onToggleSel }) {
  const toast = useToast();
  const { t, lang } = useI18n();
  const koreanMode = useKoreanMode();
  // 한글명-누락 filter/badge: Korean deploy AND Korean UI only (hidden in English).
  const koFeature = koreanMode && lang === "ko";
  const [lib, setLib] = useState({ roms: [], videos: [], music: [] });
  // Seed from the last-known systems (cached) so the loading skeleton renders the
  // RIGHT number of platform chips on first paint — otherwise it starts at the
  // fallback count and visibly jumps when /api/systems resolves mid-skeleton.
  const [systems, setSystems] = useState(() => {
    try { return JSON.parse(localStorage.getItem("gnw_systems") || "[]"); } catch { return []; }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null); // selected system key (or MEDIA_KEY)
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [searchAll, setSearchAll] = useState(false); // search scope: this system vs all
  const [missingOnly, setMissingOnly] = useState(false); // show only cover-missing roms
  const [nonKoOnly, setNonKoOnly] = useState(false); // show only NON-Korean-named roms
  const [unratedOnly, setUnratedOnly] = useState(false); // show only roms with no IGDB score (obscure)
  const [sortMode, setSortMode] = useState("recent"); // recent | name | oldest
  const sortCmp = SORTS[sortMode] || SORTS.recent;
  const [compatFilter, setCompatFilter] = useState("all"); // PICO-8 호환 상태 필터
  const pageSize = usePageSize();

  const [busy, setBusy] = useState(false);
  // Download selection is owned by App (전체 선택 + 다운로드 live in the top bar);
  // here we just render each chip's checkbox from the `selected` prop.

  const reload = useCallback(() => {
    setLoading(true);
    getLibrary()
      .then(setLib)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Re-fetch WITHOUT the loading skeleton — for post-edit refreshes (toggle
  // broken/exclude/favorite, rename…) so the chip counts update in place
  // instead of flashing the whole library back to skeletons.
  const reloadSilent = useCallback(() => {
    getLibrary().then(setLib).catch(() => {});
  }, []);

  useEffect(() => { reload(); }, [reload, reloadKey]);
  useEffect(() => {
    getSystems().then((s) => {
      setSystems(s);
      try { localStorage.setItem("gnw_systems", JSON.stringify(s)); } catch { /* ignore */ }
    }).catch(() => {});
  }, []);

  // While any cover is still being fetched (status 'pending'), poll so spinners
  // turn into covers live without a manual refresh. Stops once none are pending.
  const anyPending = useMemo(() => lib.roms.some((r) => r.cover_status === "pending"), [lib.roms]);
  useEffect(() => {
    if (!anyPending) return undefined;
    const t = setInterval(() => { getLibrary().then(setLib).catch(() => {}); }, 4000);
    return () => clearInterval(t);
  }, [anyPending]);

  const refresh = () => { reloadSilent(); onChanged?.(); };

  async function uploadHere(files, onProgress) {
    if (busy || !current) return;
    setBusy(true); setError("");
    try {
      // CD systems (PC Engine CD) are folder-per-game — use the same uploader the
      // Upload tab does, so dropping a game folder works identically here.
      const res = FOLDER_SYSTEMS.has(current)
        ? await uploadCdFolder(current, files, onProgress)
        : await uploadRoms(current, files, onProgress);
      const dups = (res.results || []).filter((r) => r.error === "duplicate");
      if (dups.length) {
        toast.warn(`${t("Skipped {n} duplicate ROM(s) already in the library", { n: dups.length })}: ${dups.map((d) => d.name).join(", ")}`);
      }
      toast.success(t("Upload complete"));
      refresh();
    } catch (e) { setError(e.message); toast.error(e.message); }
    finally { setBusy(false); }
  }

  // Group ROMs by system, in firmware order; the chips show per-system counts.
  const bySystem = useMemo(() => lib.roms.reduce((acc, r) => {
    (acc[r.system_key] ??= []).push(r);
    return acc;
  }, {}), [lib.roms]);

  // Exact-content duplicates: roms sharing one SHA-256 across the WHOLE library
  // (a game and its "부제 있고 없고" twin often turn out to be the same bytes).
  // Each rom maps to the OTHER roms with its hash → shown as a badge + in detail.
  const dupesById = useMemo(() => {
    const byHash = new Map();
    for (const r of lib.roms) {
      if (!r.content_hash) continue;
      (byHash.get(r.content_hash) ?? byHash.set(r.content_hash, []).get(r.content_hash)).push(r);
    }
    const out = {};
    for (const group of byHash.values()) {
      if (group.length < 2) continue;
      for (const r of group) {
        out[r.id] = group
          .filter((o) => o.id !== r.id)
          .map((o) => ({ id: o.id, name: o.display_name || o.stored_name }));
      }
    }
    return out;
  }, [lib.roms]);

  // Total rom files across the checked systems — shown in the selection badge
  // ("N플랫폼 · M파일 선택됨"). selected holds system keys; sum their rom counts.
  // Count only ROMs that actually ship — excluded ones (manual opt-out or PICO-8
  // 구동불가) stay in the library but won't be in the SD ZIP, so they shouldn't
  // inflate the selection.
  const selectedFileCount = useMemo(
    () => [...selected].reduce((n, k) => n + (bySystem[k]?.filter(shipsToSd).length || 0), 0),
    [selected, bySystem]
  );

  // ALL supported systems show as chips (don't omit any) — empty ones are dimmed
  // with a 0 count so the full supported lineup is always visible. Chips are
  // ordered by system name; each system's roms by display name (Korean-aware).
  const groups = useMemo(() => systems
    .map((s) => ({ key: s.key, system: s, roms: [...(bySystem[s.key] ?? [])].sort(sortCmp) }))
    .sort((a, b) => a.system.name.localeCompare(b.system.name, "en")), [systems, bySystem, sortCmp]);
  const nonEmpty = useMemo(() => groups.filter((g) => g.roms.length), [groups]);

  // Media (videos + music) is managed in the MEDIA tab, not here — LIBRARY is roms only.
  const empty = lib.roms.length === 0;

  // Keep a valid selection: default to the first NON-EMPTY group.
  const validKeys = groups.map((g) => g.key);
  const defaultKey = nonEmpty[0]?.key ?? groups[0]?.key;
  const current = validKeys.includes(active) ? active : defaultKey;
  useEffect(() => { setPage(1); }, [current]);

  const activeGroup = groups.find((g) => g.key === current);

  const q = query.trim().toLowerCase();
  const searching = q.length > 0;
  // Search scope: the selected system by default, or ALL when 전체 is chosen.
  const searchPool = searchAll ? lib.roms : (activeGroup?.roms ?? []);
  const matchName = (r) =>
    (r.stored_name || r.original_name || "").toLowerCase().includes(q);
  let items = searching
    ? searchPool.filter(matchName).sort(sortCmp)
    : (activeGroup?.roms ?? []);
  // 커버 누락 필터: 커버 없는 롬만
  if (missingOnly) items = items.filter((r) => r.cover_status !== "ok");
  // 한글명 아님 필터: 한글 없는 번역대상 롬만 (숫자전용 '1942'류 제외 — 칩 배지와 동일 기준)
  // Korea-specific → only active in Korean mode (others detect cover-missing only).
  if (nonKoOnly && koFeature) items = items.filter(needsKorean);
  // 무평점 필터: IGDB 점수조차 없는 비주류 롬만 (score>0 아닌 것 = -1/미조회). 똥겜 솎아내기용.
  if (unratedOnly) items = items.filter((r) => !(r.igdb_score > 0));
  // PICO-8 호환 상태 필터 (pico8 보기에서만 적용; 미설정 = untested)
  if (current === "pico8" && compatFilter !== "all") {
    items = items.filter((r) => (r.pico8_compat || "untested") === compatFilter);
  }
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageItems = items.slice((safePage - 1) * pageSize, safePage * pageSize);
  useEffect(() => { setPage(1); }, [q]);
  useEffect(() => { setPage(1); }, [pageSize]);
  useEffect(() => { setPage(1); }, [missingOnly, nonKoOnly, unratedOnly, compatFilter]);

  return (
    <div className="stack">
      <div className="muted">
        <Library size={13} aria-hidden /> {t("Stored")}: {lib.roms.length} ROM · {lib.videos.length} VIDEO · {lib.music?.length || 0} MUSIC{(items.length > 0 || searching || missingOnly || nonKoOnly || unratedOnly || (current === "pico8" && compatFilter !== "all")) ? ` · ${t("{n} shown", { n: items.length })}` : ""}
      </div>

      {error && <div className="badge failed">{error}</div>}
      {loading && (
        <>
          {/* Platform list is a fixed lineup → skeleton chips while loading
              (use the known system count, falling back to the full lineup). */}
          <div className="lib-chips">
            {Array.from({ length: systems.length || 21 }).map((_, i) => (
              <div className="lib-chip skel-chip" key={i}>
                <div className="skel-ico" />
                <div className="skel-line" />
              </div>
            ))}
          </div>
          <div className="grid">
            {Array.from({ length: pageSize }).map((_, i) => (
              <div className="card skel-card" key={i}>
                <div className="shot cover-slot"><div className="skeleton" /></div>
                <div className="skel-line" />
                <div className="skel-line short" />
              </div>
            ))}
          </div>
        </>
      )}
      {!loading && empty && (
        <div className="muted"><Inbox size={13} aria-hidden /> {t("No files stored yet. Pick a platform and upload ROMs below.")}</div>
      )}

      {/* Search by name, scoped to the selected system or everything */}
      {!empty && (
        <div className="lib-searchbar">
          <div className="lib-search">
            {selected.size > 0 && (
              <span className="sel-count-badge">{t("{n} platforms", { n: selected.size })} · {t("{n} files selected", { n: selectedFileCount.toLocaleString() })}</span>
            )}
            <Search size={14} strokeWidth={2.5} aria-hidden />
            <input
              className="text-input"
              value={query}
              placeholder={searchAll ? t("Search game name (all)") : t("Search game name ({sys})", { sys: activeGroup?.system.name ?? t("current platform") })}
              spellCheck={false}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <SortSelect
            value={sortMode}
            onChange={setSortMode}
            options={SORT_ORDER.map((m) => ({ key: m, label: SORT_LABELS[m] }))}
          />
          <div className="lib-filters">
            <span className="search-scope" role="group" aria-label={t("Search scope")}>
              <button className={`scope-btn ${!searchAll ? "on" : ""}`} onClick={() => setSearchAll(false)}>{t("This")}</button>
              <button className={`scope-btn ${searchAll ? "on" : ""}`} onClick={() => setSearchAll(true)}>{t("All")}</button>
            </span>
            <span className="search-scope" role="group" aria-label={t("Filter")}>
              <button className={`scope-btn ${missingOnly ? "on" : ""}`} onClick={() => setMissingOnly((m) => !m)}
                title={t("Show only ROMs without covers")} aria-pressed={missingOnly}>
                <ImageOff size={13} strokeWidth={2.5} /> {t("No cover")}
              </button>
              {koFeature && (
                <button className={`scope-btn ${nonKoOnly ? "on" : ""}`} onClick={() => setNonKoOnly((m) => !m)}
                  title={t("Show only non-Korean-named ROMs (English/Japanese names)")} aria-pressed={nonKoOnly}>
                  <Languages size={13} strokeWidth={2.5} /> {t("Korean")}
                </button>
              )}
              <button className={`scope-btn ${unratedOnly ? "on" : ""}`} onClick={() => setUnratedOnly((m) => !m)}
                title={t("Show only ROMs with no IGDB score (obscure titles)")} aria-pressed={unratedOnly}>
                <StarOff size={13} strokeWidth={2.5} /> {t("Unrated")}
              </button>
            </span>
          </div>
        </div>
      )}

      {/* PICO-8 전용: 게임 목록 위 호환 상태 필터 (전체 + 상태별) */}
      {!empty && current === "pico8" && !(searching && searchAll) && (
        <div className="lib-compat-filter">
          <Pico8CompatFilter value={compatFilter} onChange={setCompatFilter}
            roms={activeGroup?.roms ?? []} />
        </div>
      )}

      {/* Per-system count chips — also shown when empty so you can pick a system
          to upload into; hidden only during an ALL-scope search. */}
      {!loading && !(searching && searchAll) && (
        <div className="lib-chips">
          {groups.map((g) => {
            // The count reflects what actually ships to the device. Excluded
            // ROMs (manual opt-out or PICO-8 구동불가) are tallied in the footer.
            const incl = g.roms.filter(shipsToSd);
            const miss = incl.filter((r) => r.cover_status !== "ok").length;
            const koMiss = incl.filter(needsKorean).length;
            return (
            <button
              key={g.key}
              className={`lib-chip ${g.key === current ? "on" : ""} ${g.roms.length ? "" : "empty"}`}
              style={{ "--sys": systemColor(g.key) }}
              onClick={() => setActive(g.key)}
            >
              {/* One issue badge at most (avoid 3-up crowding): cover-missing has
                  priority; the 한글제목 badge only shows once covers are done. */}
              <span className="lib-chip-badges">
                <span className="lib-chip-count">{incl.length}</span>
                {miss > 0
                  ? <span className="lib-chip-miss" title={t("{n} missing covers", { n: miss })}>{miss}</span>
                  : koFeature && koMiss > 0 && <span className="lib-chip-komiss" title={t("{n} without Korean titles", { n: koMiss })}>{koMiss}</span>}
              </span>
              {g.roms.length > 0 && (
                <span
                  className={`lib-chip-check ${selected.has(g.key) ? "on" : ""}`}
                  role="checkbox" aria-checked={selected.has(g.key)} title={t("Select for download")}
                  onClick={(e) => { e.stopPropagation(); onToggleSel(g.key); }}
                >
                  {selected.has(g.key) && <Check size={16} strokeWidth={4} aria-hidden />}
                </span>
              )}
              <SystemIcon dirname={g.system.dirname} size={30} />
              <span className="lib-chip-name">{g.system.name}</span>
            </button>
          );})}
        </div>
      )}

      {/* Selected system has no roms → upload straight into it right here. */}
      {!loading && !searching && activeGroup && activeGroup.roms.length === 0 && (
        <div className="lib-upload-area">
          <Dropzone
            multiple
            folder={FOLDER_SYSTEMS.has(current)}
            accept={FOLDER_SYSTEMS.has(current) ? "" : activeGroup.system.exts.map((e) => "." + e).join(",")}
            label={
              busy
                ? <span className="dz-label"><Upload size={16} aria-hidden /> {t("Uploading…")}</span>
                : FOLDER_SYSTEMS.has(current)
                  ? <span className="dz-label"><Upload size={16} aria-hidden /> {t("Drag & drop a {name} game folder (.cue + tracks) or use 'Whole folder'", { name: activeGroup.system.name })}</span>
                  : <span className="dz-label"><Upload size={16} aria-hidden /> {t("Drag {sys} ROMs here or click", { sys: activeGroup.system.name })}</span>
            }
            onFiles={uploadHere}
          />
        </div>
      )}


      {/* Active group grid (paginated) */}
      {pageItems.length > 0 && (
        <div className="grid">
          {pageItems.map((r) => (
                <RomCard
                  key={r.id}
                  rom={r}
                  previewSrc={r.cover_status === "ok" ? coverUrl(r.id) : null}
                  onChanged={refresh}
                  dupes={dupesById[r.id] || []}
                />
              ))}
        </div>
      )}

      {/* One empty-state message only — positive when ONLY the cover filter is on,
          generic otherwise. (Never two at once.) */}
      {!loading && !empty && items.length === 0 && (searching || missingOnly || nonKoOnly) && (
        <div className="lib-empty">
          <Inbox size={18} aria-hidden />{" "}
          {missingOnly && !searching && !nonKoOnly
            ? t("No missing covers on this platform ✓")
            : t("No games found")}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="lib-pager">
          <button className="icon-btn" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>
            <ChevronLeft size={14} strokeWidth={2.5} />
          </button>
          <span className="lib-pager-info">{safePage} / {totalPages}</span>
          <button className="icon-btn" disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)}>
            <ChevronRight size={14} strokeWidth={2.5} />
          </button>
        </div>
      )}

      {/* SD-excluded tally for the current platform — kept in the library but not
          shipped. Sits at the card list's bottom-right; hidden when there are none. */}
      {!searching && activeGroup && (() => {
        const excl = activeGroup.roms.filter((r) => !shipsToSd(r)).length;
        return excl > 0 ? (
          <div className="lib-grid-foot" title={t("Kept in the library, not included in the SD download")}>
            <HardDriveDownload size={11} strokeWidth={2.5} aria-hidden /> {t("{n} excluded from SD", { n: excl })}
          </div>
        ) : null;
      })()}
    </div>
  );
}

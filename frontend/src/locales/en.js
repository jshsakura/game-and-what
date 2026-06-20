// English is the SOURCE language: in-code strings are English and used directly as
// the lookup key, so this dictionary is empty by default (a key resolves to itself).
// It only carries DISAMBIGUATION overrides: distinct keys that must render the same
// English word but need different translations elsewhere (e.g. the PICO-8 "Works"
// badge vs. the "OK" confirm button). See i18n.locales.js for the locale set.
export default {
  "Works": "OK",
  "Not on SD": "Not on SD",
  "Exclude from SD": "Exclude from SD",
  "Excluded from SD": "Excluded from SD",
  "Excluded from the SD download (kept in library)": "Excluded from the SD download (kept in library)",
  "Keep this ROM in the library but exclude it from the SD download": "Keep this ROM in the library but exclude it from the SD download",
  "{n} excluded from SD": "{n} excluded from SD",
  "Kept in the library, not included in the SD download": "Kept in the library, not included in the SD download",
};

// English is the SOURCE language: in-code strings are English and used directly as
// the lookup key, so this dictionary is empty by default (a key resolves to itself).
// It only carries DISAMBIGUATION overrides: distinct keys that must render the same
// English word but need different translations elsewhere (e.g. the PICO-8 "Works"
// badge vs. the "OK" confirm button). See i18n.locales.js for the locale set.
export default {
  "Works": "OK",
};

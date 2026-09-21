# System icons — 1:1 with firmware folder name (dirname)

Name each icon exactly `<dirname>.svg` (or `.png` for the few raster assets),
using the dirname registered in `backend/app/systems.py`. The UI loads the SVG
first unless `PNG_ICON_SYSTEMS` in `frontend/src/components.jsx` says otherwise;
missing assets fall back to a colored system abbreviation. Keep new icons square,
monochrome (`currentColor`) or flat color, and record third-party sources in
`ROMM_ATTRIBUTIONS.txt`.

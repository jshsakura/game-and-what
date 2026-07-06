import React from "react";
import { Clapperboard, Images } from "lucide-react";
import { useT } from "../i18n.jsx";
import ClockGifSection from "./ClockGifSection.jsx";
import ClockAlbumSection from "./ClockAlbumSection.jsx";

// The Clock tab bundles both firmware clock-background tools, mirroring the
// device menu (PAUSE → Background): a looping /clock/bg.gif and the /clock/album
// .565 photo album. Both share the same drag & zoom cropper (clockShared.jsx).
export default function ClockBgTab() {
  const t = useT();
  return (
    <div className="stack">
      <div className="clock-section-head">
        <Clapperboard size={14} strokeWidth={2.5} aria-hidden /> {t("Background GIF (bg.gif)")}
      </div>
      <ClockGifSection />

      <div className="clock-section-head">
        <Images size={14} strokeWidth={2.5} aria-hidden /> {t("Photo album (.565)")}
      </div>
      <ClockAlbumSection />
    </div>
  );
}

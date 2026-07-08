import React from "react";
import { BellRing, Clapperboard, Images } from "lucide-react";
import { useT } from "../i18n.jsx";
import ClockGifSection from "./ClockGifSection.jsx";
import ClockAlbumSection from "./ClockAlbumSection.jsx";
import ClockAlarmSection from "./ClockAlarmSection.jsx";

// The Clock tab bundles the firmware clock's three media tools, mirroring the
// device's own /clock subfolders: a looping /clock/gif/bg.gif background, the
// /clock/album photo album, and the /clock/alarm alarm sounds. The two picture
// tools share the same drag & zoom cropper (clockShared.jsx).
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

      <div className="clock-section-head">
        <BellRing size={14} strokeWidth={2.5} aria-hidden /> {t("Alarm sound (.mp3)")}
      </div>
      <ClockAlarmSection />
    </div>
  );
}

import React, { useState } from "react";
import { BellRing, Clapperboard, Images } from "lucide-react";
import { useT } from "../i18n.jsx";
import ClockGifSection from "./ClockGifSection.jsx";
import ClockAlbumSection from "./ClockAlbumSection.jsx";
import ClockAlarmSection from "./ClockAlarmSection.jsx";

// The Clock tab bundles the firmware clock's three media tools, mirroring the
// device's own /clock subfolders: a looping /clock/gif background, the
// /clock/album photo album, and the /clock/alarm alarm sounds. Each is a tool
// plus its own stored library, so they get one sub-tab each rather than three
// long sections stacked in a single scroll. The two picture tools share the
// same drag & zoom cropper (clockShared.jsx).
export default function ClockBgTab({ files = [], onChanged }) {
  const t = useT();
  const [sub, setSub] = useState("gif"); // "gif" | "album" | "alarm"

  const of = (kind) => files.filter((f) => f.kind === kind);
  const gifs = of("gif");
  const photos = of("album");
  const sounds = of("alarm");

  const TABS = [
    { key: "gif", label: t("Background GIF"), Icon: Clapperboard, n: gifs.length },
    { key: "album", label: t("Photo album"), Icon: Images, n: photos.length },
    { key: "alarm", label: t("Alarm sound"), Icon: BellRing, n: sounds.length },
  ];

  return (
    <div className="stack">
      <div className="media-subtabs clock-subtabs">
        {TABS.map(({ key, label, Icon, n }) => (
          <button key={key} className={`media-subtab ${sub === key ? "on" : ""}`} onClick={() => setSub(key)}>
            <Icon size={14} strokeWidth={2.5} aria-hidden /> {label}
            {n > 0 && <span className="media-count">{n}</span>}
          </button>
        ))}
      </div>

      {sub === "gif" && <ClockGifSection gifs={gifs} onChanged={onChanged} />}
      {sub === "album" && <ClockAlbumSection photos={photos} onChanged={onChanged} />}
      {sub === "alarm" && <ClockAlarmSection sounds={sounds} onChanged={onChanged} />}
    </div>
  );
}

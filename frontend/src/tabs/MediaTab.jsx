import React, { useCallback, useEffect, useState } from "react";
import { Clapperboard, Music } from "lucide-react";
import VideoTab from "./VideoTab.jsx";
import MusicTab from "./MusicTab.jsx";
import { VideoCard, MusicList } from "../components.jsx";
import { getLibrary } from "../api.js";
import { useT } from "../i18n.jsx";

// MEDIA = convert/store tools AND the stored library for media — kept entirely here
// (media isn't part of the platform SD-selection in LIBRARY). Split into 영상 / 음악
// sub-tabs; each owns its own upload tool + storage list.
export default function MediaTab({ onChanged }) {
  const t = useT();
  const [media, setMedia] = useState({ videos: [], music: [] });
  const [sub, setSub] = useState("video"); // "video" | "music"

  const reload = useCallback(() => {
    getLibrary()
      .then((l) => setMedia({ videos: l.videos || [], music: l.music || [] }))
      .catch(() => {});
  }, []);
  useEffect(() => { reload(); }, [reload]);

  // a child upload/edit/delete → refresh this list AND the app (counts elsewhere).
  const refresh = () => { reload(); onChanged?.(); };

  return (
    <div className="stack media-tab">
      <div className="media-subtabs">
        <button className={`media-subtab ${sub === "video" ? "on" : ""}`} onClick={() => setSub("video")}>
          <Clapperboard size={14} strokeWidth={2.5} aria-hidden /> {t("Video")}
          {media.videos.length > 0 && <span className="media-count">{media.videos.length}</span>}
        </button>
        <button className={`media-subtab ${sub === "music" ? "on" : ""}`} onClick={() => setSub("music")}>
          <Music size={14} strokeWidth={2.5} aria-hidden /> {t("Music")}
          {media.music.length > 0 && <span className="media-count">{media.music.length}</span>}
        </button>
      </div>

      {sub === "video" ? (
        <section className="media-section">
          <VideoTab onChanged={refresh} />
          {media.videos.length > 0 && (
            <div className="grid media-grid">
              {media.videos.map((v) => <VideoCard key={v.id} video={v} onChanged={refresh} />)}
            </div>
          )}
        </section>
      ) : (
        <section className="media-section">
          <MusicTab onChanged={refresh} />
          {media.music.length > 0 && <MusicList tracks={media.music} onChanged={refresh} />}
        </section>
      )}
    </div>
  );
}

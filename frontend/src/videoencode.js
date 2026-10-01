// Pure argv builder; parity with backend/app/services/video.py is tested.
export const DEFAULT_VIDEO_PROFILE = "balanced";
export const VIDEO_PROFILES = {
  balanced: { fps: 20, bitrate: "1600k", qmin: 17 },
  smooth: { fps: 30, bitrate: "2400k", qmin: 17 },
  light: { fps: 15, bitrate: "1000k", qmin: 20 },
};
const FILTERS = {
  fit: "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black",
  fill: "scale=320:240:force_original_aspect_ratio=increase,crop=320:240",
  stretch: "scale=320:240",
};
export function buildDeviceVideoArgs(input, output, mode = "fit", profile = DEFAULT_VIDEO_PROFILE) {
  const settings = Object.hasOwn(VIDEO_PROFILES, profile) ? VIDEO_PROFILES[profile] : VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE];
  return [
    "-hide_banner", "-y", "-i", input,
    "-c:v", "mjpeg", "-pix_fmt", "yuvj420p", "-b:v", settings.bitrate, "-maxrate", settings.bitrate,
    "-bufsize", "320k", "-qmin", String(settings.qmin), "-qmax", "31",
    "-vf", `${Object.hasOwn(FILTERS, mode) ? FILTERS[mode] : FILTERS.fit},fps=${settings.fps}`,
    "-c:a", "libmp3lame", "-ac", "1", "-b:a", "96k", "-ar", "48000", output,
  ];
}

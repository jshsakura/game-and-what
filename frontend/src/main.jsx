import React from "react";
import { createRoot } from "react-dom/client";
// Self-hosted fonts (bundled) — no dependency on Google's CDN reachability.
import "@fontsource/press-start-2p/400.css";
import "@fontsource/noto-sans-kr/korean-400.css";
import "@fontsource/noto-sans-kr/korean-700.css";
import "@fontsource/noto-sans-kr/latin-400.css";
import "@fontsource/noto-sans-kr/latin-700.css";
import App from "./App.jsx";
import { ToastProvider } from "./toast.jsx";
import { DownloadProvider } from "./download.jsx";
import { ConfigProvider } from "./config.jsx";
import { I18nProvider } from "./i18n.jsx";
import { DEMO, installDemoFetch } from "./demo.js";
import "./theme.css";

// Static GitHub Pages preview: no backend — serve canned fixtures from fetch.
if (DEMO) installDemoFetch();

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <I18nProvider>
      <ConfigProvider>
        <ToastProvider>
          <DownloadProvider>
            <App />
          </DownloadProvider>
        </ToastProvider>
      </ConfigProvider>
    </I18nProvider>
  </React.StrictMode>
);

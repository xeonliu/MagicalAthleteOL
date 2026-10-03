import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./i18n";
import "./styles.css";
import "./mobile.css";
import "./art-pack.css";
import { applyArtPack } from "./artPack";

applyArtPack();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

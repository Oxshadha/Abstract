import { StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";

import "@/index.css";

import { LandingPage } from "./LandingPage";

/** Hydrates the prerendered landing page (spec 016 AC7). Only this page's code is loaded. */
const root = document.getElementById("root");
if (root) {
  hydrateRoot(
    root,
    <StrictMode>
      <LandingPage />
    </StrictMode>,
  );
}

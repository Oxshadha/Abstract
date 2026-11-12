import { StrictMode } from "react";
import { renderToString } from "react-dom/server";

import { LandingPage } from "./LandingPage";

/** Build-time render of the landing page to static HTML (spec 016 AC7). */
export function render(): string {
  return renderToString(
    <StrictMode>
      <LandingPage />
    </StrictMode>,
  );
}

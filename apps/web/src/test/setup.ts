import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-cleans when Vitest globals are on; they are off here, so unmount
// rendered components explicitly after every test (otherwise tests see each other's DOM).
afterEach(() => {
  cleanup();
});

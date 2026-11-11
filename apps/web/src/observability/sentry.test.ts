import * as Sentry from "@sentry/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { initSentry } from "./sentry";

vi.mock("@sentry/react", () => ({ init: vi.fn(), browserTracingIntegration: vi.fn(() => ({})) }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.mocked(Sentry.init).mockClear();
});

describe("AC12/AC13: Sentry", () => {
  it("stays off without a DSN", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    expect(initSentry()).toBe(false);
    expect(Sentry.init).not.toHaveBeenCalled();
  });

  it("initialises lazily with privacy defaults and strips request bodies (D76)", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://key@o1.ingest.de.sentry.io/1");
    expect(initSentry()).toBe(true);
    await vi.waitFor(() => {
      expect(Sentry.init).toHaveBeenCalled();
    });
    const options = vi.mocked(Sentry.init).mock.calls[0]?.[0];
    expect(options?.dataCollection).toMatchObject({ userInfo: false, httpBodies: [] });
    const scrubbed = options?.beforeSend?.(
      { type: undefined, request: { data: "paper text", cookies: { s: "1" }, url: "/x" } },
      {},
    );
    expect(scrubbed).toEqual({ type: undefined, request: { url: "/x" } });
  });
});

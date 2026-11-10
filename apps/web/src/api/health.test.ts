import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchHealth } from "./health";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchHealth uses the generated client", () => {
  it("calls /api/v1/healthz and maps the response", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchHealth()).resolves.toBe("ok");
    const request = (fetchMock.mock.calls[0] as unknown[])[0] as Request;
    expect(new URL(request.url).pathname).toBe("/api/v1/healthz");
  });

  it("returns down on a problem+json error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ status: 503 }), {
            status: 503,
            headers: { "content-type": "application/problem+json" },
          }),
        ),
      ),
    );
    await expect(fetchHealth()).resolves.toBe("down");
  });
});

describe("fetchHealth resilience", () => {
  it("returns down when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(fetchHealth()).resolves.toBe("down");
  });
});

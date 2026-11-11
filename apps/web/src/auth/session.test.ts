import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";

import { configureAuth, devTokenSource } from "./session";

afterEach(() => {
  vi.unstubAllGlobals();
  configureAuth(() => Promise.resolve(null), () => undefined);
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("AC14: token on every API call", () => {
  it("attaches the bearer token from the active source", async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() => Promise.resolve(json({ status: "ok" })));
    vi.stubGlobal("fetch", fetchMock);
    configureAuth(() => Promise.resolve("tok-123"), () => undefined);
    await api.GET("/api/v1/healthz");
    const sent = fetchMock.mock.calls[0]?.[0];
    expect(sent?.headers.get("Authorization")).toBe("Bearer tok-123");
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() => Promise.resolve(json({ status: "ok" })));
    vi.stubGlobal("fetch", fetchMock);
    await api.GET("/api/v1/healthz");
    expect(fetchMock.mock.calls[0]?.[0].headers.has("Authorization")).toBe(false);
  });

  it("ends the session on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ status: 401 }, 401))));
    const onUnauthorized = vi.fn();
    configureAuth(() => Promise.resolve("expired"), onUnauthorized);
    await api.GET("/api/v1/me");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});

describe("D70: development token source", () => {
  it("fetches once, caches in memory, and refetches after reset", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json({ token: "dev-tok" })));
    vi.stubGlobal("fetch", fetchMock);
    const dev = devTokenSource("http://api.test");
    expect(await dev.source()).toBe("dev-tok");
    expect(await dev.source()).toBe("dev-tok");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    dev.reset();
    await dev.source();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(window.localStorage.length).toBe(0); // never persisted
  });
});

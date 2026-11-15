import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";

import { localReset, problem } from "./problem";

describe("Spec 012 AC3: limits say when they reset in the reader's time", () => {
  it("rewrites a limit's UTC reset into local time", () => {
    const daily = localReset("You have reached today's limit of 100 questions. It resets at midnight UTC.", "2026-11-13T00:00:00Z", "en-GB");
    expect(daily).toMatch(/^You have reached today's limit of 100 questions\. It resets at \d{1,2}:\d{2}/);
    expect(daily).not.toContain("UTC");
    const monthly = localReset("You have reached this month's limit of 20 papers. It resets on the 1st of next month (UTC).", "2026-12-01T00:00:00Z", "en-GB");
    expect(monthly).toMatch(/It resets on \d{1,2} (Nov|Dec)\.$/);
    expect(localReset("Something else.", "2026-12-01T00:00:00Z")).toBe("Something else.");
  });
});

describe("errors show the server's own message", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it("reads the problem detail even though the API client already read the body", async () => {
    const body = { type: "https://abstract.dev/problems/rate-limited", detail: "Too many requests. Try again in a minute." };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status: 429, headers: { "Content-Type": "application/problem+json" } }))));
    const { data, response } = await api.GET("/api/v1/papers/trash");
    expect(data).toBeUndefined();
    expect((await problem(response, "Fallback")).message).toBe("Too many requests. Try again in a minute.");
  });
});

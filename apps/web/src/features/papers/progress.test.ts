import { afterEach, describe, expect, it, vi } from "vitest";

import { configureAuth } from "@/auth/session";

import { status } from "./fixtures";
import { createSseParser, isFinished, readProgressStream } from "./progress";

afterEach(() => {
  vi.unstubAllGlobals();
});

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

describe("AC12: event stream parsing", () => {
  it("handles events split across chunks, heartbeats and CRLF", () => {
    const parse = createSseParser();
    expect(parse("retry: 3000\n\n: keep-alive\n\nid: 4\nevent: sta")).toEqual([]);
    expect(parse('tus\r\ndata: {"a":1}\r\n\r\n')).toEqual([{ id: "4", event: "status", data: '{"a":1}' }]);
  });

  it("knows when processing is finished", () => {
    expect(isFinished(status())).toBe(false);
    const done = status({ status: "ready", steps: status().steps.map((s) => ({ ...s, state: "done" as const })) });
    expect(isFinished(done)).toBe(true);
  });
});

describe("AC12: reading the stream", () => {
  it("sends the token in a header (never in the URL) and resumes with Last-Event-ID", async () => {
    configureAuth(() => Promise.resolve("tok"), () => undefined);
    const fetch = vi.fn(() =>
      Promise.resolve(new Response(streamOf([`id: 7\nevent: status\ndata: ${JSON.stringify(status({ seq: 7 }))}\n\n`]), { status: 200 })),
    );
    vi.stubGlobal("fetch", fetch);
    const seen: number[] = [];
    const last = await readProgressStream("p1", "6", (s) => seen.push(s.seq), new AbortController().signal);
    expect(seen).toEqual([7]);
    expect(last).toBe("7");
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain("tok");
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok", "Last-Event-ID": "6" });
  });

  it("refreshes the token once on 401", async () => {
    configureAuth(() => Promise.resolve("old"), () => undefined, () => Promise.resolve("new"));
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(streamOf([]), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await readProgressStream("p1", null, () => undefined, new AbortController().signal);
    const second = fetch.mock.calls[1] as [string, RequestInit];
    expect(second[1].headers).toMatchObject({ Authorization: "Bearer new" });
  });

  it("rejects on HTTP errors so the caller can fall back to polling", async () => {
    configureAuth(() => Promise.resolve("t"), () => undefined);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 502 }))));
    await expect(readProgressStream("p1", null, () => undefined, new AbortController().signal)).rejects.toThrow();
  });
});

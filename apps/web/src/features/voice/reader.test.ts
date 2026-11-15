import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SpeechOutput } from "./engines";
import { createReader, prepareSegments } from "./reader";

vi.mock("./usage", () => ({ reportVoice: vi.fn() }));
const { reportVoice } = await import("./usage");

/** A fake engine: each sentence ends when the test says so. */
function fakeEngine() {
  const spoken: string[] = [];
  let finish: (() => void) | null = null;
  let fail: ((e: Error) => void) | null = null;
  const output: SpeechOutput = {
    engine: "fake",
    supported: () => true,
    voices: () => [],
    onVoicesChanged: () => () => undefined,
    speak: (text) =>
      new Promise<void>((resolve, reject) => {
        spoken.push(text);
        finish = resolve;
        fail = reject;
      }),
    pause: vi.fn(),
    resume: vi.fn(),
    cancel: () => { fail?.(Object.assign(new Error("interrupted"), { name: "Cancelled" })); },
  };
  const end = async () => {
    finish?.();
    await new Promise((r) => setTimeout(r, 0));
  };
  return { output, spoken, end };
}

const SUMMARY = [
  { key: "title", text: "Attention Is All You Need. Vaswani et al." },
  { key: "methodology", heading: "Methodology", text: "They use **self-attention** [1]. No recurrence [S2]." },
  { key: "results", heading: "Results", text: "BLEU of 28.4 on WMT 2014." },
];

beforeEach(() => { vi.mocked(reportVoice).mockClear(); });

describe("AC1, AC5: the reader speaks field by field, sentence by sentence", () => {
  it("prepares fields with their names and without markers", () => {
    expect(prepareSegments(SUMMARY).map((s) => s.sentences)).toEqual([
      ["Attention Is All You Need.", "Vaswani et al."],
      ["Methodology.", "They use self-attention.", "No recurrence."],
      ["Results.", "BLEU of 28.4 on WMT 2014."],
    ]);
  });

  it("reads everything in order, then counts a finished Listen", async () => {
    const { output, spoken, end } = fakeEngine();
    const reader = createReader(output);
    reader.start("summary:s1", SUMMARY);
    for (let i = 0; i < 7; i++) await end();
    expect(spoken).toEqual(["Attention Is All You Need.", "Vaswani et al.", "Methodology.", "They use self-attention.", "No recurrence.", "Results.", "BLEU of 28.4 on WMT 2014."]);
    expect(reader.getState().status).toBe("idle");
    expect(reportVoice).toHaveBeenCalledWith("listen_started", "fake");
    expect(reportVoice).toHaveBeenCalledWith("listen_finished", "fake");
  });
});

describe("AC3: controls", () => {
  it("pauses and resumes at the same sentence, and skips fields", async () => {
    const { output, spoken, end } = fakeEngine();
    const reader = createReader(output);
    reader.start("summary:s1", SUMMARY);
    await end(); // first sentence done
    reader.pause();
    expect(reader.getState()).toMatchObject({ status: "paused", segment: 0, sentence: 1 });
    reader.resume();
    expect(spoken.at(-1)).toBe("Vaswani et al.");
    reader.next();
    await new Promise((r) => setTimeout(r, 0));
    expect(spoken.at(-1)).toBe("Methodology.");
    reader.previous(); // just started this field: back to the one before
    await new Promise((r) => setTimeout(r, 0));
    expect(spoken.at(-1)).toBe("Attention Is All You Need.");
    reader.stop();
    expect(reader.getState().status).toBe("idle");
  });

  it("AC5b: starting another reading stops the first", () => {
    const { output, spoken } = fakeEngine();
    const reader = createReader(output);
    reader.start("summary:s1", SUMMARY);
    reader.start("answer:m1", [{ key: "answer", text: "Self-attention relates positions [1]." }]);
    expect(reader.getState().owner).toBe("answer:m1");
    expect(spoken.at(-1)).toBe("Self-attention relates positions.");
    reader.stop("summary:s1"); // stopping someone else's reading does nothing
    expect(reader.getState().status).toBe("playing");
  });
});

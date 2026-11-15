import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { engines, type ListenCallbacks, type SpeechInput, type SpeechOutput } from "./engines";
import { useCanListen, useCanSpeak } from "./hooks";
import { ListenControls } from "./ListenControls";
import { reader } from "./reader";

vi.mock("./usage", () => ({ reportVoice: vi.fn() }));
vi.mock("@/features/flags/api", () => ({ useFlag: () => true }));

const real = { ...engines };
let heard: ListenCallbacks | null = null;
const stopListening = vi.fn(() => { heard?.onEnd(); });

const fakeInput: SpeechInput = {
  engine: "fake",
  processedBy: "Google",
  supported: () => true,
  listen: (_lang, callbacks) => {
    heard = callbacks;
    return stopListening;
  },
};
const fakeOutput: SpeechOutput = {
  engine: "fake",
  supported: () => true,
  voices: () => [{ id: "v1", name: "Samantha", lang: "en-US", local: true }, { id: "v2", name: "Google UK", lang: "en-GB", local: false }],
  onVoicesChanged: () => () => undefined,
  speak: () => new Promise<void>(() => undefined),
  pause: vi.fn(),
  resume: vi.fn(),
  cancel: vi.fn(),
};

function wrap(node: ReactNode) {
  const client = new QueryClient();
  client.setQueryData(["papers", "p1"], { title: "Attention Is All You Need", abstract: "We report BLEU on WMT 2014." });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  engines.input = fakeInput;
  engines.output = fakeOutput;
  heard = null;
  stopListening.mockClear();
  localStorage.clear();
});
afterEach(() => {
  engines.input = real.input;
  engines.output = real.output;
});

function Probe() {
  return <p>{`listen:${String(useCanListen())} speak:${String(useCanSpeak())}`}</p>;
}

describe("AC11: only where it works", () => {
  it("hides Listen without voices and Speak without recognition", () => {
    engines.output = { ...fakeOutput, voices: () => [] };
    engines.input = { ...fakeInput, supported: () => false };
    wrap(<Probe />);
    expect(screen.getByText("listen:false speak:false")).toBeInTheDocument();
  });
});

describe("Listen controls (AC3, AC4, AC5b)", () => {
  afterEach(() => { reader.stop(); });

  it("starts, shows the controls, offers device voices only and remembers the speed", async () => {
    wrap(<ListenControls owner="summary:s1" variant="summary" segments={() => [{ key: "a", text: "One. Two." }, { key: "b", heading: "Results", text: "Three." }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen" }));
    const bar = await screen.findByRole("toolbar", { name: "Reading controls" });
    expect(within(bar).getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Next section" })).toBeEnabled();
    fireEvent.click(within(bar).getByRole("button", { name: /^Voice/ }));
    expect(screen.getByRole("option", { name: /Samantha/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Google UK/ })).toBeNull(); // AC4: online voices hidden
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    fireEvent.click(within(bar).getByRole("button", { name: /^Speed/ }));
    fireEvent.click(screen.getByRole("option", { name: "1.5×" }));
    expect(JSON.parse(localStorage.getItem("abstract.voice") ?? "{}")).toMatchObject({ rate: 1.5 });
    fireEvent.click(within(bar).getByRole("button", { name: "Stop reading" }));
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });

  it("AC5b: an answer has a small speaker named Listen to this answer", () => {
    wrap(<ListenControls owner="answer:m1" variant="answer" segments={() => [{ key: "answer", text: "Yes [1]." }]} />);
    expect(screen.getByRole("button", { name: "Listen to this answer" })).toBeInTheDocument();
  });
});

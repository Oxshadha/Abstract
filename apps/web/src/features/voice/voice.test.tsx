import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dictation } from "./Dictation";
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

/** A tiny composer like the chat's: a box, a send button and the microphone. */
function Composer({ onSend }: { onSend: (text: string) => void }) {
  const [input, setInput] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSend(input); }}>
      <Dictation paperId="p1" disabled={false} onStart={() => undefined} onDictated={() => undefined} onReview={setInput} onSend={onSend}>
        {(mic) => (
          <>
            <label>Ask about this paper<textarea value={input} onChange={(e) => { setInput(e.target.value); }} /></label>
            {mic}
            <button type="submit">Send</button>
          </>
        )}
      </Dictation>
    </form>
  );
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

describe("Speak (spec 020 AC6 to AC8, D104)", () => {
  it("AC6: listening shows the bar and the words; Stop puts them in the box and sends nothing", async () => {
    const send = vi.fn();
    wrap(<Composer onSend={send} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by speaking" }));
    const bar = screen.getByRole("group", { name: "Speaking" });
    expect(within(bar).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByText("Your speech is turned into text by Google.")).toBeInTheDocument(); // AC8 first use
    act(() => { heard?.onText("what is the main result", false); });
    expect(screen.getByText("what is the main result")).toBeInTheDocument();
    fireEvent.click(within(bar).getByRole("button", { name: "Stop and review" }));
    await waitFor(() => { expect(screen.getByLabelText("Ask about this paper")).toHaveValue("what is the main result"); });
    expect(send).not.toHaveBeenCalled();
  });

  it("AC6, D104: the send button while listening sends the dictated question", async () => {
    const send = vi.fn();
    wrap(<Composer onSend={send} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by speaking" }));
    act(() => { heard?.onText("what blue score did they get", true); });
    fireEvent.click(within(screen.getByRole("group", { name: "Speaking" })).getByRole("button", { name: "Send" }));
    await waitFor(() => { expect(send).toHaveBeenCalledWith("what BLEU score did they get"); });
  });

  it("AC6: Cancel throws the words away", () => {
    const send = vi.fn();
    wrap(<Composer onSend={send} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by speaking" }));
    act(() => { heard?.onText("never mind", true); });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Ask about this paper")).toHaveValue("");
    expect(send).not.toHaveBeenCalled();
  });

  it("AC7: research terms are matched to the paper, visibly and undoably", async () => {
    wrap(<Composer onSend={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by speaking" }));
    act(() => { heard?.onText("what blue score on w m t", true); });
    fireEvent.click(screen.getByRole("button", { name: "Stop and review" }));
    const box = screen.getByLabelText("Ask about this paper");
    await waitFor(() => { expect(box).toHaveValue("what BLEU score on WMT"); });
    expect(screen.getByText(/Matched the paper's terms: w m t to WMT, blue to BLEU/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(box).toHaveValue("what blue score on w m t");
  });

  it("AC8: a blocked microphone says how to allow it", () => {
    wrap(<Composer onSend={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask by speaking" }));
    act(() => { heard?.onError("not-allowed"); heard?.onEnd(); });
    expect(screen.getByRole("alert")).toHaveTextContent("The microphone is blocked. Allow it for this site");
  });
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

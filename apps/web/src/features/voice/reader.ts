import { useSyncExternalStore } from "react";

import { engines, isCancelled, type SpeechOutput } from "./engines";
import { prepareForSpeech, splitSentences } from "./prepare";
import { reportVoice } from "./usage";

/**
 * One reader for the whole app (spec 020 AC1 to AC5b): a summary or an answer is a list of
 * segments (fields), each spoken sentence by sentence so long text never stops part way (AC5).
 * Starting a new reading stops the one before. Pause stops the sentence and Resume starts it
 * again, which works the same in every browser (native pause is unreliable in some).
 */

export interface Segment {
  key: string;
  heading?: string; // spoken first, e.g. "Methodology."
  text: string; // Markdown as shown on screen
}

export interface PreparedSegment {
  key: string;
  sentences: string[];
}

export interface ReaderState {
  owner: string | null; // "summary:<id>" or "answer:<id>"
  status: "idle" | "playing" | "paused";
  segments: PreparedSegment[];
  segment: number;
  sentence: number;
}

export interface VoiceSettings {
  rate: number;
  voiceId?: string;
  showOnline: boolean;
}

export const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2] as const;
const SETTINGS_KEY = "abstract.voice";
const IDLE: ReaderState = { owner: null, status: "idle", segments: [], segment: 0, sentence: 0 };

function loadSettings(): VoiceSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") as Partial<VoiceSettings>;
    const rate = RATES.find((r) => r === saved.rate) ?? 1;
    return { rate, showOnline: saved.showOnline === true, ...(saved.voiceId ? { voiceId: saved.voiceId } : {}) };
  } catch {
    return { rate: 1, showOnline: false };
  }
}

export function prepareSegments(segments: Segment[]): PreparedSegment[] {
  return segments
    .map((s) => ({
      key: s.key,
      sentences: [...(s.heading ? [`${s.heading.replace(/[.:]+$/, "")}.`] : []), ...splitSentences(prepareForSpeech(s.text))],
    }))
    .filter((s) => s.sentences.length > 0);
}

class Reader {
  private state: ReaderState = IDLE;
  private settings: VoiceSettings = loadSettings();
  private listeners = new Set<() => void>();
  private run = 0; // bumps on every start, stop or jump, so an old loop ends quietly

  constructor(private readonly engine: () => SpeechOutput) {}

  private get output(): SpeechOutput {
    return this.engine();
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getState = () => this.state;
  getSettings = () => this.settings;

  private set(patch: Partial<ReaderState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => { l(); });
  }

  updateSettings(patch: Partial<VoiceSettings>) {
    this.settings = { ...this.settings, ...patch };
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings));
    } catch {
      // private mode: remembered for this visit only
    }
    this.listeners.forEach((l) => { l(); });
    if (this.state.status === "playing" && ("rate" in patch || "voiceId" in patch)) this.jump(this.state.segment, this.state.sentence);
  }

  start(owner: string, segments: Segment[]) {
    const prepared = prepareSegments(segments);
    if (prepared.length === 0) return;
    this.output.cancel();
    this.set({ owner, segments: prepared, segment: 0, sentence: 0, status: "playing" });
    reportVoice("listen_started", this.output.engine);
    void this.loop(++this.run);
  }

  private async loop(run: number) {
    while (run === this.run) {
      const { segments, segment, sentence } = this.state;
      const text = segments[segment]?.sentences[sentence];
      if (text === undefined) {
        reportVoice("listen_finished", this.output.engine);
        this.set(IDLE);
        return;
      }
      try {
        await this.output.speak(text, { rate: this.settings.rate, ...(this.settings.voiceId ? { voiceId: this.settings.voiceId } : {}) });
      } catch (error) {
        if (run !== this.run || isCancelled(error)) return;
        // A failed sentence is skipped rather than stopping the whole reading.
      }
      if (run !== this.run) return;
      const atEnd = sentence + 1 >= (segments[segment]?.sentences.length ?? 0);
      this.set(atEnd ? { segment: segment + 1, sentence: 0 } : { sentence: sentence + 1 });
    }
  }

  private jump(segment: number, sentence = 0) {
    this.run++;
    this.output.cancel();
    this.set({ segment, sentence, status: "playing" });
    void this.loop(this.run);
  }

  pause() {
    if (this.state.status !== "playing") return;
    this.run++;
    this.output.cancel();
    this.set({ status: "paused" });
  }

  resume() {
    if (this.state.status === "paused") this.jump(this.state.segment, this.state.sentence);
  }

  next() {
    if (this.state.owner && this.state.segment + 1 < this.state.segments.length) this.jump(this.state.segment + 1);
  }

  previous() {
    if (!this.state.owner) return;
    // Like a music player: back to the start of this field, or the one before if just started.
    this.jump(this.state.sentence > 0 ? this.state.segment : Math.max(0, this.state.segment - 1));
  }

  stop(owner?: string) {
    if (owner && this.state.owner !== owner) return;
    this.run++;
    this.output.cancel();
    this.set(IDLE);
  }
}

export const reader = new Reader(() => engines.output); // the engine is chosen in one place (AC10)

export function useReader(): ReaderState {
  return useSyncExternalStore(reader.subscribe, reader.getState);
}

export function useVoiceSettings(): VoiceSettings {
  return useSyncExternalStore(reader.subscribe, reader.getSettings);
}

/** For tests: a reader on a fake engine. */
export function createReader(output: SpeechOutput) {
  return new Reader(() => output);
}

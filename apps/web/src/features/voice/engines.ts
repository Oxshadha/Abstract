/**
 * Speech engines behind two small interfaces (spec 020 AC10, D102). The browser's own engines
 * (Web Speech API) are the baseline; a better engine later (Kokoro or Piper for listening, Gemini
 * or Whisper for speaking) is a new adapter here, chosen in `engines`, with no change to the panels.
 */

export interface Voice {
  id: string;
  name: string;
  lang: string;
  local: boolean; // runs on the device, so the text does not leave it (AC4)
}

export interface SpeakOptions {
  voiceId?: string;
  rate: number;
}

export interface SpeechOutput {
  readonly engine: string;
  supported(): boolean;
  voices(): Voice[];
  onVoicesChanged(listener: () => void): () => void;
  /** Speak one sentence; resolves when it ends, rejects if it was cancelled or failed. */
  speak(text: string, options: SpeakOptions): Promise<void>;
  pause(): void;
  resume(): void;
  cancel(): void;
}

export interface ListenCallbacks {
  onText: (text: string, final: boolean) => void;
  onEnd: () => void;
  onError: (reason: "not-allowed" | "network" | "no-speech" | "other") => void;
}

export interface SpeechInput {
  readonly engine: string;
  readonly processedBy: string; // where speech is processed, for the first-use note (AC8)
  supported(): boolean;
  /** Start listening; returns a function that stops it. */
  listen(lang: string, callbacks: ListenCallbacks): () => void;
}

// ---------- browser adapters ----------

class Cancelled extends Error {}

export const browserOutput: SpeechOutput = {
  engine: "browser",
  supported: () => typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance === "function",
  voices: () =>
    browserOutput.supported()
      ? window.speechSynthesis.getVoices().map((v) => ({ id: v.voiceURI, name: v.name, lang: v.lang, local: v.localService }))
      : [],
  onVoicesChanged: (listener) => {
    if (!browserOutput.supported()) return () => undefined;
    window.speechSynthesis.addEventListener("voiceschanged", listener);
    return () => { window.speechSynthesis.removeEventListener("voiceschanged", listener); };
  },
  speak: (text, { voiceId, rate }) =>
    new Promise<void>((resolve, reject) => {
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = window.speechSynthesis.getVoices().find((v) => v.voiceURI === voiceId);
      if (voice) {
        utterance.voice = voice;
        utterance.lang = voice.lang;
      }
      utterance.rate = rate;
      utterance.onend = () => { resolve(); };
      utterance.onerror = (event) => { reject(event.error === "interrupted" || event.error === "canceled" ? new Cancelled() : new Error(event.error)); };
      window.speechSynthesis.speak(utterance);
    }),
  pause: () => { window.speechSynthesis.pause(); },
  resume: () => { window.speechSynthesis.resume(); },
  cancel: () => { if (browserOutput.supported()) window.speechSynthesis.cancel(); },
};

interface RecognitionResult { readonly isFinal: boolean; readonly 0: { transcript: string } }
interface RecognitionEvent { readonly resultIndex: number; readonly results: ArrayLike<RecognitionResult> }
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionClass; webkitSpeechRecognition?: RecognitionClass };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

function processor(): string {
  const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
  if (/Edg\//.test(ua)) return "Microsoft";
  if (/Chrome\//.test(ua)) return "Google";
  if (/Safari\//.test(ua)) return "Apple";
  return "your browser's speech service";
}

export const browserInput: SpeechInput = {
  engine: "browser",
  get processedBy() { return processor(); },
  supported: () => recognitionClass() !== undefined,
  listen: (lang, { onText, onEnd, onError }) => {
    const Rec = recognitionClass();
    if (!Rec) {
      onError("other");
      return () => undefined;
    }
    const recognition = new Rec();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    let finalText = "";
    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result) continue;
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      onText((finalText + interim).replace(/\s+/g, " ").trim(), interim === "");
    };
    recognition.onerror = (event) => {
      const reason = event.error === "not-allowed" || event.error === "service-not-allowed" ? "not-allowed" : event.error === "network" ? "network" : event.error === "no-speech" ? "no-speech" : event.error === "aborted" ? null : "other";
      if (reason) onError(reason);
    };
    recognition.onend = onEnd;
    recognition.start();
    return () => { recognition.stop(); };
  },
};

/** The one place engines are chosen (AC10). */
export const engines: { output: SpeechOutput; input: SpeechInput } = { output: browserOutput, input: browserInput };

export function isCancelled(error: unknown): boolean {
  return error instanceof Cancelled;
}
